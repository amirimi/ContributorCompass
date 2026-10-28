from collections.abc import Sequence

import numpy as np
import numpy.typing as npt
from scipy.cluster.hierarchy import fcluster, linkage

Vectors = npt.NDArray[np.float64]


def unit_rows(vectors: Vectors) -> Vectors:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)

    return vectors / np.maximum(norms, np.finfo(np.float64).tiny)


def mix_context(
    names: Vectors,
    projects: Sequence[Sequence[int]],
    contributes: Sequence[bool],
) -> Vectors:
    unit_names = unit_rows(names)
    weights = np.asarray(contributes, dtype=np.float64)[:, np.newaxis]
    context = np.zeros_like(unit_names)

    for members in projects:
        if len(members) < 2:
            continue

        rows = list(members)
        contributions = unit_names[rows] * weights[rows]
        context[rows] += contributions.sum(axis=0) - contributions

    return unit_rows(unit_names + unit_rows(context))


def nonzero_rows(vectors: Vectors) -> npt.NDArray[np.bool_]:
    return np.linalg.norm(vectors, axis=1) > 0


def cut_tree(vectors: Vectors, cuts: Sequence[float]) -> list[list[int]]:
    tree = linkage(vectors, method="average", metric="cosine")

    return [fcluster(tree, t=cut, criterion="distance").tolist() for cut in cuts]
