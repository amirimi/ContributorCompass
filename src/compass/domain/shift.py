import dataclasses

from compass.domain.classification import classify, describe_contributor, tooling_key
from compass.domain.contributions import Entry, HistorySnapshot
from compass.domain.crossing import cross, dominant_language
from compass.domain.identity import (
    ContributorIdentity,
    Crossing,
    MeaningRelation,
    Preferences,
    ProjectIdentity,
    ToolingRelation,
)
from compass.domain.models import TopicProject
from compass.domain.vocabulary import Vocabulary, normalize_tag

NO_PREFERENCES = Preferences()
NONE_CELL = "none"


@dataclasses.dataclass(frozen=True)
class AxisTokens:
    raw: frozenset[str]
    tooling: frozenset[str]
    meaning: frozenset[str]

    @property
    def grouped(self) -> frozenset[str]:
        return self.tooling | self.meaning


@dataclasses.dataclass(frozen=True)
class ClassifiedRepository:
    project: TopicProject
    identity: ProjectIdentity
    tokens: AxisTokens

    @property
    def has_language(self) -> bool:
        return dominant_language(self.identity) is not None

    @property
    def has_meaning(self) -> bool:
        return bool(self.identity.meaning)

    @property
    def assessable(self) -> bool:
        return self.has_language and self.has_meaning


@dataclasses.dataclass(frozen=True)
class ContributorView:
    identity: ContributorIdentity
    tokens: AxisTokens

    @property
    def ready(self) -> bool:
        return bool(self.tokens.tooling) and bool(self.tokens.meaning)


@dataclasses.dataclass(frozen=True)
class Observation:
    entry: Entry
    repository: ClassifiedRepository
    contributor: ContributorView
    crossing: Crossing

    @property
    def tooling_shift(self) -> bool:
        return self.crossing.tooling is not ToolingRelation.KNOWN

    @property
    def meaning_shift(self) -> bool:
        return self.crossing.meaning is not MeaningRelation.KNOWN

    @property
    def cell(self) -> str:
        return shipped_cell(self.repository, self.crossing)


def jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    union = len(left | right)

    return len(left & right) / union if union else 0.0


def shipped_cell(repository: ClassifiedRepository, crossing: Crossing) -> str:
    if not repository.assessable:
        return NONE_CELL

    return f"{crossing.tooling.value}/{crossing.meaning.value}"


def raw_tokens(topics: list[str], languages: list[str]) -> frozenset[str]:
    return frozenset(normalize_tag(name) for name in [*topics, *languages])


def classify_repository(project: TopicProject, vocabulary: Vocabulary) -> ClassifiedRepository:
    identity = classify(project, vocabulary)
    languages = [project.language] if project.language else []

    return ClassifiedRepository(
        project=project,
        identity=identity,
        tokens=AxisTokens(
            raw=raw_tokens(project.topics, languages),
            tooling=frozenset(tooling_key(item.value, vocabulary) for item in identity.tooling),
            meaning=frozenset(vocabulary.synonym(item.value) for item in identity.meaning),
        ),
    )


def view_contributor(
    login: str,
    snapshot: HistorySnapshot,
    vocabulary: Vocabulary,
) -> ContributorView:
    identity = describe_contributor(snapshot.as_profile(login), NO_PREFERENCES, vocabulary)

    return ContributorView(
        identity=identity,
        tokens=AxisTokens(
            raw=raw_tokens(
                [topic for topic, _ in snapshot.topics],
                [language for language, _ in snapshot.languages],
            ),
            tooling=frozenset(identity.tooling_history),
            meaning=frozenset(vocabulary.synonym(name) for name in identity.meaning_history),
        ),
    )


def observe(
    entry: Entry,
    repository: ClassifiedRepository,
    vocabulary: Vocabulary,
) -> Observation:
    contributor = view_contributor(entry.login, entry.history, vocabulary)

    return Observation(
        entry=entry,
        repository=repository,
        contributor=contributor,
        crossing=cross(repository.identity, contributor.identity, vocabulary),
    )
