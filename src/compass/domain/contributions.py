import dataclasses
import datetime
from collections import Counter, defaultdict
from collections.abc import Iterable

import pydantic

from compass.domain.models import CacheFile, DomainModel, PersonalProfileFile, TopicProject

TOPICS_INTRODUCED = datetime.datetime(2017, 1, 1, tzinfo=datetime.UTC)
MERGE_WINDOW = datetime.timedelta(days=60)
RETURN_WINDOW = datetime.timedelta(days=180)


class ContributionRepository(DomainModel):
    node_id: str
    owner: str
    name: str
    url: str
    is_fork: bool
    stars: int
    created_at: datetime.datetime
    language: str | None = None
    language_bytes: dict[str, int] = pydantic.Field(default_factory=dict)
    topics: list[str] = pydantic.Field(default_factory=list)

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.name}"

    def as_topic_project(self) -> TopicProject:
        return TopicProject(
            owner=self.owner,
            name=self.name,
            url=self.url,
            language=self.language,
            language_bytes=self.language_bytes,
            topics=self.topics,
            stars=self.stars,
            created_at=self.created_at,
        )


class AuthoredPullRequest(DomainModel):
    repository_id: str
    created_at: datetime.datetime
    merged_at: datetime.datetime | None = None
    merged_by_author: bool = False


class ContributorHistory(CacheFile):
    login: str
    external_pull_requests: int
    complete: bool
    owned: list[ContributionRepository] = pydantic.Field(default_factory=list)
    pull_requests: list[AuthoredPullRequest] = pydantic.Field(default_factory=list)


class RepositoryStore(CacheFile):
    repositories: dict[str, ContributionRepository] = pydantic.Field(default_factory=dict)
    missing: list[str] = pydantic.Field(default_factory=list)

    def unknown(self, node_ids: Iterable[str]) -> list[str]:
        missing = set(self.missing)

        return sorted(
            {
                node_id
                for node_id in node_ids
                if node_id not in self.repositories and node_id not in missing
            }
        )


class ShiftSample(CacheFile):
    seed: int
    logins: list[str] = pydantic.Field(default_factory=list)
    visited_projects: list[str] = pydantic.Field(default_factory=list)


@dataclasses.dataclass(frozen=True)
class HistorySnapshot:
    topics: tuple[tuple[str, int], ...]
    languages: tuple[tuple[str, int], ...]

    def as_profile(self, login: str) -> PersonalProfileFile:
        return PersonalProfileFile(
            github_handle=login,
            topics_frequency=list(self.topics),
            languages_frequency=list(self.languages),
        )


@dataclasses.dataclass(frozen=True)
class Entry:
    login: str
    repository: ContributionRepository
    created_at: datetime.datetime
    merged: bool | None
    returned: bool | None
    prior_entries: int
    history: HistorySnapshot


def history_joins(
    history: ContributorHistory,
    repositories: dict[str, ContributionRepository],
) -> list[tuple[datetime.datetime, ContributionRepository]]:
    joins = [(repository.created_at, repository) for repository in history.owned]
    first_merges: dict[str, datetime.datetime] = {}

    for pull_request in history.pull_requests:
        if pull_request.merged_at is None or pull_request.repository_id not in repositories:
            continue

        known = first_merges.get(pull_request.repository_id)

        if known is None or pull_request.merged_at < known:
            first_merges[pull_request.repository_id] = pull_request.merged_at

    joins.extend((merged_at, repositories[node_id]) for node_id, merged_at in first_merges.items())

    return sorted(joins, key=lambda join: join[0])


def pull_requests_by_repository(
    pull_requests: list[AuthoredPullRequest],
) -> dict[str, list[AuthoredPullRequest]]:
    grouped: defaultdict[str, list[AuthoredPullRequest]] = defaultdict(list)

    for pull_request in sorted(pull_requests, key=lambda item: item.created_at):
        grouped[pull_request.repository_id].append(pull_request)

    return dict(grouped)


def merged_outcome(entry: AuthoredPullRequest, fetched_at: datetime.datetime) -> bool | None:
    if entry.created_at > fetched_at - MERGE_WINDOW:
        return None

    return entry.merged_at is not None


def returned_outcome(
    entry: AuthoredPullRequest,
    later: list[AuthoredPullRequest],
    fetched_at: datetime.datetime,
) -> bool | None:
    if entry.created_at > fetched_at - RETURN_WINDOW:
        return None

    deadline = entry.created_at + RETURN_WINDOW

    return any(
        item.merged_at is not None and entry.created_at < item.created_at <= deadline
        for item in later
    )


def eligible_repository(repository: ContributionRepository, login: str, min_stars: int) -> bool:
    return (
        not repository.is_fork
        and repository.stars >= min_stars
        and repository.owner.lower() != login.lower()
    )


class HistoryAccumulator:
    def __init__(self, joins: list[tuple[datetime.datetime, ContributionRepository]]) -> None:
        self.joins = joins
        self.position = 0
        self.topics: Counter[str] = Counter()
        self.languages: Counter[str] = Counter()

    def advance(self, until: datetime.datetime) -> HistorySnapshot:
        while self.position < len(self.joins) and self.joins[self.position][0] < until:
            repository = self.joins[self.position][1]
            self.topics.update(repository.topics)

            if repository.language is not None:
                self.languages[repository.language] += 1

            self.position += 1

        return HistorySnapshot(
            topics=tuple(self.topics.most_common()),
            languages=tuple(self.languages.most_common()),
        )


def extract_entries(
    history: ContributorHistory,
    repositories: dict[str, ContributionRepository],
    min_stars: int,
) -> list[Entry]:
    grouped = pull_requests_by_repository(history.pull_requests)
    firsts = sorted(grouped.items(), key=lambda item: item[1][0].created_at)
    accumulator = HistoryAccumulator(history_joins(history, repositories))
    entries: list[Entry] = []

    for prior_entries, (node_id, pull_requests) in enumerate(firsts):
        first = pull_requests[0]
        repository = repositories.get(node_id)
        snapshot = accumulator.advance(first.created_at)

        if (
            repository is None
            or not eligible_repository(repository, history.login, min_stars)
            or first.created_at < TOPICS_INTRODUCED
            or first.merged_by_author
        ):
            continue

        entries.append(
            Entry(
                login=history.login,
                repository=repository,
                created_at=first.created_at,
                merged=merged_outcome(first, history.update_date),
                returned=returned_outcome(first, pull_requests[1:], history.update_date),
                prior_entries=prior_entries,
                history=snapshot,
            )
        )

    return entries
