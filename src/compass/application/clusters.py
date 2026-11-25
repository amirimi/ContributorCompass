import dataclasses
import logging
from collections import Counter
from collections.abc import Iterable, Sequence
from typing import Protocol

import numpy as np
import numpy.typing as npt

from compass.adapters import ClusterCache
from compass.adapters.clustering import cut_tree, mix_context, nonzero_rows
from compass.domain import (
    Axis,
    Lexicon,
    PersonalProfileFile,
    Preferences,
    TagClusters,
    TopicProject,
    Vocabulary,
    VocabularySources,
    build_vocabulary,
    group_members,
    inherit_tooling,
    label_groups,
    normalize_tag,
)

logger = logging.getLogger(__name__)

MIN_OCCURRENCES = 2
MAX_TAGS = 15_000
SYNONYM_CUT = 0.2
FAMILY_CUT = 0.4


class Embedder(Protocol):
    def encode(self, texts: Sequence[str]) -> npt.NDArray[np.float64]: ...


class TagBudgetExceeded(RuntimeError):
    pass


@dataclasses.dataclass(frozen=True)
class EmbeddingModel:
    name: str
    revision: str
    embedder: Embedder


@dataclasses.dataclass(frozen=True)
class ClusterReport:
    tags: int
    synonym_groups: int
    synonym_singletons: int
    families: int
    family_singletons: int
    inherited_tooling: int


def project_tags(projects: Iterable[TopicProject], vocabulary: Vocabulary) -> list[list[str]]:
    return [
        sorted(
            {
                token
                for token in (normalize_tag(tag) for tag in project.topics)
                if token not in vocabulary.meta
            }
        )
        for project in projects
    ]


def anchor_tags(
    sources: VocabularySources,
    lexicon: Lexicon,
    profile: PersonalProfileFile | None,
    preferences: Preferences,
) -> set[str]:
    profile_tags = [topic for topic, _ in profile.topics_frequency] if profile else []
    names = [
        *(term.name for term in sources.explore),
        *(term.name for term in lexicon.tooling_terms()),
        *lexicon.both_axes,
        *profile_tags,
        *preferences.meaning.declared,
    ]

    return {normalize_tag(name) for name in names}


def select_tags(
    tag_lists: list[list[str]],
    anchors: set[str],
    vocabulary: Vocabulary,
    min_occurrences: int,
) -> list[str]:
    counts = Counter(token for tokens in tag_lists for token in tokens)
    frequent = {token for token, count in counts.items() if count >= min_occurrences}
    selected = sorted(token for token in frequent | anchors if token not in vocabulary.meta)

    if len(selected) > MAX_TAGS:
        raise TagBudgetExceeded(f"{len(selected)} tags exceed the clustering budget of {MAX_TAGS}")

    return selected


def carries_meaning(tag: str, vocabulary: Vocabulary) -> bool:
    resolution = vocabulary.resolve(tag)

    return resolution.uncurated or bool(resolution.on(Axis.MEANING))


def embed_tags(
    tags: list[str],
    tag_lists: list[list[str]],
    embedder: Embedder,
    vocabulary: Vocabulary,
) -> tuple[list[str], npt.NDArray[np.float64]]:
    index = {tag: position for position, tag in enumerate(tags)}
    names = embedder.encode([tag.replace("-", " ") for tag in tags])
    members = [[index[token] for token in tokens if token in index] for tokens in tag_lists]
    contributes = [carries_meaning(tag, vocabulary) for tag in tags]
    vectors = mix_context(names, members, contributes)
    keep = nonzero_rows(vectors)

    return [tag for tag, kept in zip(tags, keep.tolist(), strict=True) if kept], vectors[keep]


def build_clusters(
    projects: list[TopicProject],
    sources: VocabularySources,
    lexicon: Lexicon,
    profile: PersonalProfileFile | None,
    preferences: Preferences,
    model: EmbeddingModel,
    min_occurrences: int = MIN_OCCURRENCES,
) -> TagClusters:
    vocabulary = build_vocabulary(sources, lexicon)
    tag_lists = project_tags(projects, vocabulary)
    selected = select_tags(
        tag_lists,
        anchor_tags(sources, lexicon, profile, preferences),
        vocabulary,
        min_occurrences,
    )
    tags, vectors = embed_tags(selected, tag_lists, model.embedder, vocabulary)
    synonym_ids, family_ids = cut_tree(vectors, [SYNONYM_CUT, FAMILY_CUT])
    counts = Counter(token for tokens in tag_lists for token in tokens)
    claimed = frozenset(vocabulary.claims)
    synonyms = label_groups(tags, synonym_ids, counts, claimed)

    return TagClusters(
        model=model.name,
        revision=model.revision,
        synonym_cut=SYNONYM_CUT,
        family_cut=FAMILY_CUT,
        synonyms=synonyms,
        families=label_groups(tags, family_ids, counts, claimed),
        tooling_parents=inherit_tooling(
            synonyms,
            counts,
            is_tooling=lambda tag: bool(vocabulary.resolve(tag).on(Axis.TOOLING)),
            is_claimed=lambda tag: tag in claimed,
        ),
    )


def build_clusters_within_budget(
    projects: list[TopicProject],
    sources: VocabularySources,
    lexicon: Lexicon,
    model: EmbeddingModel,
) -> tuple[TagClusters, int]:
    min_occurrences = MIN_OCCURRENCES

    while True:
        try:
            clusters = build_clusters(
                projects, sources, lexicon, None, Preferences(), model, min_occurrences
            )
        except TagBudgetExceeded as exc:
            logger.info("Raising min_occurrences above %s because %s", min_occurrences, exc)
            min_occurrences += 1
            continue

        return clusters, min_occurrences


def summarize_clusters(clusters: TagClusters) -> ClusterReport:
    synonym_groups = group_members(clusters.synonyms).values()
    families = group_members(clusters.families).values()

    return ClusterReport(
        tags=len(clusters.synonyms),
        synonym_groups=len(synonym_groups),
        synonym_singletons=sum(len(members) == 1 for members in synonym_groups),
        families=len(families),
        family_singletons=sum(len(members) == 1 for members in families),
        inherited_tooling=len(clusters.tooling_parents),
    )


def refresh_clusters(
    projects: list[TopicProject],
    sources: VocabularySources,
    lexicon: Lexicon,
    profile: PersonalProfileFile | None,
    preferences: Preferences,
    model: EmbeddingModel,
    cache: ClusterCache,
) -> ClusterReport:
    clusters = build_clusters(projects, sources, lexicon, profile, preferences, model)
    cache.save(clusters)
    report = summarize_clusters(clusters)

    logger.info(
        "Saved %s tags in %s synonym groups and %s families",
        report.tags,
        report.synonym_groups,
        report.families,
    )

    return report
