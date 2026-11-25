import random

import pytest

from compass.domain.statistics import (
    auc,
    bootstrap_fixed_effects,
    bootstrap_pooled_mean,
    contrast,
    demeaned_moments,
    fixed_effects_fit,
    percentile_interval,
    phi,
    solve,
)


def test_auc_counts_ties_as_half() -> None:
    assert auc(0.5, [0.1, 0.5, 0.9, 0.2]) == pytest.approx(0.625)


def test_phi_is_one_for_identical_splits_and_zero_for_independent_ones() -> None:
    assert phi([(True, True), (False, False)] * 5) == pytest.approx(1.0)
    assert phi([(True, True), (True, False), (False, True), (False, False)]) == pytest.approx(0.0)


def test_phi_of_a_constant_split_is_zero() -> None:
    assert phi([(True, True), (True, False)]) == 0.0


def test_percentile_interval_takes_the_outer_tails() -> None:
    assert percentile_interval([float(value) for value in range(101)]) == (2.0, 98.0)


def test_solve_returns_none_for_a_singular_system() -> None:
    assert solve([[1.0, 2.0], [2.0, 4.0]], [1.0, 2.0]) is None
    assert solve([[2.0, 0.0], [0.0, 4.0]], [2.0, 8.0]) == pytest.approx([1.0, 2.0])


def test_fixed_effects_remove_each_group_level() -> None:
    rng = random.Random(7)
    moments = []

    for level in range(40):
        rows = [[rng.random(), rng.random()] for _ in range(6)]
        outcomes = [10.0 * level + 2.0 * first - 3.0 * second for first, second in rows]
        moments.append(demeaned_moments(rows, outcomes))

    assert fixed_effects_fit(moments) == pytest.approx([2.0, -3.0])


def test_bootstrap_brackets_a_noisy_effect() -> None:
    rng = random.Random(11)
    moments = []

    for level in range(60):
        rows = [[float(rng.random() < 0.5)] for _ in range(8)]
        outcomes = [level + 0.3 * row[0] + rng.gauss(0, 0.2) for row in rows]
        moments.append(demeaned_moments(rows, outcomes))

    point = fixed_effects_fit(moments)
    assert point is not None

    draws = bootstrap_fixed_effects(moments, 500, random.Random(3))
    effect = contrast(point, draws, [1.0])

    assert effect.low < 0.3 < effect.high
    assert effect.excludes_zero


def test_pooled_mean_weights_groups_by_size() -> None:
    estimate = bootstrap_pooled_mean([[1.0, 1.0, 1.0], [0.0]], 200, random.Random(5))

    assert estimate.value == pytest.approx(0.75)
    assert 0.0 <= estimate.low <= estimate.high <= 1.0
