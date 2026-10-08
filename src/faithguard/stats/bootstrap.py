"""Issuer-clustered bootstrap: confidence intervals that respect companies.

Answers about the same company are related, so resampling answers one by one
gives intervals that are too narrow. Here whole issuers are resampled with
replacement, and every answer of a chosen issuer comes along.
"""

from __future__ import annotations

import random
from typing import Callable, Hashable, Sequence, TypeVar

T = TypeVar("T")


def cluster_bootstrap(
    records: Sequence[T],
    cluster: Callable[[T], Hashable],
    statistic: Callable[[list[T]], float],
    n_boot: int = 2000,
    level: float = 0.95,
    seed: int = 0,
) -> tuple[float, float, float]:
    """(estimate, lower, upper): a percentile interval from resampling clusters."""
    groups: dict[Hashable, list[T]] = {}
    for r in records:
        groups.setdefault(cluster(r), []).append(r)
    keys = list(groups)
    estimate = statistic(list(records))
    if len(keys) < 2:
        return estimate, float("nan"), float("nan")
    rng = random.Random(seed)
    stats = []
    for _ in range(n_boot):
        sample = [r for k in rng.choices(keys, k=len(keys)) for r in groups[k]]
        stats.append(statistic(sample))
    stats.sort()
    lo = stats[int((1 - level) / 2 * n_boot)]
    hi = stats[min(n_boot - 1, int((1 + level) / 2 * n_boot))]
    return estimate, lo, hi
