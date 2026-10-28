"""Outcome models: P(unsafe) and P(fix) from pre-action information.

    P(unsafe)  the chance the original answer is unsafe to send (it contains an unsupported number)
    P(fix)     the chance the repairer returns a safe and useful answer

Both are trained on replay records (every action played out on every item), using
only what is known before any action. LightGBM, on the pre-action features, is the
main model. The challenger (D-096, in place of TabICLv2) is a neural outcome model:
an mmBERT encoder fine-tuned on a GPU on the question, evidence, answer and the same
features as text (faithguard.policy.neural). It is trained on the fit records, with the
tune records for early stopping; like LightGBM it never sees a calibration or test label.
Here it is read back as the probabilities it wrote for every record.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
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


MAKERS = {"lightgbm": _lightgbm}


class Scores:
    """Probabilities a model trained elsewhere wrote for each record (faithguard.train.outcome_model).

    Unlike a fitted classifier it is looked up by item id, so it needs the records, not their features.
    """

    def __init__(self, path: str | Path):
        self.path = str(path)
        self.p: dict[str, tuple[float, float]] = {}
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                self.p[row["item_id"]] = (float(row["p_unsafe"]), float(row["p_fix"]))

    def predict(self, records: Sequence) -> tuple[np.ndarray, np.ndarray]:
        missing = [r.item_id for r in records if r.item_id not in self.p]
        if missing:
            raise ValueError(f"{len(missing)} records have no prediction in {self.path} (first: {missing[0]}); "
                             "it must come from `faithguard outcome-data` on the same controlled-track cache")
        p = np.array([self.p[r.item_id] for r in records], dtype=float).reshape(-1, 2)
        return p[:, 0], p[:, 1]


# Kinds trained on a GPU, and where `faithguard policy` finds their probabilities by default.
PRECOMPUTED = {"neural": "runs/policy/neural/outcome-model/predictions.jsonl"}  # `kaggle_run.py fetch outcome_model`


@dataclass
class OutcomeModels:
    kind: str
    names: list[str]
    unsafe: Any
    fix: Any
    info: dict = field(default_factory=dict)

    def predict(self, records: Sequence) -> tuple[np.ndarray, np.ndarray]:
        if isinstance(self.unsafe, Scores):
            return self.unsafe.predict(records)
        X = matrix(records, self.names)
        return self.unsafe.predict_proba(X)[:, 1], self.fix.predict_proba(X)[:, 1]


def fit(records: Sequence, kind: str = "lightgbm", seed: int = 0, predictions: str | Path | None = None) -> OutcomeModels:
    """Fit both outcome models on these records; for a PRECOMPUTED kind, read the probabilities a GPU run wrote."""
    rows = list(records)
    if kind in PRECOMPUTED:
        path = Path(predictions or PRECOMPUTED[kind])
        if not path.exists():
            raise FileNotFoundError(f"no {kind} predictions at {path}: run the outcome_model notebook and fetch them")
        scores = Scores(path)  # trained on these fit records; predict() checks it covers the records scored
        return OutcomeModels(kind=kind, names=[], unsafe=scores, fix=scores, info={"rows": len(rows), "predictions": str(path)})
    names = feature_names(rows)
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
