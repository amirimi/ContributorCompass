from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence

from compass.domain.models import CacheFile


class TagClusters(CacheFile):
    model: str
    revision: str
    synonym_cut: float
    family_cut: float
    synonyms: dict[str, str]
    families: dict[str, str]
    tooling_parents: dict[str, str]


def group_members(assignments: Mapping[str, str]) -> dict[str, list[str]]:
    groups: defaultdict[str, list[str]] = defaultdict(list)

    for tag, group in assignments.items():
        groups[group].append(tag)

    return dict(groups)


def label_groups(
    tags: Sequence[str],
    assignments: Sequence[int],
    counts: Mapping[str, int],
    curated: frozenset[str],
) -> dict[str, str]:
    groups: defaultdict[int, list[str]] = defaultdict(list)

    for tag, group in zip(tags, assignments, strict=True):
        groups[group].append(tag)

    labels: dict[str, str] = {}

    for members in groups.values():
        label = min(members, key=lambda tag: (tag not in curated, -counts.get(tag, 0), tag))

        for tag in members:
            labels[tag] = label

    return labels


def inherit_tooling(
    synonyms: Mapping[str, str],
    counts: Mapping[str, int],
    is_tooling: Callable[[str], bool],
    is_claimed: Callable[[str], bool],
) -> dict[str, str]:
    parents: dict[str, str] = {}

    for members in group_members(synonyms).values():
        tooling = sorted(
            (tag for tag in members if is_tooling(tag)),
            key=lambda tag: (-counts.get(tag, 0), tag),
        )

        if not tooling:
            continue

        for tag in members:
            if not is_claimed(tag):
                parents[tag] = tooling[0]

    return parents
