import dataclasses

from compass.domain import (
    Crossing,
    PersonalProfileFile,
    Preferences,
    ProjectIdentity,
    TopicProject,
    Vocabulary,
    classify,
    cross,
    describe_contributor,
)


@dataclasses.dataclass(frozen=True)
class RepositoryInspection:
    project: TopicProject
    identity: ProjectIdentity
    crossing: Crossing | None


def find_project(slug: str, projects: list[TopicProject]) -> TopicProject | None:
    wanted = slug.strip("/").lower()

    for project in projects:
        if f"{project.owner}/{project.name}".lower() == wanted:
            return project

    return None


def inspect_repository(
    project: TopicProject,
    vocabulary: Vocabulary,
    profile: PersonalProfileFile | None,
    preferences: Preferences,
) -> RepositoryInspection:
    identity = classify(project, vocabulary)

    if profile is None:
        return RepositoryInspection(project=project, identity=identity, crossing=None)

    contributor = describe_contributor(profile, preferences, vocabulary)

    return RepositoryInspection(
        project=project,
        identity=identity,
        crossing=cross(identity, contributor, vocabulary),
    )
