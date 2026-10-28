from compass.application.clusters import ClusterReport


def render_cluster_report(report: ClusterReport) -> str:
    return "\n".join(
        [
            f"clustered tags            {report.tags}",
            f"synonym groups            {report.synonym_groups} ({report.synonym_singletons} single tags)",
            f"families                  {report.families} ({report.family_singletons} single tags)",
            f"tooling through synonyms  {report.inherited_tooling}",
        ]
    )
