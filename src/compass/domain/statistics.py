import dataclasses
import math
import random
from collections.abc import Sequence

CONFIDENCE = 0.95
SINGULAR_PIVOT = 1e-9


@dataclasses.dataclass(frozen=True)
class Estimate:
    value: float
    low: float
    high: float

    @property
    def excludes_zero(self) -> bool:
        return self.low > 0 or self.high < 0

    @property
    def standard_error(self) -> float:
        return (self.high - self.low) / (2 * 1.96)


@dataclasses.dataclass(frozen=True)
class GroupMoments:
    xtx: tuple[tuple[float, ...], ...]
    xty: tuple[float, ...]
    rows: int


def auc(positive: float, negatives: Sequence[float]) -> float:
    wins = sum(
        1.0 if positive > other else 0.5 if positive == other else 0.0 for other in negatives
    )

    return wins / len(negatives)


def phi(pairs: Sequence[tuple[bool, bool]]) -> float:
    both = sum(first and second for first, second in pairs)
    first_only = sum(first and not second for first, second in pairs)
    second_only = sum(second and not first for first, second in pairs)
    neither = len(pairs) - both - first_only - second_only
    denominator = math.sqrt(
        (both + first_only)
        * (second_only + neither)
        * (both + second_only)
        * (first_only + neither)
    )

    if denominator == 0:
        return 0.0

    return (both * neither - first_only * second_only) / denominator


def percentile_interval(samples: Sequence[float]) -> tuple[float, float]:
    ordered = sorted(samples)
    tail = (1 - CONFIDENCE) / 2
    last = len(ordered) - 1

    return ordered[math.floor(tail * last)], ordered[math.ceil((1 - tail) * last)]


def resample(size: int, rng: random.Random) -> list[int]:
    return rng.choices(range(size), k=size)


def bootstrap_pooled_mean(
    groups: Sequence[Sequence[float]],
    reps: int,
    rng: random.Random,
) -> Estimate:
    sums = [sum(group) for group in groups]
    counts = [len(group) for group in groups]
    draws: list[float] = []

    for _ in range(reps):
        picked = resample(len(groups), rng)
        total = sum(counts[index] for index in picked)

        if total:
            draws.append(sum(sums[index] for index in picked) / total)

    low, high = percentile_interval(draws)

    return Estimate(value=sum(sums) / sum(counts), low=low, high=high)


def demeaned_moments(rows: Sequence[Sequence[float]], outcomes: Sequence[float]) -> GroupMoments:
    width = len(rows[0])
    means = [sum(row[column] for row in rows) / len(rows) for column in range(width)]
    outcome_mean = sum(outcomes) / len(outcomes)
    centered = [[row[column] - means[column] for column in range(width)] for row in rows]
    centered_outcomes = [outcome - outcome_mean for outcome in outcomes]

    return GroupMoments(
        xtx=tuple(
            tuple(sum(row[left] * row[right] for row in centered) for right in range(width))
            for left in range(width)
        ),
        xty=tuple(
            sum(
                row[column] * outcome
                for row, outcome in zip(centered, centered_outcomes, strict=True)
            )
            for column in range(width)
        ),
        rows=len(rows),
    )


def solve(matrix: list[list[float]], vector: list[float]) -> list[float] | None:
    size = len(vector)
    augmented = [[*matrix[row], vector[row]] for row in range(size)]
    scale = max((abs(value) for row in matrix for value in row), default=0.0) or 1.0

    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))

        if abs(augmented[pivot][column]) < SINGULAR_PIVOT * scale:
            return None

        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]

        for row in range(size):
            if row == column:
                continue

            factor = augmented[row][column] / augmented[column][column]
            augmented[row] = [
                value - factor * base
                for value, base in zip(augmented[row], augmented[column], strict=True)
            ]

    return [augmented[row][size] / augmented[row][row] for row in range(size)]


def fixed_effects_fit(moments: Sequence[GroupMoments]) -> list[float] | None:
    width = len(moments[0].xty)
    xtx = [
        [sum(item.xtx[row][column] for item in moments) for column in range(width)]
        for row in range(width)
    ]
    xty = [sum(item.xty[row] for item in moments) for row in range(width)]

    return solve(xtx, xty)


def bootstrap_fixed_effects(
    moments: Sequence[GroupMoments],
    reps: int,
    rng: random.Random,
) -> list[list[float]]:
    draws: list[list[float]] = []

    for _ in range(reps):
        fit = fixed_effects_fit([moments[index] for index in resample(len(moments), rng)])

        if fit is not None:
            draws.append(fit)

    return draws


def contrast(
    point: Sequence[float], draws: Sequence[Sequence[float]], weights: Sequence[float]
) -> Estimate:
    def combine(values: Sequence[float]) -> float:
        return sum(weight * value for weight, value in zip(weights, values, strict=True))

    low, high = percentile_interval([combine(draw) for draw in draws])

    return Estimate(value=combine(point), low=low, high=high)
