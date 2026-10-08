"""Policy families: each turns per-item predictions into an action for every setting on its grid.

    outcome_aware  send if P(unsafe) < tau_send; else repair if P(fix) > tau_fix; else abstain  (the paper's policy)
    verified_only  send if the detector's risk is below a threshold, else abstain (calibrated detector threshold)
    threshold_v0   as verified_only, but repair when the evidence holds every correct value (policy v0)
    four_state     a static classifier: clean -> send, fixable -> repair, otherwise abstain, above a confidence
    send_all, repair_all   fixed strategies
    oracle         the best action per item from stored outcomes (an upper bound, not a policy)

A grid is fixed in advance (pre-registered); certification picks among its settings.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np

TAU_SEND = (0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.3, 0.5)
TAU_FIX = (0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99)
RISK_THRESHOLDS = (0.25, 0.75, 1.01)
CONFIDENCE = (0.5, 0.6, 0.7, 0.8, 0.9, 0.95)
SAFE = ("supported_unhelpful", "supported_useful")


def outcome_aware(p_unsafe: np.ndarray, p_fix: np.ndarray) -> dict[str, list[str]]:
    out = {}
    for ts in TAU_SEND:
        for tf in TAU_FIX:
            acts = np.where(p_unsafe < ts, "send", np.where(p_fix > tf, "repair", "abstain"))
            out[f"send<{ts},fix>{tf}"] = acts.tolist()
    return out


def verified_only(records: Sequence) -> dict[str, list[str]]:
    return {f"risk<{t}": ["send" if r.risk < t else "abstain" for r in records] for t in RISK_THRESHOLDS}


def threshold_v0(records: Sequence) -> dict[str, list[str]]:
    out = {}
    for t in RISK_THRESHOLDS:
        out[f"risk<{t}"] = [
            "send" if r.risk < t and r.features.get("n_claims", 0) > 0
            else "repair" if r.features.get("evidence_sufficient", 0) > 0
            else "abstain"
            for r in records
        ]
    return out


def four_state_labels(records: Sequence) -> np.ndarray:
    """0 clean (the original is safe), 1 fixable (repair gives a useful answer), 2 neither."""
    return np.array([
        0 if r.outcomes["send"] in SAFE else 1 if r.outcomes["repair"] == "supported_useful" else 2
        for r in records
    ])


def four_state(proba: np.ndarray) -> dict[str, list[str]]:
    """Act on the most likely state only if the classifier is confident enough; otherwise abstain."""
    best, conf = proba.argmax(axis=1), proba.max(axis=1)
    action = np.array(["send", "repair", "abstain"])[best]
    return {f"conf>={c}": np.where(conf >= c, action, "abstain").tolist() for c in CONFIDENCE}


def fixed(records: Sequence, action: str) -> dict[str, list[str]]:
    return {action: [action] * len(records)}


def oracle(records: Sequence) -> list[str]:
    """The best action with hindsight: a useful answer if any action gives one, else a safe one, else abstain."""
    acts = []
    for r in records:
        if r.outcomes["send"] == "supported_useful":
            acts.append("send")
        elif r.outcomes["repair"] == "supported_useful":
            acts.append("repair")
        elif r.outcomes["send"] in SAFE:
            acts.append("send")
        elif r.outcomes["repair"] in SAFE:
            acts.append("repair")
        else:
            acts.append("abstain")
    return acts
