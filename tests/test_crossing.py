from compass.domain import (
    Crossing,
    MeaningRelation,
    PersonalProfileFile,
    Preferences,
    Stance,
    TagClusters,
    ToolingRelation,
    TopicProject,
    classify,
    cross,
    describe_contributor,
)
from tests.vocabulary_fixtures import make_clusters, make_vocabulary

PREFERENCES = Preferences.model_validate(
    {
        "meaning": {"declared": ["llms"]},
        "tooling": {"open": ["rust"], "avoided": ["TypeScript"]},
    }
)


def profile(
    topics: list[tuple[str, int]] | None = None,
    languages: list[tuple[str, int]] | None = None,
) -> PersonalProfileFile:
    return PersonalProfileFile(
        github_handle="octocat",
        topics_frequency=topics or [("python", 5), ("editor", 2)],
        languages_frequency=languages or [("Python", 5)],
    )


def project(language: str, language_bytes: dict[str, int], topics: list[str]) -> TopicProject:
    return TopicProject(
        owner="owner",
        name="repo",
        url="https://github.com/owner/repo",
        language=language,
        language_bytes=language_bytes,
        topics=topics,
    )


def crossing(
    target: TopicProject,
    contributor_profile: PersonalProfileFile | None = None,
    clusters: TagClusters | None = None,
    preferences: Preferences = PREFERENCES,
) -> Crossing:
    vocabulary = make_vocabulary(clusters)
    contributor = describe_contributor(contributor_profile or profile(), preferences, vocabulary)

    return cross(classify(target, vocabulary), contributor, vocabulary)


def test_stances_resolve_through_the_vocabulary() -> None:
    vocabulary = make_vocabulary()
    contributor = describe_contributor(profile(), PREFERENCES, vocabulary)

    assert contributor.stances == {"rust": Stance.OPEN, "typescript": Stance.AVOIDED}
    assert contributor.declared_meaning == {"llm"}
    assert contributor.tooling_history == {"python": 10}


def test_avoided_primary_language_is_vetoed() -> None:
    result = crossing(project("TypeScript", {"TypeScript": 100}, ["cli"]))

    assert result.tooling is ToolingRelation.AVOIDED


def test_avoided_language_outside_the_primary_slot_is_not_vetoed() -> None:
    result = crossing(project("Go", {"Go": 54, "TypeScript": 21, "HTML": 25}, ["cli"]))

    assert result.tooling is ToolingRelation.UNFAMILIAR


def test_open_language_in_a_declared_domain() -> None:
    result = crossing(project("Rust", {"Rust": 100}, ["llm", "rust"]))

    assert (result.tooling, result.meaning) == (ToolingRelation.OPEN, MeaningRelation.DECLARED)


def test_avoidance_beats_history() -> None:
    history = profile(languages=[("TypeScript", 9), ("Python", 1)])
    result = crossing(project("TypeScript", {"TypeScript": 100}, ["cli"]), history)

    assert result.tooling is ToolingRelation.AVOIDED


def test_known_language_from_history() -> None:
    result = crossing(project("Python", {"Python": 100}, ["cli"]))

    assert result.tooling is ToolingRelation.KNOWN


def test_related_topic_of_a_known_topic_is_adjacent() -> None:
    history = profile(topics=[("neovim", 3)])
    result = crossing(project("Lua", {"Lua": 100}, ["vim"]), history)

    assert result.meaning is MeaningRelation.ADJACENT
    assert result.deciding_terms[-1] == "vim"


def test_unrelated_topic_is_new() -> None:
    result = crossing(project("Lua", {"Lua": 100}, ["raspberry-pi"]))

    assert result.meaning is MeaningRelation.NEW


def test_avoided_form_is_vetoed_whatever_the_language() -> None:
    preferences = Preferences.model_validate({"tooling": {"avoided": ["electron"]}})
    result = crossing(
        project("JavaScript", {"JavaScript": 100}, ["electron"]), preferences=preferences
    )

    assert (result.tooling, result.deciding_terms[0]) == (ToolingRelation.AVOIDED, "electron")


def test_shared_forms_join_the_deciding_terms_of_known_tooling() -> None:
    history = profile(topics=[("cli", 3)])
    result = crossing(project("Python", {"Python": 100}, ["cli", "emulator"]), history)

    assert result.tooling is ToolingRelation.KNOWN
    assert result.deciding_terms[:2] == ["python", "cli"]


def test_synonym_of_a_history_term_is_known() -> None:
    clusters = make_clusters(synonyms={"text-editor": "editor", "editor": "editor"})
    result = crossing(project("Lua", {"Lua": 100}, ["text-editor"]), clusters=clusters)

    assert (result.meaning, result.deciding_terms[-1]) == (MeaningRelation.KNOWN, "text-editor")


def test_family_of_a_history_term_is_only_adjacent() -> None:
    clusters = make_clusters(families={"wysiwyg": "editor", "editor": "editor"})
    result = crossing(project("Lua", {"Lua": 100}, ["wysiwyg"]), clusters=clusters)

    assert result.meaning is MeaningRelation.ADJACENT


def test_family_of_a_declared_term_is_declared() -> None:
    clusters = make_clusters(families={"local-llm": "llm", "llm": "llm"})
    result = crossing(project("Rust", {"Rust": 100}, ["local-llm"]), clusters=clusters)

    assert result.meaning is MeaningRelation.DECLARED
