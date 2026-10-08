"""Policy v0: a plain risk threshold.

Send the original if the detector's risk is below the threshold; otherwise repair
if the evidence holds a value for every failing claim; otherwise abstain with the
evidence and a reason. Whether the answer addresses the question is a feature for
the learned policy, not a gate here: correct numbers are never unsafe to send. The outcome-aware
LightGBM policy (phase 4) replaces this and is compared against it.
"""

from __future__ import annotations

from dataclasses import dataclass

from faithguard.policy.features import features
from faithguard.records import Decision, DetectorOutput, Item


@dataclass
class ThresholdPolicy:
    send_below: float = 0.25
    name: str = "threshold-v0"

    def decide(self, item: Item, det: DetectorOutput) -> Decision:
        f = features(item, det)
        scores = {"risk": det.risk, "evidence_sufficient": f["evidence_sufficient"]}
        if det.risk < self.send_below and det.claims:
            return Decision(item_id=item.id, policy=self.name, action="send", reason="every number traced to the evidence", scores=scores)
        if f["evidence_sufficient"]:
            return Decision(item_id=item.id, policy=self.name, action="repair", reason="the evidence holds the correct values", scores=scores)
        if not det.claims:
            reason = "no checkable number in the answer"
        elif f["missing_operands"]:
            reason = "the evidence lacks a value the answer needs"
        else:
            reason = "no rule can confirm or fix this answer"
        return Decision(item_id=item.id, policy=self.name, action="abstain", reason=reason, scores=scores)
