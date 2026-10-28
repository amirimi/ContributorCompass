from compass.application.identity import RepositoryInspection
from compass.application.vocabulary import VocabularyReport
from compass.domain import Evidence
from compass.views.attribution import EXPLORE_ATTRIBUTION


def format_evidence(items: list[Evidence]) -> str:
    if not items:
        return "none"

    return ", ".join(f"{item.value} ({item.source}: {item.raw})" for item in items)


def format_counts(counts: list[tuple[str, int]]) -> str:
    return "\n".join(f"  {count:>5}  {name}" for name, count in counts)


def render_inspection(inspection: RepositoryInspection) -> str:
    identity = inspection.identity
    lines = [
        f"{inspection.project.owner}/{inspection.project.name}",
        f"  tooling     {format_evidence(identity.tooling)}",
        f"  meaning     {format_evidence(identity.meaning)}",
        f"  unresolved  {', '.join(identity.unresolved) or 'none'}",
    ]

    if inspection.crossing is not None:
        crossing = inspection.crossing
        lines.append(
            f"  crossing    tooling {crossing.tooling}, meaning {crossing.meaning}"
            f" ({', '.join(crossing.deciding_terms) or 'no deciding terms'})"
        )

    return "\n".join([*lines, "", EXPLORE_ATTRIBUTION])


def render_vocabulary_report(report: VocabularyReport) -> str:
    sections = [
        f"explore topics             {report.explore_terms}",
        f"linguist languages         {report.linguist_terms}",
        f"cached projects            {report.projects}",
        f"clustered tags             {report.clustered_tags}",
        f"tooling through synonyms   {report.inherited_tooling}",
        f"projects with tooling tags {report.projects_with_tooling_tags}",
        f"unresolved tags            {report.unresolved_tags}",
    ]

    if report.meaning_relations:
        sections += [
            "",
            "meaning relations to your profile",
            format_counts(report.meaning_relations),
        ]

    sections += [
        "",
        "most frequent tooling tags",
        format_counts(report.top_tooling_tags),
        "",
        "most frequent unresolved tags",
        format_counts(report.top_unresolved),
        "",
        EXPLORE_ATTRIBUTION,
    ]

    return "\n".join(sections)
