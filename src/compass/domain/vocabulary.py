import dataclasses
import re
from collections import defaultdict
from enum import StrEnum

import pydantic

from compass.domain.clusters import TagClusters
from compass.domain.models import CacheFile, DomainModel

TAG_SEPARATORS = re.compile(r"[\s_]+")
PLURAL_MIN_LENGTH = 5
SEGMENT_STEM_LENGTH = 3
SPELLING_PREFIX = 5


def normalize_tag(raw: str) -> str:
    return TAG_SEPARATORS.sub("-", raw.strip().lower())


def singular_segments(tag: str) -> list[str]:
    return [
        segment[:-1] if len(segment) > SEGMENT_STEM_LENGTH and segment.endswith("s") else segment
        for segment in normalize_tag(tag).split("-")
    ]


def unshared_segments(
    first: list[str],
    second: list[str],
) -> tuple[list[str], list[str]] | None:
    shared = 0

    while first and second and first[0] == second[0]:
        first, second, shared = first[1:], second[1:], shared + 1

    while first and second and first[-1] == second[-1]:
        first, second, shared = first[:-1], second[:-1], shared + 1

    return (first, second) if shared else None


def spelling_variants(first: str, second: str) -> bool:
    return (
        first.startswith(second)
        or second.startswith(first)
        or first[:SPELLING_PREFIX] == second[:SPELLING_PREFIX]
    )


def sibling_compounds(first: str, second: str) -> bool:
    left, right = singular_segments(first), singular_segments(second)

    if len(left) < 2 or len(right) < 2:
        return False

    remainders = unshared_segments(left, right)

    if remainders is None or not all(remainders):
        return False

    return not spelling_variants("".join(remainders[0]), "".join(remainders[1]))


class Axis(StrEnum):
    TOOLING = "tooling"
    MEANING = "meaning"


class TermSource(StrEnum):
    EXPLORE = "explore"
    LINGUIST = "linguist"
    LEXICON = "lexicon"


class Term(DomainModel):
    name: str
    axis: Axis
    aliases: frozenset[str] = frozenset()
    related: frozenset[str] = frozenset()
    source: TermSource

    def tokens(self) -> set[str]:
        return {normalize_tag(self.name), *(normalize_tag(alias) for alias in self.aliases)}


class VocabularySources(CacheFile):
    explore: list[Term]
    linguist: list[Term]


class Lexicon(DomainModel):
    meta: tuple[str, ...] = ()
    reclaim_from_linguist: tuple[str, ...] = ()
    both_axes: tuple[str, ...] = ()
    tooling: dict[str, dict[str, list[str]]] = pydantic.Field(default_factory=dict)

    def tooling_terms(self) -> list[Term]:
        return [
            Term(
                name=name,
                axis=Axis.TOOLING,
                aliases=frozenset(aliases),
                source=TermSource.LEXICON,
            )
            for table in self.tooling.values()
            for name, aliases in table.items()
        ]


@dataclasses.dataclass(frozen=True)
class Resolution:
    token: str
    terms: tuple[Term, ...] = ()
    meta: bool = False
    inherited: bool = False

    @property
    def uncurated(self) -> bool:
        return not self.terms and not self.meta

    def on(self, axis: Axis) -> list[Term]:
        return [term for term in self.terms if term.axis is axis]


@dataclasses.dataclass(frozen=True)
class Vocabulary:
    claims: dict[str, tuple[Term, ...]]
    meta: frozenset[str]
    adjacency: dict[str, frozenset[str]]
    inherited: dict[str, tuple[Term, ...]]
    synonyms: dict[str, str]
    families: dict[str, str]

    def resolve(self, raw: str) -> Resolution:
        token = normalize_tag(raw)

        if token in self.meta:
            return Resolution(token=token, meta=True)

        if token in self.inherited:
            return Resolution(token=token, terms=self.inherited[token], inherited=True)

        return Resolution(token=token, terms=self.claims.get(token) or self.singular_claim(token))

    def singular_claim(self, token: str) -> tuple[Term, ...]:
        if len(token) < PLURAL_MIN_LENGTH or not token.endswith("s"):
            return ()

        terms = self.claims.get(token[:-1], ())

        if any(term.source is TermSource.LINGUIST for term in terms):
            return ()

        return terms

    def neighbours(self, meaning: str) -> frozenset[str]:
        return self.adjacency.get(meaning, frozenset())

    def is_language(self, name: str) -> bool:
        return any(
            term.source is TermSource.LINGUIST for term in self.resolve(name).on(Axis.TOOLING)
        )

    def clustered(self, name: str) -> bool:
        return normalize_tag(name) in self.synonyms

    def synonym(self, name: str) -> str:
        token = normalize_tag(name)

        return self.synonyms.get(token, token)

    def family(self, name: str) -> str:
        token = normalize_tag(name)

        return self.families.get(token, token)


