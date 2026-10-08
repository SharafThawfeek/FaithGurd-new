"""The outcome-aware policy as used in the pipeline: fitted models plus certified thresholds.

    send the original   if P(unsafe) < tau_send
    repair              else if P(fix) > tau_fix
    abstain             otherwise

Load it from the bundle that `faithguard policy` saves, then pass it to pipeline.run.
"""

from __future__ import annotations

import pickle
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from faithguard.policy.features import features
from faithguard.records import Decision, DetectorOutput, Item


def parse_setting(name: str) -> tuple[float, float]:
    """'send<0.005,fix>0.5' -> (0.005, 0.5)."""
    m = re.fullmatch(r"send<([\d.]+),fix>([\d.]+)", name)
    if not m:
        raise ValueError(f"not an outcome-aware setting: {name}")
    return float(m.group(1)), float(m.group(2))


@dataclass
class OutcomeAwarePolicy:
    names: list[str]
    unsafe_model: object
    fix_model: object
    tau_send: float
    tau_fix: float
    certificate: dict
    name: str = "outcome-aware-v1"

    def scores(self, item: Item, det: DetectorOutput) -> tuple[float, float]:
        f = features(item, det)
        X = np.array([[float(f.get(n, 0.0)) for n in self.names]])
        return float(self.unsafe_model.predict_proba(X)[0, 1]), float(self.fix_model.predict_proba(X)[0, 1])

    def decide(self, item: Item, det: DetectorOutput) -> Decision:
        p_unsafe, p_fix = self.scores(item, det)
        scores = {"p_unsafe": p_unsafe, "p_fix": p_fix, "risk": det.risk}
        if p_unsafe < self.tau_send:
            return Decision(item_id=item.id, policy=self.name, action="send", reason=f"P(unsafe) {p_unsafe:.3f} below {self.tau_send}", scores=scores)
        if p_fix > self.tau_fix:
            return Decision(item_id=item.id, policy=self.name, action="repair", reason=f"P(fix) {p_fix:.3f} above {self.tau_fix}", scores=scores)
        return Decision(item_id=item.id, policy=self.name, action="abstain", reason="neither sending nor repairing is safe enough", scores=scores)

    def save(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self, f)

    @staticmethod
    def load(path: str | Path) -> "OutcomeAwarePolicy":
        with open(path, "rb") as f:
            return pickle.load(f)
