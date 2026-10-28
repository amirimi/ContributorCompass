import logging
import os
from pathlib import Path

import pydantic

from compass.domain import (
    CacheFile,
    PersonalProfileFile,
    ProjectTopicsFile,
    TagClusters,
    VocabularySources,
)

logger = logging.getLogger(__name__)


def load_cache_file[CachedT: CacheFile](
    model: type[CachedT],
    file_path: Path,
) -> CachedT | None:
    try:
        return model.model_validate_json(file_path.read_bytes())
    except FileNotFoundError:
        return None
    except pydantic.ValidationError:
        logger.warning("Discarding unreadable cache at %s", file_path)
        return None


def write_cache_file(cache_file: CacheFile, file_path: Path) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    temp_file = file_path.with_suffix(".json.tmp")

    with temp_file.open("w") as file:
        file.write(cache_file.model_dump_json(indent=4))
        file.flush()
        os.fsync(file.fileno())

    os.replace(temp_file, file_path)


class TopicCache:
    def __init__(self, personal_file: Path, project_dir: Path) -> None:
        self.personal_file = personal_file
        self.project_dir = project_dir

    def project_path(self, topic: str) -> Path:
        return self.project_dir / f"{topic}.json"

    def cached_topics(self) -> list[str]:
        return sorted(path.stem for path in self.project_dir.glob("*.json"))

    def load_personal(self) -> PersonalProfileFile | None:
        return load_cache_file(PersonalProfileFile, self.personal_file)

    def save_personal(self, profile: PersonalProfileFile) -> None:
        write_cache_file(profile, self.personal_file)

    def load_projects(self, topic: str) -> ProjectTopicsFile | None:
        return load_cache_file(ProjectTopicsFile, self.project_path(topic))

    def save_projects(self, topic: str, project_topics: ProjectTopicsFile) -> None:
        write_cache_file(project_topics, self.project_path(topic))


class VocabularyCache:
    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path

    def load(self) -> VocabularySources | None:
        return load_cache_file(VocabularySources, self.file_path)

    def save(self, sources: VocabularySources) -> None:
        write_cache_file(sources, self.file_path)


class ClusterCache:
    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path

    def load(self) -> TagClusters | None:
        return load_cache_file(TagClusters, self.file_path)

    def save(self, clusters: TagClusters) -> None:
        write_cache_file(clusters, self.file_path)
