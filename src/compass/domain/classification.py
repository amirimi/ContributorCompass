from collections import Counter
from collections.abc import Sequence

from compass.domain.identity import (
    ContributorIdentity,
    Evidence,
    EvidenceSource,
    Preferences,
    ProjectIdentity,
    Stance,
)
from compass.domain.models import PersonalProfileFile, TopicProject
from compass.domain.vocabulary import Axis, Resolution, Term, Vocabulary, normalize_tag

TOOLING_SHARE = 0.10


def tooling_key(name: str, vocabulary: Vocabulary) -> str:
    terms = vocabulary.resolve(name).on(Axis.TOOLING)

    return normalize_tag(terms[0].name) if terms else normalize_tag(name)


def term_source(resolution: Resolution, term: Term) -> EvidenceSource:
    if resolution.inherited:
        return EvidenceSource.SYNONYM

    if normalize_tag(term.name) == resolution.token:
        return EvidenceSource.TAG

    return EvidenceSource.ALIAS


def first_per_value(evidence: list[Evidence]) -> list[Evidence]:
    kept: dict[str, Evidence] = {}

    for item in evidence:
        kept.setdefault(normalize_tag(item.value), item)

    return list(kept.values())


def tooling_from_bytes(project: TopicProject) -> list[Evidence]:
    total = sum(project.language_bytes.values())

    if total == 0:
        if project.language is None:
            return []

        return [
            Evidence(
                value=project.language,
                source=EvidenceSource.PRIMARY_LANGUAGE,
                raw=project.language,
            )
        ]

    ranked = sorted(project.language_bytes.items(), key=lambda item: -item[1])

    return [
        Evidence(
            value=language,
            source=EvidenceSource.LANGUAGE_BYTES,
            raw=f"{language} {size / total:.0%}",
        )
        for language, size in ranked
        if size / total >= TOOLING_SHARE
    ]


def tooling_from_tags(tags: Sequence[str], vocabulary: Vocabulary) -> list[Evidence]:
    evidence: list[Evidence] = []

    for tag in tags:
        resolution = vocabulary.resolve(tag)

        evidence.extend(
            Evidence(value=term.name, source=term_source(resolution, term), raw=tag)
            for term in resolution.on(Axis.TOOLING)
        )

    return evidence


def meaning_from_tags(
    tags: Sequence[str],
    vocabulary: Vocabulary,
) -> tuple[list[Evidence], list[str]]:
    evidence: list[Evidence] = []
    unresolved: list[str] = []

    for tag in tags:
        resolution = vocabulary.resolve(tag)

        evidence.extend(
            Evidence(value=term.name, source=term_source(resolution, term), raw=tag)
            for term in resolution.on(Axis.MEANING)
        )

        if not resolution.uncurated:
            continue

        evidence.append(Evidence(value=resolution.token, source=EvidenceSource.UNCURATED, raw=tag))

        if not vocabulary.clustered(resolution.token):
            unresolved.append(resolution.token)

    return first_per_value(evidence), unresolved


def classify(project: TopicProject, vocabulary: Vocabulary) -> ProjectIdentity:
    meaning, unresolved = meaning_from_tags(project.topics, vocabulary)

    return ProjectIdentity(
        url=project.url,
        primary_language=project.language,
        tooling=first_per_value(
            [*tooling_from_bytes(project), *tooling_from_tags(project.topics, vocabulary)]
        ),
        meaning=meaning,
        unresolved=unresolved,
    )


def meaning_values(tags: Sequence[str], vocabulary: Vocabulary) -> list[str]:
    evidence, _ = meaning_from_tags(tags, vocabulary)

    return [item.value for item in evidence]


def describe_contributor(
    profile: PersonalProfileFile,
    preferences: Preferences,
    vocabulary: Vocabulary,
) -> ContributorIdentity:
    tooling_history: Counter[str] = Counter()
    meaning_history: Counter[str] = Counter()

    for language, count in profile.languages_frequency:
        tooling_history[tooling_key(language, vocabulary)] += count

    for topic, count in profile.topics_frequency:
        for item in tooling_from_tags([topic], vocabulary):
            tooling_history[tooling_key(item.value, vocabulary)] += count

        for name in meaning_values([topic], vocabulary):
            meaning_history[name] += count

    stances: dict[str, Stance] = {}
    tooling = preferences.tooling

    for stance, names in [
        (Stance.OPEN, tooling.open),
        (Stance.PREFERRED, tooling.preferred),
        (Stance.AVOIDED, tooling.avoided),
    ]:
        for name in names:
            stances[tooling_key(name, vocabulary)] = stance

    return ContributorIdentity(
        tooling_history=dict(tooling_history),
        meaning_history=dict(meaning_history),
        declared_meaning=frozenset(meaning_values(preferences.meaning.declared, vocabulary)),
        stances=stances,
    )
