from compass.application.shift_data import FetchSummary
from compass.application.shift_report import OwnEntry, ShiftReport
from compass.domain.feedback import FeedbackResult
from compass.domain.statistics import Estimate

DETECTABLE_ERRORS = 2.8


def estimate(value: Estimate, digits: int = 3) -> str:
    return f"{value.value:+.{digits}f} [{value.low:+.{digits}f}, {value.high:+.{digits}f}]"


def share(part: int, whole: int) -> str:
    return f"{part:,} of {whole:,} ({part / whole:.1%})" if whole else f"{part:,} of 0"


def render_fetch_summary(summary: FetchSummary, points: int | None) -> str:
    minutes = summary.elapsed.total_seconds() / 60
    cost = f"{points:,} GraphQL points" if points is not None else "an unknown number of points"

    return (
        f"Fetched {summary.fetched} contributors in {minutes:.1f} minutes using {cost}. "
        f"Skipped {summary.skipped} above the pull request cap, {summary.failed} failed, "
        f"{summary.remaining} remain."
    )


def render_feedback(result: FeedbackResult) -> list[str]:
    lines = [
        f"  {result.outcome.value}: {result.entries:,} entries from {result.contributors:,} contributors"
    ]
    lines.extend(
        f"    {cell}: {rate.entries:,} entries, rate {rate.rate:.3f}"
        for cell, rate in result.cells.items()
    )
    lines.extend(
        f"    {name}: {estimate(value)}, detectable {DETECTABLE_ERRORS * value.standard_error:.3f}"
        for name, value in result.coefficients.items()
    )

    return lines


def render_report(report: ShiftReport) -> str:
    choice = report.choice
    decision = report.decision
    lines = [
        f"== {report.label} ==",
        f"Contributors: {report.contributors:,} complete, {report.skipped:,} skipped",
        f"D1 entries with a dominant language: {share(report.with_language, report.entries)}",
        f"D1 entries with a meaning value: {share(report.with_meaning, report.entries)}",
        f"D1 assessable on both axes: {share(report.assessable, report.entries)}",
        f"Eligible entries with a ready history: {report.eligible:,}",
        f"D2 phi of tooling shift and meaning shift: {report.phi:+.3f}",
        "Shipped cells among eligible entries:",
        *(f"  {cell}: {count:,}" for cell, count in report.cells.items()),
        (
            f"D3 choice: {choice.train_cases:,} train cases, {choice.test_cases:,} test cases "
            f"from {choice.test_contributors:,} contributors, tooling weight {choice.weight:.1f}"
        ),
        *(f"  AUC {name}: {estimate(value)}" for name, value in choice.auc.items()),
        *(f"  gain {name}: {estimate(value)}" for name, value in choice.gains.items()),
        "D4 feedback, linear probability with contributor fixed effects:",
    ]

    for result in report.feedback:
        lines.extend(render_feedback(result))

    lines.extend(
        [
            (
                f"Decision: assessable {decision.assessable}, distinct {decision.distinct}, "
                f"choice {decision.choice}, feedback {decision.feedback}"
            ),
            f"Verdict: {decision.verdict.value}",
            f"Axes without signal: {', '.join(decision.axes_without_signal) or 'none'}",
        ]
    )

    return "\n".join(lines)


def outcome_text(value: bool | None) -> str:
    return "open window" if value is None else "yes" if value else "no"


def render_own_entries(login: str, entries: list[OwnEntry]) -> str:
    lines = [f"== {login}: {len(entries)} entries =="]
    lines.extend(
        (
            f"  {entry.created_at:%Y-%m-%d} {entry.slug} ({entry.stars:,} stars) cell {entry.cell}, "
            f"with preferences {entry.with_preferences.tooling.value}/{entry.with_preferences.meaning.value}, "
            f"merged {outcome_text(entry.merged)}, returned {outcome_text(entry.returned)}"
        )
        for entry in entries
    )

    return "\n".join(lines)
