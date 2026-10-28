import logging
from collections.abc import Sequence
from pathlib import Path

import httpx
import numpy as np
import numpy.typing as npt
from model2vec import StaticModel

logger = logging.getLogger(__name__)

MODEL_FILES = ("config.json", "tokenizer.json", "model.safetensors")
HUB_FILE_URL = "https://huggingface.co/{repository}/resolve/{revision}/{file_name}"
IPV4_ANY = "0.0.0.0"


def download_file(url: str, path: Path, timeout: float) -> None:
    partial = path.with_name(f"{path.name}.part")

    transport = httpx.HTTPTransport(local_address=IPV4_ANY)

    with (
        httpx.Client(transport=transport, follow_redirects=True, timeout=timeout) as client,
        client.stream("GET", url) as response,
    ):
        response.raise_for_status()

        with partial.open("wb") as file:
            for chunk in response.iter_bytes():
                file.write(chunk)

    partial.replace(path)


def download_model(repository: str, revision: str, cache_dir: Path, timeout: float) -> Path:
    model_dir = cache_dir / repository.replace("/", "--") / revision
    model_dir.mkdir(parents=True, exist_ok=True)

    for file_name in MODEL_FILES:
        path = model_dir / file_name

        if path.exists():
            continue

        url = HUB_FILE_URL.format(repository=repository, revision=revision, file_name=file_name)
        logger.info("Downloading %s", url)
        download_file(url, path, timeout)

    return model_dir


class TagEmbedder:
    def __init__(self, model_dir: Path) -> None:
        self.model = StaticModel.from_pretrained(model_dir, force_download=False)

    def encode(self, texts: Sequence[str]) -> npt.NDArray[np.float64]:
        return np.asarray(self.model.encode(list(texts)), dtype=np.float64)