def claim_tokens(
    ranked_terms: list[list[Term]],
    reclaimed: frozenset[str],
) -> dict[str, tuple[Term, ...]]:
    claims: dict[str, list[Term]] = {}

    for terms in ranked_terms:
        claimed_above = set(claims)

        for term in terms:
            for token in term.tokens():
                if token in claimed_above:
                    continue

                if term.source is TermSource.LINGUIST and token in reclaimed:
                    continue

                claims.setdefault(token, []).append(term)

    return {token: tuple(terms) for token, terms in claims.items()}


def fold_tooling_topics(
    explore: list[Term],
    tooling_ranks: list[list[Term]],
    reclaimed: frozenset[str],
) -> list[Term]:
    tooling: dict[str, Term] = {}

    for terms in tooling_ranks:
        for term in terms:
            for token in term.tokens():
                if term.source is TermSource.LINGUIST and token in reclaimed:
                    continue

                tooling.setdefault(token, term)

    folded: list[Term] = []

    for term in explore:
        claimed = tooling.get(normalize_tag(term.name))
        folded.append(
            term if claimed is None else claimed.model_copy(update={"aliases": term.aliases})
        )

    return folded


def meaning_names(claims: dict[str, tuple[Term, ...]], token: str) -> list[str]:
    return [term.name for term in claims.get(token, ()) if term.axis is Axis.MEANING]


def lexicon_term(name: str, axis: Axis) -> Term:
    return Term(name=name, axis=axis, source=TermSource.LEXICON)


def place_on_both_axes(
    claims: dict[str, tuple[Term, ...]],
    names: frozenset[str],
) -> dict[str, tuple[Term, ...]]:
    placed = dict(claims)

    for name in names:
        if not meaning_names(placed, name):
            placed[name] = (*placed.get(name, ()), lexicon_term(name, Axis.MEANING))

    for token, terms in list(placed.items()):
        tooling = {term.name for term in terms if term.axis is Axis.TOOLING}
        missing = [
            name
            for name in meaning_names(placed, token)
            if normalize_tag(name) in names and name not in tooling
        ]

        if missing:
            placed[token] = (*terms, *(lexicon_term(name, Axis.TOOLING) for name in missing))

    return placed


def outward_links(
    claims: dict[str, tuple[Term, ...]],
    explore: list[Term],
) -> dict[str, frozenset[str]]:
    links: defaultdict[str, set[str]] = defaultdict(set)

    for term in explore:
        for source in meaning_names(claims, normalize_tag(term.name)):
            links[source].update(
                target
                for related in term.related
                for target in meaning_names(claims, normalize_tag(related))
                if target != source
            )

    return {name: frozenset(targets) for name, targets in links.items() if targets}


def inherited_claims(
    claims: dict[str, tuple[Term, ...]],
    meta: frozenset[str],
    tooling_parents: dict[str, str],
) -> dict[str, tuple[Term, ...]]:
    return {
        token: claims[parent]
        for token, parent in tooling_parents.items()
        if token not in claims
        and token not in meta
        and any(term.axis is Axis.TOOLING for term in claims.get(parent, ()))
    }


def build_vocabulary(
    sources: VocabularySources,
    lexicon: Lexicon,
    clusters: TagClusters | None = None,
) -> Vocabulary:
    meta = frozenset(normalize_tag(tag) for tag in lexicon.meta)
    reclaimed = frozenset(normalize_tag(tag) for tag in lexicon.reclaim_from_linguist)
    tooling_ranks = [lexicon.tooling_terms(), sources.linguist]
    ranked = claim_tokens(
        ranked_terms=[
            *tooling_ranks,
            fold_tooling_topics(sources.explore, tooling_ranks, reclaimed),
        ],
        reclaimed=reclaimed,
    )
    claims = place_on_both_axes(
        ranked,
        frozenset(normalize_tag(name) for name in lexicon.both_axes),
    )

    return Vocabulary(
        claims=claims,
        meta=meta,
        adjacency=outward_links(claims, sources.explore),
        inherited=inherited_claims(claims, meta, clusters.tooling_parents) if clusters else {},
        synonyms=clusters.synonyms if clusters else {},
        families=clusters.families if clusters else {},
    )
