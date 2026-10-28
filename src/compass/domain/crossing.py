from compass.domain.classification import tooling_key
from compass.domain.identity import (
    ContributorIdentity,
    Crossing,
    EvidenceSource,
    MeaningRelation,
    ProjectIdentity,
    Stance,
    ToolingRelation,
)
from compass.domain.vocabulary import Vocabulary

LANGUAGE_SOURCES = frozenset({EvidenceSource.LANGUAGE_BYTES, EvidenceSource.PRIMARY_LANGUAGE})


def dominant_language(project: ProjectIdentity) -> str | None:
    languages = [item.value for item in project.tooling if item.source in LANGUAGE_SOURCES]

    return languages[0] if languages else project.primary_language


def vetoes(
    project: ProjectIdentity,
    contributor: ContributorIdentity,
    vocabulary: Vocabulary,
) -> list[str]:
    stances = contributor.stances
    keys = [
        tooling_key(item.value, vocabulary)
        for item in project.tooling
        if not vocabulary.is_language(item.value)
    ]

    if project.primary_language is not None:
        keys.insert(0, tooling_key(project.primary_language, vocabulary))

    return [key for key in dict.fromkeys(keys) if stances.get(key) is Stance.AVOIDED]


def tooling_relation(
    project: ProjectIdentity,
    contributor: ContributorIdentity,
    vocabulary: Vocabulary,
) -> tuple[ToolingRelation, list[str]]:
    stances = contributor.stances
    avoided = vetoes(project, contributor, vocabulary)

    if avoided:
        return ToolingRelation.AVOIDED, avoided

    keys = [tooling_key(item.value, vocabulary) for item in project.tooling]
    preferred = [key for key in keys if stances.get(key) is Stance.PREFERRED]

    if preferred:
        return ToolingRelation.PREFERRED, preferred

    language = dominant_language(project)

    if language is None:
        return ToolingRelation.UNFAMILIAR, []

    dominant = tooling_key(language, vocabulary)

    if dominant in contributor.tooling_history:
        shared = [key for key in keys if key != dominant and key in contributor.tooling_history]

        return ToolingRelation.KNOWN, [dominant, *shared]

    if stances.get(dominant) is Stance.OPEN:
        return ToolingRelation.OPEN, [dominant]

    return ToolingRelation.UNFAMILIAR, [dominant]


def meaning_relation(
    project: ProjectIdentity,
    contributor: ContributorIdentity,
    vocabulary: Vocabulary,
) -> tuple[MeaningRelation, list[str]]:
    names = [item.value for item in project.meaning]

    declared_families = {vocabulary.family(name) for name in contributor.declared_meaning}
    declared = [name for name in names if vocabulary.family(name) in declared_families]

    if declared:
        return MeaningRelation.DECLARED, declared

    known_synonyms = {vocabulary.synonym(name) for name in contributor.meaning_history}
    known = [name for name in names if vocabulary.synonym(name) in known_synonyms]

    if known:
        return MeaningRelation.KNOWN, known

    reference = contributor.declared_meaning | contributor.meaning_history.keys()
    reference_families = {vocabulary.family(name) for name in reference}
    adjacent = [
        name
        for name in names
        if vocabulary.family(name) in reference_families or vocabulary.neighbours(name) & reference
    ]

    if adjacent:
        return MeaningRelation.ADJACENT, adjacent

    return MeaningRelation.NEW, []


def cross(
    project: ProjectIdentity,
    contributor: ContributorIdentity,
    vocabulary: Vocabulary,
) -> Crossing:
    tooling, tooling_terms = tooling_relation(project, contributor, vocabulary)
    meaning, meaning_terms = meaning_relation(project, contributor, vocabulary)

    return Crossing(
        tooling=tooling,
        meaning=meaning,
        deciding_terms=[*tooling_terms, *meaning_terms],
    )
