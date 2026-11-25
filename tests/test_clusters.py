from collections.abc import Sequence
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pytest

from compass.adapters import ClusterCache, load_lexicon
from compass.adapters.clustering import cut_tree, mix_context
from compass.application import clusters as clustering
from compass.application.clusters import (
    MIN_OCCURRENCES,
    EmbeddingModel,
    TagBudgetExceeded,
    build_clusters,
    refresh_clusters,
    select_tags,
)
from compass.domain import (
    PersonalProfileFile,
    Preferences,
    TagClusters,
    TopicProject,
    inherit_tooling,
    label_groups,
)
from tests.vocabulary_fixtures import SOURCES, make_vocabulary

SHARED_AXES = {"cli": 0, "cli tools": 0, "emulator": 1, "nes": 1}


class FakeEmbedder:
    def encode(self, texts: Sequence[str]) -> npt.NDArray[np.float64]:
        vectors = np.zeros((len(texts), len(texts) + len(SHARED_AXES)))

        for row, text in enumerate(texts):
            vectors[row, SHARED_AXES.get(text, len(SHARED_AXES) + row)] = 1.0

        return vectors


def project(name: str, topics: list[str]) -> TopicProject:
    return TopicProject(
        owner="owner",
        name=name,
        url=f"https://github.com/owner/{name}",
        topics=topics,
    )


PROJECTS = [
    project("a", ["cli"]),
    project("b", ["cli-tools"]),
    project("c", ["cli-tools"]),
    project("d", ["emulator", "nes", "hacktoberfest"]),
    project("e", ["emulator", "nes"]),
]

MODEL = EmbeddingModel(name="fake", revision="fake", embedder=FakeEmbedder())


def build() -> TagClusters:
    return build_clusters(
        projects=PROJECTS,
        sources=SOURCES,
        lexicon=load_lexicon(),
        profile=PersonalProfileFile(
            github_handle="octocat",
            topics_frequency=[("own-topic", 1)],
            languages_frequency=[("Python", 1)],
        ),
        preferences=Preferences(),
        model=MODEL,
    )


def test_labels_prefer_claimed_members_then_frequency() -> None:
    labels = label_groups(
        ["cli-tools", "cli", "zeta", "alpha"],
        [1, 1, 2, 2],
        counts={"cli-tools": 9, "cli": 1, "zeta": 5, "alpha": 5},
        curated=frozenset({"cli"}),
    )

    assert labels == {"cli-tools": "cli", "cli": "cli", "zeta": "alpha", "alpha": "alpha"}


def test_unclaimed_members_inherit_the_most_frequent_tooling_member() -> None:
    parents = inherit_tooling(
        {"cli-tools": "cli", "cli": "cli", "tui": "cli", "emulator": "cli"},
        counts={"cli": 5, "tui": 2},
        is_tooling=lambda tag: tag in {"cli", "tui"},
        is_claimed=lambda tag: tag in {"cli", "tui", "emulator"},
    )

    assert parents == {"cli-tools": "cli"}


def test_context_pulls_tags_that_share_projects_together() -> None:
    names = np.eye(3)
    mixed = mix_context(names, [[0, 2], [1, 2]], contributes=[True, True, True])

    assert mixed[0] @ mixed[1] > names[0] @ names[1]


def test_non_contributing_tags_add_no_context() -> None:
    names = np.eye(3)
    mixed = mix_context(names, [[0, 2], [1, 2]], contributes=[True, True, False])

    assert mixed[0] @ mixed[1] == pytest.approx(0.0)


def test_two_cuts_split_one_tree_at_two_heights() -> None:
    vectors = np.array([[1.0, 0.0], [0.99, 0.14], [0.0, 1.0], [0.14, 0.99]])
    tight, loose = cut_tree(vectors, [0.05, 1.5])

    assert tight[0] == tight[1] != tight[2] == tight[3]
    assert len(set(loose)) == 1


def test_build_groups_variants_and_inherits_tooling() -> None:
    clusters = build()

    assert clusters.synonyms["cli-tools"] == clusters.synonyms["cli"]
    assert clusters.synonyms["nes"] == clusters.synonyms["emulator"]
    assert clusters.tooling_parents == {"cli-tools": "cli"}
    assert "hacktoberfest" not in clusters.synonyms
    assert "own-topic" in clusters.synonyms


def test_built_clusters_feed_the_vocabulary() -> None:
    vocabulary = make_vocabulary(build())

    assert [term.name for term in vocabulary.resolve("cli-tools").terms] == ["cli"]


def test_tag_budget_stops_the_build(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clustering, "MAX_TAGS", 1)

    with pytest.raises(TagBudgetExceeded):
        select_tags([["a", "b"], ["a", "b"]], set(), make_vocabulary(), MIN_OCCURRENCES)


def test_refresh_saves_the_file_and_reports_counts(tmp_path: Path) -> None:
    cache = ClusterCache(file_path=tmp_path / "clusters.json")
    report = refresh_clusters(
        projects=PROJECTS,
        sources=SOURCES,
        lexicon=load_lexicon(),
        profile=None,
        preferences=Preferences(),
        model=MODEL,
        cache=cache,
    )
    saved = cache.load()

    assert saved is not None
    assert report.tags == len(saved.synonyms)
    assert report.inherited_tooling == 1
