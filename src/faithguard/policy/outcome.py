"""Outcome models: P(unsafe) and P(fix) from pre-action features.

    P(unsafe)  the chance the original answer is unsafe to send (it contains an unsupported number)
    P(fix)     the chance the repairer returns a safe and useful answer

Both are trained on replay records (every action played out on every item), using
only the features known before any action. LightGBM is the main model; TabICLv2,
a tabular foundation model, is the challenger (cut-list item 1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np


def targets(records: Sequence) -> tuple[np.ndarray, np.ndarray]:
    y_unsafe = np.array([r.outcomes["send"] == "unsupported" for r in records], dtype=int)
    y_fix = np.array([r.outcomes["repair"] == "supported_useful" for r in records], dtype=int)
    return y_unsafe, y_fix


def feature_names(records: Sequence) -> list[str]:
    names: set[str] = set()
    for r in records:
        names.update(r.features)
    return sorted(names)


def matrix(records: Sequence, names: list[str]) -> np.ndarray:
    return np.array([[float(r.features.get(n, 0.0)) for n in names] for r in records], dtype=float)


class _Constant:
    """Stands in when a training target has a single class."""

    def __init__(self, p: float):
        self.p = p

    def predict_proba(self, X):
        n = len(X)
        return np.column_stack([np.full(n, 1 - self.p), np.full(n, self.p)])


def _lightgbm(seed: int):
    from lightgbm import LGBMClassifier

    return LGBMClassifier(
        n_estimators=300, learning_rate=0.05, num_leaves=15, min_child_samples=20,
        subsample=0.8, subsample_freq=1, colsample_bytree=0.8,
        random_state=seed, deterministic=True, force_row_wise=True, verbose=-1,
    )


def _tabicl(seed: int):
    from tabicl import TabICLClassifier  # optional: pip install -r requirements/challenger.txt

    return TabICLClassifier(random_state=seed)


MAKERS = {"lightgbm": _lightgbm, "tabicl": _tabicl}
MAX_CONTEXT = {"tabicl": 4000}  # in-context learners read their training rows at prediction time


@dataclass
class OutcomeModels:
    kind: str
    names: list[str]
    unsafe: Any
    fix: Any
    info: dict = field(default_factory=dict)

    def predict(self, records: Sequence) -> tuple[np.ndarray, np.ndarray]:
        X = matrix(records, self.names)
        return self.unsafe.predict_proba(X)[:, 1], self.fix.predict_proba(X)[:, 1]


def fit(records: Sequence, kind: str = "lightgbm", seed: int = 0) -> OutcomeModels:
    names = feature_names(records)
    rows = list(records)
    if kind in MAX_CONTEXT and len(rows) > MAX_CONTEXT[kind]:
        rng = np.random.default_rng(seed)
        rows = [rows[i] for i in sorted(rng.choice(len(rows), MAX_CONTEXT[kind], replace=False))]
    X = matrix(rows, names)
    y_unsafe, y_fix = targets(rows)
    models = []
    for y in (y_unsafe, y_fix):
        if y.min() == y.max():
            models.append(_Constant(float(y[0])))
        else:
            m = MAKERS[kind](seed)
            m.fit(X, y)
            models.append(m)
    return OutcomeModels(kind=kind, names=names, unsafe=models[0], fix=models[1], info={"rows": len(rows)})


# ---------------------------------------------------------------------------
# Probability quality
# ---------------------------------------------------------------------------


def brier(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def ece(y: np.ndarray, p: np.ndarray, bins: int = 10) -> float:
    """Expected calibration error with equal-width bins."""
    edges = np.linspace(0, 1, bins + 1)
    total, n = 0.0, len(y)
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (p >= lo) & ((p < hi) if hi < 1 else (p <= hi))
        if mask.any():
            total += mask.sum() / n * abs(p[mask].mean() - y[mask].mean())
    return float(total)


def auroc(y: np.ndarray, p: np.ndarray) -> float | None:
    from sklearn.metrics import roc_auc_score

    return float(roc_auc_score(y, p)) if 0 < y.sum() < len(y) else None
