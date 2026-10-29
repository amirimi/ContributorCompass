import dataclasses
import math
import random
from collections import defaultdict
from collections.abc import Sequence
from enum import StrEnum

from compass.domain.shift import Observation
from compass.domain.statistics import (
    Estimate,
    GroupMoments,
    bootstrap_fixed_effects,
    contrast,
    demeaned_moments,
    fixed_effects_fit,
)

CONTRASTS = {
    "tooling_shift": (1.0, 0.0, 0.0, 0.0, 0.0),
    "meaning_shift": (0.0, 1.0, 0.0, 0.0, 0.0),
    "both_shifts": (0.0, 0.0, 1.0, 0.0, 0.0),
    "tooling_minus_meaning": (1.0, -1.0, 0.0, 0.0, 0.0),
}


class Outcome(StrEnum):
    MERGED = "merged"
    RETURNED = "returned"


@dataclasses.dataclass(frozen=True)
class CellRate:
    entries: int
    rate: float


@dataclasses.dataclass(frozen=True)
class FeedbackResult:
    outcome: Outcome
    entries: int
    contributors: int
    cells: dict[str, CellRate]
    coefficients: dict[str, Estimate]


def outcome_value(observation: Observation, outcome: Outcome) -> bool | None:
    if outcome is Outcome.MERGED:
        return observation.entry.merged

    return observation.entry.returned


def feedback_cell(observation: Observation) -> str:
    tooling = "tooling shift" if observation.tooling_shift else "tooling known"
    meaning = "meaning shift" if observation.meaning_shift else "meaning known"

    return f"{tooling}, {meaning}"


def design_row(observation: Observation) -> list[float]:
    tooling = float(observation.tooling_shift)
    meaning = float(observation.meaning_shift)

    return [
        tooling,
        meaning,
        tooling * meaning,
        math.log1p(observation.entry.repository.stars),
        math.log1p(observation.entry.prior_entries),
    ]


def usable(observations: Sequence[Observation], outcome: Outcome) -> list[Observation]:
    return [
        observation
        for observation in observations
        if observation.repository.assessable
        and observation.contributor.ready
        and outcome_value(observation, outcome) is not None
    ]


def cell_rates(observations: Sequence[Observation], outcome: Outcome) -> dict[str, CellRate]:
    cells: defaultdict[str, list[bool]] = defaultdict(list)

    for observation in observations:
        cells[feedback_cell(observation)].append(bool(outcome_value(observation, outcome)))

    return {
        cell: CellRate(entries=len(values), rate=sum(values) / len(values))
        for cell, values in sorted(cells.items())
    }


def contributor_moments(
    observations: Sequence[Observation], outcome: Outcome
) -> list[GroupMoments]:
    groups: defaultdict[str, list[Observation]] = defaultdict(list)

    for observation in observations:
        groups[observation.entry.login].append(observation)

    return [
        demeaned_moments(
            [design_row(observation) for observation in members],
            [float(bool(outcome_value(observation, outcome))) for observation in members],
        )
        for members in groups.values()
        if len(members) > 1
    ]


def evaluate_feedback(
    observations: Sequence[Observation],
    outcome: Outcome,
    reps: int,
    rng: random.Random,
) -> FeedbackResult | None:
    rows = usable(observations, outcome)
    moments = contributor_moments(rows, outcome)

    if not moments:
        return None

    point = fixed_effects_fit(moments)

    if point is None:
        return None

    draws = bootstrap_fixed_effects(moments, reps, rng)

    return FeedbackResult(
        outcome=outcome,
        entries=sum(item.rows for item in moments),
        contributors=len(moments),
        cells=cell_rates(rows, outcome),
        coefficients={name: contrast(point, draws, weights) for name, weights in CONTRASTS.items()},
    )
