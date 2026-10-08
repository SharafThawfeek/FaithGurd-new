"""Fusing Channel A and Channel B into one calibrated risk.

Per numeric claim, features from both channels feed a logistic regression that
predicts whether the claim is wrong; isotonic regression (or temperature scaling)
then calibrates it on the calibration split. An answer's risk is the chance that at
least one claim is wrong. Learn-then-Test then picks the send threshold (policy study).
"""

from __future__ import annotations

import pickle
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence

import numpy as np

from faithguard.records import DetectorOutput, Item, Span

FEATURES = (
    "b_supported", "b_unsupported", "b_unverifiable", "b_slots", "b_has_expected",
    "a_max", "a_mean", "a_any", "kind_percent", "has_direction",
)


def claim_features(det: DetectorOutput, tokens: Sequence[tuple[int, int, float, int]]) -> list[dict]:
    """One row per claim: Channel B's verdict and Channel A's token probabilities over the claim's characters."""
    rows = []
    for claim in det.claims:
        check = det.check(claim.id)
        covered = [p for s, e, p, _ in tokens if s < claim.end and e > claim.start]
        if claim.direction_span:
            ds, de = claim.direction_span
            covered += [p for s, e, p, _ in tokens if s < de and e > ds]
        rows.append({
            "claim_id": claim.id,
            "b_supported": float(check.verdict == "supported"),
            "b_unsupported": float(check.verdict == "unsupported"),
            "b_unverifiable": float(check.verdict == "unverifiable"),
            "b_slots": float(len(check.slots)),
            "b_has_expected": float(check.expected is not None),
            "a_max": max(covered, default=0.0),
            "a_mean": float(np.mean(covered)) if covered else 0.0,
            "a_any": float(any(p >= 0.5 for p in covered)),
            "kind_percent": float(claim.kind == "percent"),
            "has_direction": float(claim.direction is not None),
        })
    return rows


@dataclass
class Fusion:
    model: object
    calibrator: object | None = None
    features: tuple[str, ...] = FEATURES
    info: dict = field(default_factory=dict)

    @classmethod
    def fit(cls, rows: Sequence[dict], features: tuple[str, ...] = FEATURES) -> "Fusion":
        from sklearn.linear_model import LogisticRegression

        X = np.array([[r[f] for f in features] for r in rows])
        y = np.array([r["label"] for r in rows])
        model = LogisticRegression(max_iter=1000, C=1.0).fit(X, y)
        return cls(model=model, features=features, info={"rows": len(rows), "positive": int(y.sum())})

    def raw(self, rows: Sequence[dict]) -> np.ndarray:
        X = np.array([[r[f] for f in self.features] for r in rows])
        return self.model.predict_proba(X)[:, 1] if len(rows) else np.array([])

    def calibrate(self, rows: Sequence[dict], method: str = "isotonic") -> None:
        """Fit the calibrator on calibration-split claims (never on the rows the model was fitted on)."""
        p = self.raw(rows)
        y = np.array([r["label"] for r in rows])
        if method == "isotonic":
            from sklearn.isotonic import IsotonicRegression

            self.calibrator = IsotonicRegression(out_of_bounds="clip").fit(p, y)
        else:
            from scipy.optimize import minimize_scalar

            logit = np.log(np.clip(p, 1e-6, 1 - 1e-6) / np.clip(1 - p, 1e-6, 1))
            nll = lambda t: -np.mean(y * np.log(1 / (1 + np.exp(-logit / t)) + 1e-12) + (1 - y) * np.log(1 - 1 / (1 + np.exp(-logit / t)) + 1e-12))
            temperature = minimize_scalar(nll, bounds=(0.05, 20), method="bounded").x
            self.calibrator = ("temperature", float(temperature))
        self.info["calibration"] = method

    def claim_probs(self, rows: Sequence[dict]) -> np.ndarray:
        p = self.raw(rows)
        if self.calibrator is None or not len(p):
            return p
        if isinstance(self.calibrator, tuple):
            t = self.calibrator[1]
            logit = np.log(np.clip(p, 1e-6, 1 - 1e-6) / np.clip(1 - p, 1e-6, 1))
            return 1 / (1 + np.exp(-logit / t))
        return self.calibrator.predict(p)

    def item_risk(self, rows: Sequence[dict]) -> float:
        """P(at least one claim is wrong), treating claims as independent; 0.5 if there is nothing to check."""
        if not rows:
            return 0.5
        return float(1 - np.prod(1 - self.claim_probs(rows)))

    def save(self, path: str | Path) -> None:
        with open(path, "wb") as f:
            pickle.dump(self, f)

    @staticmethod
    def load(path: str | Path) -> "Fusion":
        with open(path, "rb") as f:
            return pickle.load(f)


class FusedDetector:
    """Channel B checks + Channel A spans + the fused, calibrated risk, as one detector for the pipeline."""

    def __init__(self, channel_a, fusion: Fusion, channel_b: Callable[[Item], DetectorOutput] | None = None):
        from faithguard.detect import detect

        self.channel_a, self.fusion, self.channel_b = channel_a, fusion, channel_b or detect

    def __call__(self, item: Item) -> DetectorOutput:
        det = self.channel_b(item)
        tokens = self.channel_a.token_probs(item)
        spans: list[Span] = self.channel_a.spans(item)
        risk = self.fusion.item_risk(claim_features(det, tokens))
        return det.model_copy(update={"spans": spans, "risk": risk, "detector": "fused-a+b-v1"})
