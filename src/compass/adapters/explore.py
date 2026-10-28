import logging
import re
from typing import Any

import yaml

from compass.adapters.github import GRAPHQL_FAILURES, GitHubClient
from compass.domain import Axis, Term, TermSource, normalize_tag

logger = logging.getLogger(__name__)

EXPLORE_OWNER = "github"
EXPLORE_NAME = "explore"
EXPLORE_TOPICS = "main:topics"
TOPIC_BATCH_SIZE = 100
TOPIC_MIN_BATCH_SIZE = 25

FRONT_MATTER = re.compile(r"\A---\s*\n(.*?)\n---", re.DOTALL)

TOPIC_TREE_QUERY = """
query ($owner: String!, $name: String!, $expression: String!) {
  repository(owner: $owner, name: $name) {
    object(expression: $expression) {
      ... on Tree {
        entries {
          name
          type
        }
      }
    }
  }
}
"""


def topic_batch_query(size: int) -> str:
    parameters = ", ".join(f"$e{index}: String!" for index in range(size))
    fields = "\n".join(
        f"    t{index}: object(expression: $e{index}) {{ ... on Blob {{ text }} }}"
        for index in range(size)
    )

    return (
        f"query ($owner: String!, $name: String!, {parameters}) {{\n"
        f"  repository(owner: $owner, name: $name) {{\n{fields}\n  }}\n}}"
    )


def topic_page_expression(directory: str) -> str:
    return f"{EXPLORE_TOPICS}/{directory}/index.md"


def split_list(value: Any) -> frozenset[str]:
    if value is None:
        return frozenset()

    items = value if isinstance(value, list) else str(value).split(",")

    return frozenset(normalize_tag(str(item)) for item in items if str(item).strip())


def parse_topic_page(directory: str, text: str) -> Term | None:
    match = FRONT_MATTER.match(text)

    if match is None:
        return None

    try:
        fields = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        logger.warning("Skipping explore topic %s with unreadable front matter", directory)
        return None

    if not isinstance(fields, dict):
        return None

    return Term(
        name=normalize_tag(str(fields.get("topic") or directory)),
        axis=Axis.MEANING,
        aliases=split_list(fields.get("aliases")),
        related=split_list(fields.get("related")),
        source=TermSource.EXPLORE,
    )


class ExploreSource:
    def __init__(self, github: GitHubClient) -> None:
        self.github = github

    def topic_directories(self) -> list[str]:
        response: Any = self.github.graphql(
            TOPIC_TREE_QUERY,
            {"owner": EXPLORE_OWNER, "name": EXPLORE_NAME, "expression": EXPLORE_TOPICS},
        )
        entries = response["repository"]["object"]["entries"]

        return [entry["name"] for entry in entries if entry["type"] == "tree"]

    def fetch_page_batch(self, directories: list[str]) -> dict[str, str]:
        response: Any = self.github.graphql(
            topic_batch_query(len(directories)),
            {
                "owner": EXPLORE_OWNER,
                "name": EXPLORE_NAME,
                **{
                    f"e{index}": topic_page_expression(directory)
                    for index, directory in enumerate(directories)
                },
            },
        )
        repository = response["repository"]

        return {
            directory: repository[f"t{index}"]["text"]
            for index, directory in enumerate(directories)
            if repository[f"t{index}"]
        }

    def fetch_pages(self, directories: list[str]) -> dict[str, str]:
        try:
            return self.fetch_page_batch(directories)
        except GRAPHQL_FAILURES as exc:
            if len(directories) <= TOPIC_MIN_BATCH_SIZE:
                logger.warning(
                    "Skipping %s explore topics after a failed batch: %s", len(directories), exc
                )
                return {}

        half = len(directories) // 2

        return {**self.fetch_pages(directories[:half]), **self.fetch_pages(directories[half:])}

    def fetch_terms(self) -> list[Term]:
        directories = self.topic_directories()
        pages: dict[str, str] = {}

        for start in range(0, len(directories), TOPIC_BATCH_SIZE):
            pages.update(self.fetch_pages(directories[start : start + TOPIC_BATCH_SIZE]))

        terms = [parse_topic_page(directory, text) for directory, text in pages.items()]

        return [term for term in terms if term is not None]
