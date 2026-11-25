import dataclasses
import datetime
import logging
from typing import Any

from githubkit.exception import GraphQLFailed

from compass.adapters.github import GitHubClient
from compass.domain.contributions import AuthoredPullRequest, ContributionRepository

logger = logging.getLogger(__name__)

SEARCH_RESULT_LIMIT = 1000
PAGE_SIZE = 100
HYDRATION_BATCH_SIZE = 100
SAMPLING_BATCH_SIZE = 20
RECENT_PULL_REQUESTS = 30
OWNED_REPOSITORY_PAGES = 5
EARLIEST_SEARCH_DATE = datetime.date(2008, 1, 1)
TOLERATED_ERRORS = frozenset({"NOT_FOUND", "FORBIDDEN"})

CONTRIBUTION_REPOSITORY_FRAGMENT = """
fragment ContributionRepository on Repository {
  id
  owner {
    login
  }
  name
  url
  isFork
  stargazerCount
  createdAt
  primaryLanguage {
    name
  }
  languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
    edges {
      size
      node {
        name
      }
    }
  }
  repositoryTopics(first: 20) {
    nodes {
      topic {
        name
      }
    }
  }
}
"""

OWNED_REPOSITORIES_QUERY = (
    CONTRIBUTION_REPOSITORY_FRAGMENT
    + """
query ($login: String!, $cursor: String) {
  user(login: $login) {
    repositories(first: 100, after: $cursor, ownerAffiliations: OWNER, isFork: false) {
      nodes {
        ...ContributionRepository
      }
      pageInfo {
        hasNextPage
        endCursor
      }
    }
  }
}
"""
)

HYDRATION_QUERY = (
    CONTRIBUTION_REPOSITORY_FRAGMENT
    + """
query ($ids: [ID!]!) {
  nodes(ids: $ids) {
    ... on Repository {
      ...ContributionRepository
    }
  }
}
"""
)

RATE_LIMIT_QUERY = """
query {
  rateLimit {
    remaining
    resetAt
  }
}
"""

PULL_REQUEST_SEARCH_QUERY = """
query ($searchQuery: String!, $first: Int!, $cursor: String) {
  search(query: $searchQuery, type: ISSUE, first: $first, after: $cursor) {
    issueCount
    nodes {
      ... on PullRequest {
        createdAt
        mergedAt
        mergedBy {
          login
        }
        repository {
          id
        }
      }
    }
    pageInfo {
      hasNextPage
      endCursor
    }
  }
}
"""


@dataclasses.dataclass(frozen=True)
class SearchPage:
    count: int
    pull_requests: list[AuthoredPullRequest]
    cursor: str | None


def parse_timestamp(value: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))


def build_contribution_repository(node: dict[str, Any]) -> ContributionRepository:
    language = node["primaryLanguage"]

    return ContributionRepository(
        node_id=node["id"],
        owner=node["owner"]["login"],
        name=node["name"],
        url=node["url"],
        is_fork=node["isFork"],
        stars=node["stargazerCount"],
        created_at=parse_timestamp(node["createdAt"]),
        language=language["name"] if language else None,
        language_bytes={edge["node"]["name"]: edge["size"] for edge in node["languages"]["edges"]},
        topics=[entry["topic"]["name"] for entry in node["repositoryTopics"]["nodes"]],
    )


def build_pull_request(node: dict[str, Any], login: str) -> AuthoredPullRequest | None:
    if not node or node.get("repository") is None:
        return None

    merged_by = node["mergedBy"]
    merged_at = node["mergedAt"]

    return AuthoredPullRequest(
        repository_id=node["repository"]["id"],
        created_at=parse_timestamp(node["createdAt"]),
        merged_at=parse_timestamp(merged_at) if merged_at else None,
        merged_by_author=merged_by is not None and merged_by["login"].lower() == login.lower(),
    )


def pull_request_search(login: str, start: datetime.date, end: datetime.date) -> str:
    return f"is:pr author:{login} -user:{login} created:{start}..{end} sort:created-asc"


def recent_authors_query(count: int) -> str:
    arguments = ", ".join(f"$o{index}: String!, $n{index}: String!" for index in range(count))
    fields = "\n".join(
        f"  r{index}: repository(owner: $o{index}, name: $n{index}) {{"
        f" pullRequests(last: {RECENT_PULL_REQUESTS}) {{ nodes {{ author {{ __typename login }} }} }} }}"
        for index in range(count)
    )

    return f"query ({arguments}) {{\n{fields}\n}}"


