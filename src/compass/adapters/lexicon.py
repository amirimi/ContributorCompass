import tomllib
from importlib import resources
from pathlib import Path

from compass.domain import Lexicon, Preferences

LEXICON_RESOURCE = "lexicon.toml"


def load_lexicon() -> Lexicon:
    text = resources.files("compass").joinpath(LEXICON_RESOURCE).read_text()

    return Lexicon.model_validate(tomllib.loads(text))


def load_preferences(file_path: Path) -> Preferences:
    try:
        text = file_path.read_text()
    except FileNotFoundError:
        return Preferences()

    return Preferences.model_validate(tomllib.loads(text))
