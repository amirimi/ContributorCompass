from compass.domain import EvidenceSource, TopicProject, classify
from tests.vocabulary_fixtures import make_clusters, make_vocabulary


def project(
    name: str,
    description: str | None = None,
    topics: list[str] | None = None,
    language: str | None = None,
    language_bytes: dict[str, int] | None = None,
) -> TopicProject:
    return TopicProject(
        owner="owner",
        name=name,
        url=f"https://github.com/owner/{name}",
        description=description,
        topics=topics or [],
        language=language,
        language_bytes=language_bytes or {},
    )


def test_tooling_lists_every_language_above_a_tenth_of_the_code() -> None:
    neovim = project(
        "neovim",
        language="Vim Script",
        language_bytes={"Vim Script": 39, "Lua": 33, "C": 27, "CMake": 1},
    )

    identity = classify(neovim, make_vocabulary())

    assert [item.value for item in identity.tooling] == ["Vim Script", "Lua", "C"]
    assert identity.tooling[0].raw == "Vim Script 39%"


def test_tooling_falls_back_to_the_primary_language_without_bytes() -> None:
    identity = classify(project("bare", language="Go"), make_vocabulary())

    assert [(item.value, item.source) for item in identity.tooling] == [
        ("Go", EvidenceSource.PRIMARY_LANGUAGE)
    ]


def test_language_tags_join_tooling_once() -> None:
    identity = classify(
        project("cli", topics=["golang", "rust"], language_bytes={"Go": 100}),
        make_vocabulary(),
    )

    assert [item.value for item in identity.tooling] == ["Go", "Rust"]


def test_forms_and_hosts_join_tooling() -> None:
    identity = classify(
        project("plugin", topics=["neovim-plugin", "cli", "git"], language_bytes={"Lua": 100}),
        make_vocabulary(),
    )

    assert [item.value for item in identity.tooling] == ["Lua", "neovim-plugin", "cli", "git"]
    assert [item.value for item in identity.meaning] == ["git"]


def test_inherited_tooling_names_the_synonym_source() -> None:
    clusters = make_clusters(synonyms={"cli-tools": "cli"}, tooling_parents={"cli-tools": "cli"})
    identity = classify(project("tool", topics=["cli-tools"]), make_vocabulary(clusters))

    assert [(item.value, item.source) for item in identity.tooling] == [
        ("cli", EvidenceSource.SYNONYM)
    ]
    assert identity.meaning == []


def test_meaning_keeps_curated_and_uncurated_terms_apart() -> None:
    clusters = make_clusters(synonyms={"retro-thing": "emulator"})
    identity = classify(
        project("repo", topics=["nvim", "retro-thing", "hacktoberfest", "rust", "mystery-tag"]),
        make_vocabulary(clusters),
    )

    assert [(item.value, item.source) for item in identity.meaning] == [
        ("neovim", EvidenceSource.ALIAS),
        ("retro-thing", EvidenceSource.UNCURATED),
        ("mystery-tag", EvidenceSource.UNCURATED),
    ]
    assert identity.unresolved == ["mystery-tag"]


def test_every_piece_of_evidence_names_its_source_and_input() -> None:
    identity = classify(
        project(
            "repo",
            "A Neovim plugin for git",
            ["nvim", "golang", "mystery-tag"],
            language="Lua",
            language_bytes={"Lua": 90, "Go": 10},
        ),
        make_vocabulary(),
    )
    evidence = [*identity.tooling, *identity.meaning]

    assert evidence
    assert all(item.source and item.raw for item in evidence)
