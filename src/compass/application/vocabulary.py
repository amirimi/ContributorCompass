import dataclasses
import datetime
import logging
from collections import Counter

from compass.adapters import TopicCache, VocabularyCache
from compass.adapters.explore import ExploreSource
from compass.adapters.linguist import LinguistSource
from compass.domain import (
    ContributorIdentity,
    EvidenceSource,
    ProjectIdentity,
    TopicProject,
    Vocabulary,
    VocabularySources,
    classify,
    cross,
)

logger = logging.getLogger(__name__)

REPORT_LIMIT = 40
TOOLING_REPORT_LIMIT = 20
TAG_SOURCES = frozenset({EvidenceSource.TAG, EvidenceSource.ALIAS, EvidenceSource.SYNONYM})


@dataclasses.dataclass(frozen=True)
class VocabularyReport:
    explore_terms: int
    linguist_terms: int
    projects: int
    clustered_tags: int
    inherited_tooling: int
    projects_with_tooling_tags: int
    meaning_relations: list[tuple[str, int]]
    top_tooling_tags: list[tuple[str, int]]
    unresolved_tags: int
    top_unresolved: list[tuple[str, int]]


def refresh_sources(
    explore: ExploreSource,
    linguist: LinguistSource,
    cache: VocabularyCache,
) -> VocabularySources:
    sources = VocabularySources(explore=explore.fetch_terms(), linguist=linguist.fetch_terms())
    cache.save(sources)

    logger.info(
        "Saved %s explore topics and %s Linguist languages",
        len(sources.explore),
        len(sources.linguist),
    )

    return sources


def load_fresh_sources(
    cache: VocabularyCache,
    stale_after: datetime.timedelta,
) -> VocabularySources | None:
    sources = cache.load()

    if sources is None or sources.is_stale(stale_after):
        return None

    return sources


def cached_projects(cache: TopicCache) -> list[TopicProject]:
    projects: dict[str, TopicProject] = {}

    for topic in cache.cached_topics():
        collection = cache.load_projects(topic)

        if collection is None:
            continue

        for project in collection.projects:
            projects.setdefault(project.url, project)

    return list(projects.values())


def tooling_tags(identity: ProjectIdentity, vocabulary: Vocabulary) -> list[str]:
    return [
        item.value
        for item in identity.tooling
        if item.source in TAG_SOURCES and not vocabulary.is_language(item.value)
    ]


def report_vocabulary(
    sources: VocabularySources,
    vocabulary: Vocabulary,
    projects: list[TopicProject],
    contributor: ContributorIdentity | None,
) -> VocabularyReport:
    unresolved: Counter[str] = Counter()
    tooling: Counter[str] = Counter()
    relations: Counter[str] = Counter()
    with_tooling_tags = 0

    for project in projects:
        identity = classify(project, vocabulary)
        tags = tooling_tags(identity, vocabulary)
        unresolved.update(identity.unresolved)
        tooling.update(tags)
        with_tooling_tags += bool(tags)

        if contributor is not None:
            relations[cross(identity, contributor, vocabulary).meaning] += 1

    return VocabularyReport(
        explore_terms=len(sources.explore),
        linguist_terms=len(sources.linguist),
        projects=len(projects),
        clustered_tags=len(vocabulary.synonyms),
        inherited_tooling=len(vocabulary.inherited),
        projects_with_tooling_tags=with_tooling_tags,
        meaning_relations=relations.most_common(),
        top_tooling_tags=tooling.most_common(TOOLING_REPORT_LIMIT),
        unresolved_tags=len(unresolved),
        top_unresolved=unresolved.most_common(REPORT_LIMIT),
    )
