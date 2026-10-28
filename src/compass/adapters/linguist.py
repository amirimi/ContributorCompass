from typing import Any

import httpx
import yaml

from compass.domain import Axis, Term, TermSource

LINGUIST_LANGUAGES_URL = (
    "https://raw.githubusercontent.com/github-linguist/linguist/main/lib/linguist/languages.yml"
)
TOOLING_TYPES = frozenset({"programming", "markup"})


def parse_languages(text: str) -> list[Term]:
    languages: dict[str, dict[str, Any]] = yaml.safe_load(text)

    return [
        Term(
            name=name,
            axis=Axis.TOOLING,
            aliases=frozenset(str(alias) for alias in fields.get("aliases", [])),
            source=TermSource.LINGUIST,
        )
        for name, fields in languages.items()
        if fields.get("type") in TOOLING_TYPES
    ]


class LinguistSource:
    def __init__(self, timeout: float = 30) -> None:
        self.timeout = timeout

    def fetch_terms(self) -> list[Term]:
        response = httpx.get(LINGUIST_LANGUAGES_URL, timeout=self.timeout, follow_redirects=True)
        response.raise_for_status()

        return parse_languages(response.text)
