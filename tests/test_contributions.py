import datetime

from compass.domain.contributions import (
    AuthoredPullRequest,
    ContributionRepository,
    ContributorHistory,
    RepositoryStore,
    extract_entries,
)

FETCHED_AT = datetime.datetime(2026, 10, 29, tzinfo=datetime.UTC)


def day(year: int, month: int, date: int) -> datetime.datetime:
    return datetime.datetime(year, month, date, tzinfo=datetime.UTC)


def repository(
    node_id: str,
    owner: str = "org",
    stars: int = 1000,
    is_fork: bool = False,
    language: str | None = "Python",
    topics: list[str] | None = None,
    created_at: datetime.datetime | None = None,
) -> ContributionRepository:
    return ContributionRepository(
        node_id=node_id,
        owner=owner,
        name=node_id,
        url=f"https://github.com/{owner}/{node_id}",
        is_fork=is_fork,
        stars=stars,
        created_at=created_at or day(2015, 1, 1),
        language=language,
        topics=topics or [],
    )


def pull_request(
    node_id: str,
    created_at: datetime.datetime,
    merged_at: datetime.datetime | None = None,
    merged_by_author: bool = False,
) -> AuthoredPullRequest:
    return AuthoredPullRequest(
        repository_id=node_id,
        created_at=created_at,
        merged_at=merged_at,
        merged_by_author=merged_by_author,
    )


def history(
    pull_requests: list[AuthoredPullRequest],
    owned: list[ContributionRepository] | None = None,
) -> ContributorHistory:
    return ContributorHistory(
        login="octocat",
        external_pull_requests=len(pull_requests),
        complete=True,
        owned=owned or [],
        pull_requests=pull_requests,
        creation_date=FETCHED_AT,
        update_date=FETCHED_AT,
    )


def test_only_the_first_pull_request_to_a_repository_is_an_entry() -> None:
    repositories = {"a": repository("a")}
    entries = extract_entries(
        history(
            [
                pull_request("a", day(2024, 3, 1)),
                pull_request("a", day(2024, 1, 1), merged_at=day(2024, 1, 2)),
            ]
        ),
        repositories,
        min_stars=100,
    )

    assert [entry.created_at for entry in entries] == [day(2024, 1, 1)]
    assert entries[0].merged is True


def test_ineligible_repositories_and_self_merges_leave_no_entry() -> None:
    repositories = {
        "fork": repository("fork", is_fork=True),
        "small": repository("small", stars=99),
        "own": repository("own", owner="OctoCat"),
        "self": repository("self"),
        "old": repository("old"),
    }
    entries = extract_entries(
        history(
            [
                pull_request("fork", day(2024, 1, 1)),
                pull_request("small", day(2024, 1, 1)),
                pull_request("own", day(2024, 1, 1)),
                pull_request("self", day(2024, 1, 1), day(2024, 1, 1), merged_by_author=True),
                pull_request("old", day(2016, 12, 31)),
                pull_request("gone", day(2024, 1, 1)),
            ]
        ),
        repositories,
        min_stars=100,
    )

    assert entries == []


def test_history_holds_owned_repositories_and_earlier_merges_only() -> None:
    repositories = {
        "first": repository("first", language="Go", topics=["kubernetes"]),
        "second": repository("second", language="Rust", topics=["cli"]),
        "third": repository("third"),
    }
    owned = [
        repository("mine", owner="octocat", topics=["editor"], created_at=day(2020, 1, 1)),
        repository("later", owner="octocat", topics=["game"], created_at=day(2025, 1, 1)),
    ]
    entries = extract_entries(
        history(
            [
                pull_request("first", day(2021, 1, 1), merged_at=day(2021, 2, 1)),
                pull_request("second", day(2021, 3, 1)),
                pull_request("third", day(2022, 1, 1)),
            ],
            owned=owned,
        ),
        repositories,
        min_stars=100,
    )
    snapshots = {entry.repository.node_id: entry.history for entry in entries}

    assert snapshots["first"].topics == (("editor", 1),)
    assert dict(snapshots["second"].topics) == {"editor": 1, "kubernetes": 1}
    assert dict(snapshots["third"].languages) == {"Python": 1, "Go": 1}
    assert [entry.prior_entries for entry in entries] == [0, 1, 2]


def test_outcome_windows_leave_recent_entries_open() -> None:
    repositories = {name: repository(name) for name in ["early", "middle", "late"]}
    entries = extract_entries(
        history(
            [
                pull_request("early", day(2025, 1, 1)),
                pull_request("early", day(2025, 6, 1), merged_at=day(2025, 6, 2)),
                pull_request("middle", day(2026, 7, 1), merged_at=day(2026, 7, 2)),
                pull_request("late", day(2026, 10, 1), merged_at=day(2026, 10, 2)),
            ]
        ),
        repositories,
        min_stars=100,
    )
    outcomes = {entry.repository.node_id: (entry.merged, entry.returned) for entry in entries}

    assert outcomes == {
        "early": (False, True),
        "middle": (True, None),
        "late": (None, None),
    }


def test_a_return_needs_a_merge_inside_the_window() -> None:
    repositories = {"a": repository("a")}
    entries = extract_entries(
        history(
            [
                pull_request("a", day(2024, 1, 1)),
                pull_request("a", day(2024, 2, 1)),
                pull_request("a", day(2024, 9, 1), merged_at=day(2024, 9, 2)),
            ]
        ),
        repositories,
        min_stars=100,
    )

    assert entries[0].returned is False


def test_store_lists_only_unknown_repositories() -> None:
    store = RepositoryStore(repositories={"a": repository("a")}, missing=["b"])

    assert store.unknown(["a", "b", "c", "c"]) == ["c"]
