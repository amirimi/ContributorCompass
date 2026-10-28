import datetime

from compass.adapters import GitHubClient, TopicCache, TopicRepoRecord
from compass.application.topics import collect_profile
from compass.domain import PersonalProfileFile, ProjectTopicsFile

STALE_AFTER = datetime.timedelta(days=30)


class FakeCache(TopicCache):
    def __init__(self, personal: PersonalProfileFile | None = None) -> None:
        self.personal = personal
        self.projects: dict[str, ProjectTopicsFile] = {}

    def load_personal(self) -> PersonalProfileFile | None:
        return self.personal

    def save_personal(self, profile: PersonalProfileFile) -> None:
        self.personal = profile

    def load_projects(self, topic: str) -> ProjectTopicsFile | None:
        return self.projects.get(topic)

    def save_projects(self, topic: str, project_topics: ProjectTopicsFile) -> None:
        self.projects[topic] = project_topics


class FakeGitHub(GitHubClient):
    def __init__(self) -> None:
        self.calls = 0

    def user_repos(self, github_handle: str, max_pages: int = 5) -> list[TopicRepoRecord]:
        self.calls += 1

        return [
            TopicRepoRecord(
                node_id="node",
                owner=github_handle,
                name="repo",
                url=f"https://github.com/{github_handle}/repo",
                description=None,
                stars=1,
                forks=0,
                language="Python",
                topics=["python"],
                updated_at=datetime.datetime.now(datetime.UTC).isoformat(),
            )
        ]


def test_fresh_personal_cache_is_served_without_a_fetch() -> None:
    cached = PersonalProfileFile(
        github_handle="octocat",
        topics_frequency=[("python", 3)],
        languages_frequency=[("Python", 3)],
    )
    github = FakeGitHub()

    result = collect_profile(
        github_handle="https://github.com/Octocat",
        github=github,
        cache=FakeCache(personal=cached),
        stale_after=STALE_AFTER,
    )

    assert result is cached
    assert github.calls == 0


def test_stale_personal_cache_is_refetched_and_saved() -> None:
    old = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=31)
    stale = PersonalProfileFile(
        github_handle="octocat",
        topics_frequency=[("python", 3)],
        languages_frequency=[("Python", 3)],
        update_date=old,
    )
    cache = FakeCache(personal=stale)
    github = FakeGitHub()

    result = collect_profile(
        github_handle="octocat", github=github, cache=cache, stale_after=STALE_AFTER
    )

    assert github.calls == 1
    assert result.topics_frequency == [("python", 1)]
    assert result.languages_frequency == [("Python", 1)]
    assert cache.personal is result