class ContributionSource:
    def __init__(self, github: GitHubClient) -> None:
        self.github = github

    def tolerant_graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        try:
            response: dict[str, Any] = self.github.graphql(query, variables)
        except GraphQLFailed as exc:
            if any(error.type not in TOLERATED_ERRORS for error in exc.response.errors or []):
                raise

            return exc.response.data or {}

        return response

    def rate_limit(self) -> tuple[int, str]:
        data = self.tolerant_graphql(RATE_LIMIT_QUERY, {})

        return data["rateLimit"]["remaining"], data["rateLimit"]["resetAt"]

    def recent_authors(self, projects: list[tuple[str, str]]) -> dict[str, list[str]]:
        authors: dict[str, list[str]] = {}

        for start in range(0, len(projects), SAMPLING_BATCH_SIZE):
            batch = projects[start : start + SAMPLING_BATCH_SIZE]
            variables: dict[str, Any] = {}

            for index, (owner, name) in enumerate(batch):
                variables[f"o{index}"] = owner
                variables[f"n{index}"] = name

            data = self.tolerant_graphql(recent_authors_query(len(batch)), variables)

            for index, (owner, name) in enumerate(batch):
                repository = data.get(f"r{index}")
                nodes = repository["pullRequests"]["nodes"] if repository else []
                authors[f"{owner}/{name}"] = [
                    node["author"]["login"]
                    for node in nodes
                    if node and node["author"] and node["author"]["__typename"] == "User"
                ]

        return authors

    def search_page(
        self,
        login: str,
        start: datetime.date,
        end: datetime.date,
        cursor: str | None,
        first: int = PAGE_SIZE,
    ) -> SearchPage:
        data = self.tolerant_graphql(
            PULL_REQUEST_SEARCH_QUERY,
            {
                "searchQuery": pull_request_search(login, start, end),
                "first": first,
                "cursor": cursor,
            },
        )
        search = data["search"]
        page_info = search["pageInfo"]
        parsed = (build_pull_request(node, login) for node in search["nodes"])

        return SearchPage(
            count=search["issueCount"],
            pull_requests=[item for item in parsed if item is not None],
            cursor=page_info["endCursor"] if page_info["hasNextPage"] else None,
        )

    def pull_request_count(self, login: str, until: datetime.date) -> int:
        return self.search_page(login, EARLIEST_SEARCH_DATE, until, cursor=None, first=1).count

    def pull_requests(
        self,
        login: str,
        start: datetime.date,
        end: datetime.date,
    ) -> list[AuthoredPullRequest]:
        page = self.search_page(login, start, end, cursor=None)

        if page.count > SEARCH_RESULT_LIMIT and start < end:
            middle = start + (end - start) / 2

            return [
                *self.pull_requests(login, start, middle),
                *self.pull_requests(login, middle + datetime.timedelta(days=1), end),
            ]

        collected = list(page.pull_requests)

        while page.cursor is not None:
            page = self.search_page(login, start, end, cursor=page.cursor)
            collected.extend(page.pull_requests)

        return collected

    def owned_repositories(self, login: str) -> list[ContributionRepository]:
        repositories: list[ContributionRepository] = []
        cursor: str | None = None

        for _ in range(OWNED_REPOSITORY_PAGES):
            data = self.tolerant_graphql(
                OWNED_REPOSITORIES_QUERY, {"login": login, "cursor": cursor}
            )
            user = data.get("user")

            if user is None:
                return repositories

            connection = user["repositories"]
            repositories.extend(build_contribution_repository(node) for node in connection["nodes"])

            if not connection["pageInfo"]["hasNextPage"]:
                return repositories

            cursor = connection["pageInfo"]["endCursor"]

        logger.warning("Owned repositories of %s exceed %s pages", login, OWNED_REPOSITORY_PAGES)

        return repositories

    def hydrate(self, node_ids: list[str]) -> dict[str, ContributionRepository]:
        repositories: dict[str, ContributionRepository] = {}

        for start in range(0, len(node_ids), HYDRATION_BATCH_SIZE):
            data = self.tolerant_graphql(
                HYDRATION_QUERY, {"ids": node_ids[start : start + HYDRATION_BATCH_SIZE]}
            )

            for node in data.get("nodes") or []:
                if node:
                    repository = build_contribution_repository(node)
                    repositories[repository.node_id] = repository

        return repositories
