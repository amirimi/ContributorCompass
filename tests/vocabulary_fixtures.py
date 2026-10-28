from collections.abc import Iterable

from compass.adapters import load_lexicon
from compass.domain import (
    Axis,
    TagClusters,
    Term,
    TermSource,
    Vocabulary,
    VocabularySources,
    build_vocabulary,
)


def explore(name: str, aliases: Iterable[str] = (), related: Iterable[str] = ()) -> Term:
    return Term(
        name=name,
        axis=Axis.MEANING,
        aliases=frozenset(aliases),
        related=frozenset(related),
        source=TermSource.EXPLORE,
    )


def linguist(name: str, aliases: Iterable[str] = ()) -> Term:
    return Term(
        name=name,
        axis=Axis.TOOLING,
        aliases=frozenset(aliases),
        source=TermSource.LINGUIST,
    )


SOURCES = VocabularySources(
    explore=[
        explore("neovim", ["nvim", "neovim-qt"], ["vim", "neovim-plugin"]),
        explore("vim", related=["emacs"]),
        explore("emacs"),
        explore("neovim-plugin"),
        explore("cli", ["command-line", "commandline", "command-line-interface"]),
        explore("docker", ["docker-image"]),
        explore("tui", ["terminal-user-interface"], ["cli", "terminal"]),
        explore("terminal"),
        explore("llm", ["llms", "large-language-model"], ["machine-learning"]),
        explore("machine-learning"),
        explore("raspberry-pi"),
        explore("git"),
        explore("python", ["python3"]),
        explore("rust", ["rust-lang"]),
        explore("emulator"),
        explore("go", ["golang"]),
        explore("typescript"),
        explore("nodejs", ["node"]),
        explore("django"),
        explore("framework"),
    ],
    linguist=[
        linguist("Python", ["python3", "py"]),
        linguist("Rust", ["rs"]),
        linguist("Go", ["golang"]),
        linguist("TypeScript", ["ts"]),
        linguist("JavaScript", ["js", "node"]),
        linguist("Lua"),
        linguist("C"),
        linguist("Kotlin"),
        linguist("Vim script", ["vim", "viml", "nvim", "vimscript"]),
        linguist("Jinja", ["django", "jinja2"]),
    ],
)


def make_clusters(
    synonyms: dict[str, str] | None = None,
    families: dict[str, str] | None = None,
    tooling_parents: dict[str, str] | None = None,
) -> TagClusters:
    return TagClusters(
        model="fake",
        revision="fake",
        synonym_cut=0.2,
        family_cut=0.4,
        synonyms=synonyms or {},
        families=families or {},
        tooling_parents=tooling_parents or {},
    )


def make_vocabulary(clusters: TagClusters | None = None) -> Vocabulary:
    return build_vocabulary(SOURCES, load_lexicon(), clusters or make_clusters())
