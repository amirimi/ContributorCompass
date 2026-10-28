from enum import StrEnum

from compass.domain.models import DomainModel


class EvidenceSource(StrEnum):
    TAG = "tag"
    ALIAS = "alias"
    UNCURATED = "uncurated"
    SYNONYM = "synonym"
    LANGUAGE_BYTES = "language_bytes"
    PRIMARY_LANGUAGE = "primary_language"


class Evidence(DomainModel):
    value: str
    source: EvidenceSource
    raw: str


class ProjectIdentity(DomainModel):
    url: str
    primary_language: str | None
    tooling: list[Evidence]
    meaning: list[Evidence]
    unresolved: list[str]


class Stance(StrEnum):
    PREFERRED = "preferred"
    OPEN = "open"
    AVOIDED = "avoided"


class MeaningPreferences(DomainModel):
    declared: tuple[str, ...] = ()


class ToolingPreferences(DomainModel):
    preferred: tuple[str, ...] = ()
    open: tuple[str, ...] = ()
    avoided: tuple[str, ...] = ()


class Preferences(DomainModel):
    meaning: MeaningPreferences = MeaningPreferences()
    tooling: ToolingPreferences = ToolingPreferences()


class ContributorIdentity(DomainModel):
    tooling_history: dict[str, int]
    meaning_history: dict[str, int]
    declared_meaning: frozenset[str]
    stances: dict[str, Stance]


class ToolingRelation(StrEnum):
    AVOIDED = "avoided"
    PREFERRED = "preferred"
    KNOWN = "known"
    OPEN = "open"
    UNFAMILIAR = "unfamiliar"


class MeaningRelation(StrEnum):
    DECLARED = "declared"
    KNOWN = "known"
    ADJACENT = "adjacent"
    NEW = "new"


class Crossing(DomainModel):
    tooling: ToolingRelation
    meaning: MeaningRelation
    deciding_terms: list[str]
