import datetime
import random

import pytest

from compass.application.shift_report import cap_per_contributor
from compass.domain.choice import (
    CandidateFeatures,
    ChoiceCase,
    ChoiceResult,
    case_auc,
    evaluate_choice,
    fit_cell_scores,
    fit_weight,
)
from compass.domain.contributions import ContributionRepository, Entry, HistorySnapshot
from compass.domain.feedback import FeedbackResult, Outcome, design_row, evaluate_feedback
from compass.domain.shift import NONE_CELL, Observation, classify_repository, observe
from compass.domain.statistics import Estimate
from compass.domain.verdict import Verdict, decide
from tests.vocabulary_fixtures import make_clusters, make_vocabulary

VOCABULARY = make_vocabulary(make_clusters(synonyms={"llm": "llm", "llms": "llm"}))
HISTORY = HistorySnapshot(topics=(("llms", 2), ("cli", 1)), languages=(("Python", 3),))


def repository(
    language: str | None, topics: list[str], stars: int = 1000
) -> ContributionRepository:
    return ContributionRepository(
        node_id=f"{language}-{'-'.join(topics)}",
        owner="org",
        name=f"{language}-{'-'.join(topics)}",
        url=f"https://github.com/org/{language}-{'-'.join(topics)}",
        is_fork=False,
        stars=stars,
        created_at=datetime.datetime(2020, 1, 1, tzinfo=datetime.UTC),
        language=language,
        language_bytes={language: 100} if language else {},
        topics=topics,
    )


def observation(
    target: ContributionRepository,
    login: str = "octocat",
    merged: bool | None = True,
    history: HistorySnapshot = HISTORY,
    prior_entries: int = 3,
) -> Observation:
    entry = Entry(
        login=login,
        repository=target,
        created_at=datetime.datetime(2024, 1, 1, tzinfo=datetime.UTC),
        merged=merged,
        returned=None,
        prior_entries=prior_entries,
        history=history,
    )

    return observe(entry, classify_repository(target.as_topic_project(), VOCABULARY), VOCABULARY)


def test_known_language_and_synonym_meaning_read_as_no_shift() -> None:
    seen = observation(repository("Python", ["llm"]))

    assert (seen.tooling_shift, seen.meaning_shift) == (False, False)
    assert seen.cell == "known/known"


def test_each_axis_shifts_on_its_own() -> None:
    tooling = observation(repository("Rust", ["llm"]))
    meaning = observation(repository("Python", ["emulator"]))

    assert (tooling.tooling_shift, tooling.meaning_shift) == (True, False)
    assert (meaning.tooling_shift, meaning.meaning_shift) == (False, True)


def test_a_repository_without_language_or_meaning_sits_in_the_none_cell() -> None:
    assert observation(repository(None, ["llm"])).cell == NONE_CELL
    assert observation(repository("Python", [])).cell == NONE_CELL


def test_tokens_split_tooling_from_meaning() -> None:
    target = classify_repository(repository("Rust", ["cli", "llms"]).as_topic_project(), VOCABULARY)

    assert "rust" in target.tokens.tooling
    assert "cli" in target.tokens.tooling
    assert target.tokens.meaning == frozenset({"llm"})
    assert target.tokens.raw == frozenset({"rust", "cli", "llms"})


def test_a_history_without_meaning_is_not_ready() -> None:
    empty = HistorySnapshot(topics=(), languages=(("Python", 1),))

    assert not observation(repository("Python", ["llm"]), history=empty).contributor.ready
    assert observation(repository("Python", ["llm"])).contributor.ready


def test_design_row_holds_shifts_and_controls() -> None:
    row = design_row(observation(repository("Rust", ["emulator"], stars=999)))

    assert row[:3] == [1.0, 1.0, 1.0]
    assert row[3] == pytest.approx(6.907755)


def features(tooling: float, meaning: float, cell: str = "known/known") -> CandidateFeatures:
    return CandidateFeatures(
        raw=0.0, grouped=(tooling + meaning) / 2, tooling=tooling, meaning=meaning, cell=cell
    )


def test_weight_fit_prefers_the_axis_that_separates() -> None:
    cases = [
        ChoiceCase(
            login="a",
            actual=features(0.2, 0.9),
            decoys=(features(0.9, 0.3), features(0.5, 0.2)),
        )
    ]

    assert fit_weight(cases) == 0.4


def test_cell_scores_favour_cells_entered_more_than_decoys() -> None:
    cases = [
        ChoiceCase(
            login="a",
            actual=features(1, 1, "known/known"),
            decoys=(features(0, 0, "unfamiliar/new"), features(0, 0, "unfamiliar/new")),
        )
    ]
    scores = fit_cell_scores(cases)

    assert scores["known/known"] > scores["unfamiliar/new"]


