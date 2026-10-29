import dataclasses
import hashlib
import math
import random
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence

from compass.domain.crossing import cross
from compass.domain.shift import (
    ClassifiedRepository,
    ContributorView,
    Observation,
    jaccard,
    shipped_cell,
)
from compass.domain.statistics import Estimate, auc, bootstrap_pooled_mean
from compass.domain.vocabulary import Vocabulary

DECOYS = 20
DECOY_ATTEMPTS = 50
WEIGHT_GRID = tuple(step / 10 for step in range(11))
BALANCED_WEIGHT = 0.5

GAINS = {
    "two_axis_over_blind_grouped": ("two_axis", "blind_grouped"),
    "two_axis_over_blind_raw": ("two_axis", "blind_raw"),
    "two_axis_over_tooling_only": ("two_axis", "tooling_only"),
    "two_axis_over_meaning_only": ("two_axis", "meaning_only"),
    "crossing_cells_over_blind_grouped": ("crossing_cells", "blind_grouped"),
}


@dataclasses.dataclass(frozen=True)
class CandidateFeatures:
    raw: float
    grouped: float
    tooling: float
    meaning: float
    cell: str


@dataclasses.dataclass(frozen=True)
class ChoiceCase:
    login: str
    actual: CandidateFeatures
    decoys: tuple[CandidateFeatures, ...]


@dataclasses.dataclass(frozen=True)
class ChoiceResult:
    train_cases: int
    test_cases: int
    test_contributors: int
    weight: float
    cell_scores: dict[str, float]
    auc: dict[str, Estimate]
    gains: dict[str, Estimate]


Scorer = Callable[[CandidateFeatures], float]


def in_test_half(login: str) -> bool:
    return hashlib.sha256(login.lower().encode()).digest()[0] % 2 == 1


def candidate_features(
    repository: ClassifiedRepository,
    contributor: ContributorView,
    vocabulary: Vocabulary,
) -> CandidateFeatures:
    crossing = cross(repository.identity, contributor.identity, vocabulary)
    history = contributor.tokens
    target = repository.tokens

    return CandidateFeatures(
        raw=jaccard(history.raw, target.raw),
        grouped=jaccard(history.grouped, target.grouped),
        tooling=jaccard(history.tooling, target.tooling),
        meaning=jaccard(history.meaning, target.meaning),
        cell=shipped_cell(repository, crossing),
    )


def draw_decoys(
    observation: Observation,
    pool: Sequence[Observation],
    touched: frozenset[str],
    rng: random.Random,
) -> list[ClassifiedRepository]:
    chosen: dict[str, ClassifiedRepository] = {}

    for _ in range(DECOYS * DECOY_ATTEMPTS):
        if len(chosen) == DECOYS:
            break

        candidate = rng.choice(pool)
        slug = candidate.entry.repository.slug

        if candidate.entry.login != observation.entry.login and slug not in touched:
            chosen.setdefault(slug, candidate.repository)

    return list(chosen.values())


def build_cases(
    observations: Sequence[Observation],
    touched: Mapping[str, frozenset[str]],
    vocabulary: Vocabulary,
    rng: random.Random,
) -> list[ChoiceCase]:
    cases: list[ChoiceCase] = []

    for observation in observations:
        decoys = draw_decoys(observation, observations, touched[observation.entry.login], rng)

        if len(decoys) < DECOYS:
            continue

        contributor = observation.contributor
        cases.append(
            ChoiceCase(
                login=observation.entry.login,
                actual=candidate_features(observation.repository, contributor, vocabulary),
                decoys=tuple(
                    candidate_features(decoy, contributor, vocabulary) for decoy in decoys
                ),
            )
        )

    return cases


def axis_scorer(weight: float) -> Scorer:
    return lambda features: weight * features.tooling + (1 - weight) * features.meaning


def cell_scorer(scores: Mapping[str, float]) -> Scorer:
    return lambda features: scores.get(features.cell, 0.0)


def case_auc(case: ChoiceCase, scorer: Scorer) -> float:
    return auc(scorer(case.actual), [scorer(decoy) for decoy in case.decoys])


def mean_auc(cases: Sequence[ChoiceCase], scorer: Scorer) -> float:
    return sum(case_auc(case, scorer) for case in cases) / len(cases)


def fit_weight(cases: Sequence[ChoiceCase]) -> float:
    return max(
        WEIGHT_GRID,
        key=lambda weight: (
            round(mean_auc(cases, axis_scorer(weight)), 6),
            -abs(weight - BALANCED_WEIGHT),
        ),
    )


def fit_cell_scores(cases: Sequence[ChoiceCase]) -> dict[str, float]:
    actual = Counter(case.actual.cell for case in cases)
    decoys = Counter(decoy.cell for case in cases for decoy in case.decoys)
    cells = set(actual) | set(decoys)
    actual_total = sum(actual.values()) + len(cells)
    decoy_total = sum(decoys.values()) + len(cells)

    return {
        cell: math.log((actual[cell] + 1) / actual_total)
        - math.log((decoys[cell] + 1) / decoy_total)
        for cell in cells
    }


def grouped_by_login(cases: Sequence[ChoiceCase], values: Sequence[float]) -> list[list[float]]:
    groups: defaultdict[str, list[float]] = defaultdict(list)

    for case, value in zip(cases, values, strict=True):
        groups[case.login].append(value)

    return list(groups.values())


def evaluate_choice(cases: Sequence[ChoiceCase], reps: int, rng: random.Random) -> ChoiceResult:
    train = [case for case in cases if not in_test_half(case.login)]
    test = [case for case in cases if in_test_half(case.login)]
    weight = fit_weight(train)
    cell_scores = fit_cell_scores(train)
    scorers: dict[str, Scorer] = {
        "blind_raw": lambda features: features.raw,
        "blind_grouped": lambda features: features.grouped,
        "tooling_only": axis_scorer(1.0),
        "meaning_only": axis_scorer(0.0),
        "two_axis": axis_scorer(weight),
        "crossing_cells": cell_scorer(cell_scores),
    }
    per_case = {name: [case_auc(case, scorer) for case in test] for name, scorer in scorers.items()}

    return ChoiceResult(
        train_cases=len(train),
        test_cases=len(test),
        test_contributors=len({case.login for case in test}),
        weight=weight,
        cell_scores=cell_scores,
        auc={
            name: bootstrap_pooled_mean(grouped_by_login(test, values), reps, rng)
            for name, values in per_case.items()
        },
        gains={
            name: bootstrap_pooled_mean(
                grouped_by_login(
                    test,
                    [
                        better - worse
                        for better, worse in zip(per_case[left], per_case[right], strict=True)
                    ],
                ),
                reps,
                rng,
            )
            for name, (left, right) in GAINS.items()
        },
    )
