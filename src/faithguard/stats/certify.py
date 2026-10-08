"""Certified risk control: Learn-then-Test with Hoeffding-Bentkus p-values.

The policy paper certifies that, among answers the pipeline sends, the share that
are wrong is at most alpha, with probability at least 1 - delta over the draw of
the calibration set. The ratio "wrong sent / sent <= alpha" is rewritten as a
per-item loss whose mean must be <= 0:

    L = 1{unsafe answer sent} - alpha * 1{answer sent}       in [-alpha, 1]

Shifting to [0, 1] gives L' = (L + alpha) / (1 + alpha), certified at alpha / (1 + alpha).
Each candidate policy setting gets a p-value; fixed-sequence testing walks the
settings from most to least cautious and certifies them until the first failure.

Assumption: calibration answers are independent draws from the same distribution
as test answers. Answers about the same company are related, so pair every
certificate with the issuer-level sensitivity check (risk R-14).
"""

from __future__ import annotations

import math
from typing import Sequence

from scipy.stats import binom


def _h1(a: float, b: float) -> float:
    """Kullback-Leibler divergence between Bernoulli(a) and Bernoulli(b)."""
    a = min(max(a, 1e-12), 1 - 1e-12)
    return a * math.log(a / b) + (1 - a) * math.log((1 - a) / (1 - b))


def hb_pvalue(mean_loss: float, n: int, alpha: float) -> float:
    """Hoeffding-Bentkus p-value for H0: E[loss] > alpha, losses in [0, 1] (Bates et al. 2021)."""
    if n == 0:
        return 1.0
    hoeffding = math.exp(-n * _h1(min(mean_loss, alpha), alpha))
    bentkus = math.e * binom.cdf(math.ceil(n * mean_loss), n, alpha)
    return min(1.0, hoeffding, bentkus)


def selective_risk_pvalue(unsafe_sent: Sequence[bool], sent: Sequence[bool], alpha: float) -> float:
    """p-value for H0: P(unsafe | sent) > alpha, from per-item indicators."""
    n = len(sent)
    if n == 0:
        return 1.0
    shifted = [((float(u) - alpha * float(s)) + alpha) / (1 + alpha) for u, s in zip(unsafe_sent, sent)]
    return hb_pvalue(sum(shifted) / n, n, alpha / (1 + alpha))


def fixed_sequence(p_values: Sequence[float], delta: float) -> list[int]:
    """Indices certified by fixed-sequence testing (p-values ordered from most to least cautious)."""
    certified = []
    for i, p in enumerate(p_values):
        if p > delta:
            break
        certified.append(i)
    return certified


def zero_error_budget(alpha: float, delta: float = 0.05) -> int:
    """Answers needed, with no errors among them, for an exact binomial bound below alpha."""
    return math.ceil(math.log(delta) / math.log(1 - alpha))


def hb_zero_error_budget(alpha: float, delta: float = 0.05) -> int:
    """The same budget under the linearised Hoeffding-Bentkus certificate (every item sent, none unsafe)."""
    n = 1
    while selective_risk_pvalue([False] * n, [True] * n, alpha) > delta:
        n += 1
    return n


def clopper_pearson_upper(errors: int, n: int, delta: float = 0.05) -> float:
    """One-sided (1 - delta) upper bound on an error rate."""
    if n == 0:
        return 1.0
    if errors >= n:
        return 1.0
    from scipy.stats import beta

    return float(beta.ppf(1 - delta, errors + 1, n - errors))
