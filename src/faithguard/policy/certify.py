"""Certifying a policy family: Learn-then-Test over its grid.

1. Order the grid on the tune split, most cautious (lowest estimated risk) first.
2. On the calibration split, compute each setting's Hoeffding-Bentkus p-value for
   H0: P(unsafe | sent) > alpha, and certify settings in order until the first p > delta.
3. Among certified settings, choose the one with the highest useful coverage on calibration.

Because the order comes from a different split, every certified setting keeps the
guarantee simultaneously, so choosing among them is allowed. A cluster-level version
treats each issuer as one draw (the sensitivity check for risk R-14).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from faithguard.evaluate import policy_metrics
from faithguard.stats import fixed_sequence, hb_pvalue, selective_risk_pvalue


def states(records: Sequence, actions: Sequence[str]) -> list[str]:
    return [r.outcomes[a] for r, a in zip(records, actions)]


def indicators(records: Sequence, actions: Sequence[str]) -> tuple[list[bool], list[bool]]:
    s = states(records, actions)
    sent = [x != "abstained" for x in s]
    unsafe = [x == "unsupported" for x in s]
    return unsafe, sent


@dataclass
class Certificate:
    alpha: float
    delta: float
    order: list[str]
    pvalues: dict[str, float]
    certified: list[str]
    chosen: str | None
    calibration: dict = field(default_factory=dict)  # metrics of the chosen setting on calibration


def order_settings(tune: Sequence, candidates: dict[str, list[str]]) -> list[str]:
    """Most cautious first: lowest residual risk on the tune split, then lowest coverage."""
    keyed = []
    for name, acts in candidates.items():
        m = policy_metrics(states(tune, acts))
        keyed.append((m["residual_risk"], m["emission_coverage"], name))
    return [name for *_, name in sorted(keyed)]


def certify(
    tune: Sequence, calibration: Sequence, tune_candidates: dict[str, list[str]],
    cal_candidates: dict[str, list[str]], alpha: float = 0.10, delta: float = 0.05,
) -> Certificate:
    order = order_settings(tune, tune_candidates)
    pvalues = {}
    for name in order:
        unsafe, sent = indicators(calibration, cal_candidates[name])
        pvalues[name] = selective_risk_pvalue(unsafe, sent, alpha)
    certified = [order[i] for i in fixed_sequence([pvalues[n] for n in order], delta)]
    chosen, best = None, None
    for name in certified:
        m = policy_metrics(states(calibration, cal_candidates[name]))
        key = (m["useful_coverage"], -m["residual_risk"])
        if best is None or key > best:
            chosen, best = name, key
    cal = policy_metrics(states(calibration, cal_candidates[chosen])) if chosen else {}
    return Certificate(alpha, delta, order, pvalues, certified, chosen, cal)


def cluster_pvalue(records: Sequence, actions: Sequence[str], alpha: float) -> float:
    """Issuer-level certificate: each issuer's mean shifted loss is one bounded draw."""
    by_issuer: dict[str, list[float]] = {}
    for r, a in zip(records, actions):
        state = r.outcomes[a]
        loss = (float(state == "unsupported") - alpha * float(state != "abstained") + alpha) / (1 + alpha)
        by_issuer.setdefault(r.issuer, []).append(loss)
    means = [float(np.mean(v)) for v in by_issuer.values()]
    return hb_pvalue(float(np.mean(means)), len(means), alpha / (1 + alpha))
