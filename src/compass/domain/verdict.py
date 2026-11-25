import dataclasses
from collections.abc import Sequence
from enum import StrEnum

from compass.domain.choice import ChoiceResult
from compass.domain.feedback import FeedbackResult

COVERAGE_FLOOR = 0.80
PHI_CEILING = 0.5
CHOICE_GAIN = 0.01


class Verdict(StrEnum):
    KEEP = "keep the split and build the engine on it"
    KEEP_NEEDS_MEANING_SOURCE = "keep the split, but meaning needs a source beyond topics"
    KILL_REDUNDANT = "kill the split, because one axis carries the other"
    KILL_NO_GAIN = "kill the split, because it adds nothing to an undivided bag"


@dataclasses.dataclass(frozen=True)
class Decision:
    assessable: bool
    distinct: bool
    choice: bool
    feedback: bool
    verdict: Verdict
    axes_without_signal: tuple[str, ...]


def choice_passes(choice: ChoiceResult) -> bool:
    gain = choice.gains["two_axis_over_blind_grouped"]

    return gain.value >= CHOICE_GAIN and gain.low > 0


def feedback_passes(result: FeedbackResult) -> bool:
    coefficients = result.coefficients

    return coefficients["tooling_minus_meaning"].excludes_zero and (
        coefficients["tooling_shift"].excludes_zero or coefficients["meaning_shift"].excludes_zero
    )


def axis_signal(choice: ChoiceResult, feedback: Sequence[FeedbackResult], axis: str) -> bool:
    other = "meaning" if axis == "tooling" else "tooling"
    choice_gain = choice.gains[f"two_axis_over_{other}_only"].low > 0
    feedback_gain = any(result.coefficients[f"{axis}_shift"].excludes_zero for result in feedback)

    return choice_gain or feedback_gain


def verdict_for(assessable: bool, distinct: bool, useful: bool) -> Verdict:
    if not distinct:
        return Verdict.KILL_REDUNDANT

    if not useful:
        return Verdict.KILL_NO_GAIN

    return Verdict.KEEP if assessable else Verdict.KEEP_NEEDS_MEANING_SOURCE


def decide(
    coverage: float,
    phi: float,
    choice: ChoiceResult,
    feedback: Sequence[FeedbackResult],
) -> Decision:
    assessable = coverage >= COVERAGE_FLOOR
    distinct = abs(phi) <= PHI_CEILING
    choice_ok = choice_passes(choice)
    feedback_ok = any(feedback_passes(result) for result in feedback)
    verdict = verdict_for(assessable, distinct, choice_ok or feedback_ok)
    survives = verdict in (Verdict.KEEP, Verdict.KEEP_NEEDS_MEANING_SOURCE)

    return Decision(
        assessable=assessable,
        distinct=distinct,
        choice=choice_ok,
        feedback=feedback_ok,
        verdict=verdict,
        axes_without_signal=tuple(
            axis
            for axis in ("tooling", "meaning")
            if survives and not axis_signal(choice, feedback, axis)
        ),
    )