def test_case_auc_scores_the_entry_against_its_decoys() -> None:
    case = ChoiceCase(
        login="a", actual=features(0.5, 0.5), decoys=(features(0.1, 0.1), features(0.9, 0.9))
    )

    assert case_auc(case, lambda item: item.tooling) == pytest.approx(0.5)


def test_choice_evaluation_reports_every_model_and_gain() -> None:
    rng = random.Random(1)
    cases = [
        ChoiceCase(
            login=f"user{index}",
            actual=features(rng.random(), 0.8),
            decoys=tuple(features(rng.random(), rng.random() * 0.5) for _ in range(5)),
        )
        for index in range(40)
    ]
    result = evaluate_choice(cases, 100, random.Random(2))

    assert set(result.auc) == {
        "blind_raw",
        "blind_grouped",
        "tooling_only",
        "meaning_only",
        "two_axis",
        "crossing_cells",
    }
    assert result.auc["meaning_only"].value > result.auc["tooling_only"].value
    assert result.weight < 0.5


def test_feedback_recovers_a_tooling_penalty() -> None:
    rng = random.Random(4)
    cells = {
        (False, False): ("Python", ["llm"]),
        (True, False): ("Rust", ["llm"]),
        (False, True): ("Python", ["emulator"]),
        (True, True): ("Rust", ["emulator"]),
    }
    observations = []

    for index in range(150):
        for (tooling, _), (language, topics) in cells.items():
            target = repository(language, topics, stars=rng.randrange(100, 50_000))
            observations.append(
                observation(
                    target,
                    login=f"user{index}",
                    merged=rng.random() < (0.3 if tooling else 0.7),
                    prior_entries=rng.randrange(20),
                )
            )

    result = evaluate_feedback(observations, Outcome.MERGED, 300, random.Random(5))

    assert result is not None
    assert result.coefficients["tooling_shift"].high < 0
    assert result.coefficients["meaning_shift"].low < 0 < result.coefficients["meaning_shift"].high
    assert result.coefficients["tooling_minus_meaning"].excludes_zero


def estimate(value: float, low: float, high: float) -> Estimate:
    return Estimate(value=value, low=low, high=high)


def choice(gain: Estimate, over_tooling: Estimate, over_meaning: Estimate) -> ChoiceResult:
    return ChoiceResult(
        train_cases=0,
        test_cases=0,
        test_contributors=0,
        weight=0.5,
        cell_scores={},
        auc={},
        gains={
            "two_axis_over_blind_grouped": gain,
            "two_axis_over_tooling_only": over_tooling,
            "two_axis_over_meaning_only": over_meaning,
        },
    )


def feedback(tooling: Estimate, meaning: Estimate, difference: Estimate) -> FeedbackResult:
    return FeedbackResult(
        outcome=Outcome.MERGED,
        entries=0,
        contributors=0,
        cells={},
        coefficients={
            "tooling_shift": tooling,
            "meaning_shift": meaning,
            "both_shifts": estimate(0, -1, 1),
            "tooling_minus_meaning": difference,
        },
    )


NULL = estimate(0.0, -0.01, 0.01)
REAL = estimate(0.05, 0.02, 0.08)


def test_verdict_kills_a_split_that_adds_nothing() -> None:
    decision = decide(0.9, 0.2, choice(NULL, NULL, NULL), [feedback(NULL, NULL, NULL)])

    assert decision.verdict is Verdict.KILL_NO_GAIN


def test_verdict_kills_redundant_axes_first() -> None:
    decision = decide(0.9, 0.8, choice(REAL, REAL, REAL), [feedback(REAL, NULL, REAL)])

    assert decision.verdict is Verdict.KILL_REDUNDANT


def test_verdict_keeps_the_split_and_names_a_silent_axis() -> None:
    decision = decide(0.9, 0.2, choice(NULL, NULL, REAL), [feedback(REAL, NULL, REAL)])

    assert decision.verdict is Verdict.KEEP
    assert decision.axes_without_signal == ("meaning",)


def test_verdict_asks_for_a_meaning_source_when_coverage_is_low() -> None:
    decision = decide(0.5, 0.2, choice(REAL, REAL, REAL), [])

    assert decision.verdict is Verdict.KEEP_NEEDS_MEANING_SOURCE


def test_entry_cap_samples_only_large_contributors() -> None:
    heavy = [observation(repository("Python", ["llm"]), login="heavy") for _ in range(7)]
    light = [observation(repository("Python", ["llm"]), login="light") for _ in range(2)]
    capped = cap_per_contributor([*heavy, *light], 3)

    assert [item.entry.login for item in capped].count("heavy") == 3
    assert [item.entry.login for item in capped].count("light") == 2
    assert cap_per_contributor(heavy, None) == heavy
