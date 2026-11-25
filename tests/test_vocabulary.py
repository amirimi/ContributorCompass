import pytest

from compass.adapters.explore import parse_topic_page
from compass.adapters.linguist import parse_languages
from compass.domain import Axis, TermSource
from compass.domain.vocabulary import sibling_compounds
from tests.vocabulary_fixtures import make_clusters, make_vocabulary

NEOVIM_PAGE = """---
aliases: nvim, neovim-qt, neovim-guis, neovim-clients
display_name: Neovim
related: vim, neovim-plugin, nvimrc
short_description: Vim-fork focused on extensibility and usability.
topic: neovim
---
Neovim is a refactor, and sometimes redactor, in the tradition of Vim.
"""

LANGUAGES_YAML = """
Go:
  type: programming
  aliases:
  - golang
Markdown:
  type: prose
  aliases:
  - md
JSON:
  type: data
HTML:
  type: markup
"""


def names_on(raw: str, axis: Axis) -> list[str]:
    return [term.name for term in make_vocabulary().resolve(raw).on(axis)]


@pytest.mark.parametrize(
    ("raw", "canonical"),
    [("nvim", "neovim"), ("neovim-qt", "neovim"), ("llms", "llm")],
)
def test_aliases_fold_into_one_meaning(raw: str, canonical: str) -> None:
    assert names_on(raw, Axis.MEANING) == [canonical]


@pytest.mark.parametrize(
    ("raw", "language"),
    [
        ("golang", "Go"),
        ("typescript", "TypeScript"),
        ("rust", "Rust"),
        ("python3", "Python"),
        ("rust-lang", "Rust"),
    ],
)
def test_language_tags_land_on_tooling(raw: str, language: str) -> None:
    assert names_on(raw, Axis.TOOLING) == [language]
    assert names_on(raw, Axis.MEANING) == []


@pytest.mark.parametrize(
    ("raw", "form"),
    [
        ("cli", "cli"),
        ("command-line", "cli"),
        ("command-line-interface", "cli"),
        ("docker-image", "docker"),
        ("tui", "tui"),
        ("framework", "framework"),
        ("library", "library"),
        ("neovim-plugin", "neovim-plugin"),
        ("onion-architecture", "onion-architecture"),
    ],
)
def test_forms_land_on_tooling_only(raw: str, form: str) -> None:
    assert names_on(raw, Axis.TOOLING) == [form]
    assert names_on(raw, Axis.MEANING) == []


@pytest.mark.parametrize(
    ("raw", "name"),
    [("neovim", "neovim"), ("nvim", "neovim"), ("llm", "llm"), ("browser", "browser")],
)
def test_terms_on_both_axes_resolve_to_tooling_and_meaning(raw: str, name: str) -> None:
    assert names_on(raw, Axis.TOOLING) == [name]
    assert names_on(raw, Axis.MEANING) == [name]


def test_reclaimed_tags_never_resolve_to_the_linguist_language() -> None:
    vocabulary = make_vocabulary()

    for raw in ["vim", "nvim"]:
        sources = {term.source for term in vocabulary.resolve(raw).on(Axis.TOOLING)}

        assert TermSource.LINGUIST not in sources


def test_lexicon_frameworks_outrank_linguist_and_explore() -> None:
    vocabulary = make_vocabulary()

    for raw, name in [("django", "django"), ("node", "nodejs")]:
        terms = vocabulary.resolve(raw).terms

        assert [(term.name, term.axis, term.source) for term in terms] == [
            (name, Axis.TOOLING, TermSource.LEXICON)
        ]


@pytest.mark.parametrize("raw", ["Hacktoberfest", "app", "application"])
def test_meta_tags_resolve_to_nothing(raw: str) -> None:
    resolution = make_vocabulary().resolve(raw)

    assert resolution.meta
    assert resolution.terms == ()


@pytest.mark.parametrize("raw", ["machine-learning", "emulator"])
def test_domain_tags_land_on_meaning_only(raw: str) -> None:
    assert names_on(raw, Axis.MEANING) == [raw]
    assert names_on(raw, Axis.TOOLING) == []


def test_uncurated_tag_inherits_tooling_through_its_synonym_group() -> None:
    clusters = make_clusters(
        synonyms={"cli-tools": "cli", "cli": "cli"},
        tooling_parents={"cli-tools": "cli"},
    )
    resolution = make_vocabulary(clusters).resolve("cli-tools")

    assert resolution.inherited
    assert [term.name for term in resolution.on(Axis.TOOLING)] == ["cli"]


def test_claimed_tag_never_inherits_tooling() -> None:
    clusters = make_clusters(tooling_parents={"emulator": "cli"})
    resolution = make_vocabulary(clusters).resolve("emulator")

    assert not resolution.inherited
    assert resolution.on(Axis.TOOLING) == []


def test_cluster_lookups_fall_back_to_the_tag_itself() -> None:
    vocabulary = make_vocabulary(make_clusters(synonyms={"llms": "llm"}, families={"llms": "llm"}))

    assert vocabulary.synonym("LLMs") == "llm"
    assert vocabulary.family("emulator") == "emulator"
    assert vocabulary.clustered("llms")
    assert not vocabulary.clustered("emulator")


def test_related_topics_link_outward_from_their_own_page_only() -> None:
    vocabulary = make_vocabulary()

    assert "vim" in vocabulary.neighbours("neovim")
    assert "neovim" not in vocabulary.neighbours("vim")


def test_plural_tag_resolves_to_its_singular_term() -> None:
    assert names_on("large-language-models", Axis.MEANING) == ["llm"]


@pytest.mark.parametrize("raw", ["ds", "schemes", "rusts"])
def test_short_plurals_and_language_singulars_never_fold(raw: str) -> None:
    assert make_vocabulary().resolve(raw).uncurated


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("image-classification", "text-classification"),
        ("data-mining", "data-science"),
        ("vpn-client", "vpn-server"),
    ],
)
def test_compounds_differing_beside_a_shared_segment_are_siblings(first: str, second: str) -> None:
    assert sibling_compounds(first, second)
    assert sibling_compounds(second, first)


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("data-visualisation", "data-visualization"),
        ("recommender-system", "recommendation-system"),
        ("threat-intelligence", "cyber-threat-intelligence"),
        ("github", "github-api"),
        ("algorithm-competitions", "competitive-programming"),
        ("neural-networks", "neural-network"),
    ],
)
def test_spelling_variants_and_unrelated_compounds_are_not_siblings(
    first: str, second: str
) -> None:
    assert not sibling_compounds(first, second)


def test_explore_front_matter_becomes_a_meaning_term() -> None:
    term = parse_topic_page("neovim", NEOVIM_PAGE)

    assert term is not None
    assert term.name == "neovim"
    assert term.axis is Axis.MEANING
    assert {"nvim", "neovim-qt"} <= term.aliases
    assert term.related == {"vim", "neovim-plugin", "nvimrc"}


def test_page_without_front_matter_is_skipped() -> None:
    assert parse_topic_page("broken", "no front matter here") is None


def test_linguist_keeps_programming_and_markup_languages_only() -> None:
    terms = parse_languages(LANGUAGES_YAML)

    assert [term.name for term in terms] == ["Go", "HTML"]
    assert terms[0].aliases == {"golang"}
