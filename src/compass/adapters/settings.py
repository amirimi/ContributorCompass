import datetime
import os
from pathlib import Path

from dotenv import load_dotenv

PERSONAL_PROFILE_FILE = Path("personal_profile.json")
PROJECT_TOPICS_DIR = Path("project_topics")
VOCABULARY_FILE = Path("vocabulary.json")
PREFERENCES_FILE = Path("preferences.toml")
CLUSTERS_FILE = Path("clusters.json")
MODEL_CACHE_DIR = Path(".cache/models")

EMBEDDING_MODEL = "minishlab/potion-base-8M"
EMBEDDING_REVISION = "bf8b056651a2c21b8d2565580b8569da283cab23"
MODEL_DOWNLOAD_TIMEOUT = 120.0

PERSONAL_PROFILE_STALE_AFTER = datetime.timedelta(days=30)
PROJECT_TOPICS_STALE_AFTER = datetime.timedelta(days=7)
VOCABULARY_STALE_AFTER = datetime.timedelta(days=30)

PERSONAL_PROFILE_REFRESH_AFTER = datetime.timedelta(days=25)
PROJECT_TOPICS_REFRESH_AFTER = datetime.timedelta(days=5)


def resolve_github_token() -> str | None:
    load_dotenv()

    return os.environ.get("GITHUB_TOKEN") or None
