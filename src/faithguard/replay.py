"""The replay harness: every action on every item, each outcome scored.

For each item it runs the detector, records the pre-action features and the
policy's choice, then plays out all three actions (send the original, repair,
abstain) and scores each against the gold store. The policy paper trains and
certifies on these records; the flip matrix shows answers repair made worse.
"""

from __future__ import annotations

from typing import Callable, Iterable, Iterator

from faithguard.detect import detect as default_detect
from faithguard.evaluate import flip_matrix, policy_metrics, score_text
from faithguard.gold import GoldStore
from faithguard.policy import ThresholdPolicy, features
from faithguard.records import Action, DetectorOutput, Item, Record, RepairOutput
from faithguard.repair import repair as default_repair


class ReplayRecord(Record):
    item_id: str
    question_id: str
    issuer: str
    split: str | None = None
    error: str | None = None  # injected error, if any
    expected_action: Action | None = None
    features: dict[str, float]
    risk: float
    decision: Action
    outcomes: dict[str, str]  # action -> state
    repair_status: str
    repair_text: str | None = None

    @property
    def final_state(self) -> str:
        return self.outcomes[self.decision]


def replay(
    items: Iterable[Item],
    gold: GoldStore,
    detector: Callable[[Item], DetectorOutput] = default_detect,
    repairer: Callable[[Item, DetectorOutput], RepairOutput] = default_repair,
    policy=None,
) -> Iterator[ReplayRecord]:
    policy = policy or ThresholdPolicy()
    for item in items:
        g = gold.questions[item.question.id]
        det = detector(item)
        decision = policy.decide(item, det)
        rep = repairer(item, det)
        repaired_text = rep.text if rep.status in ("repaired", "nothing_to_fix") else None
        injection = gold.injections.get(item.id)
        yield ReplayRecord(
            item_id=item.id,
            question_id=item.question.id,
            issuer=item.question.issuer,
            split=item.question.split,
            error=injection.error if injection else None,
            expected_action=injection.expected_action if injection else None,
            features=features(item, det),
            risk=det.risk,
            decision=decision.action,
            outcomes={"send": score_text(item.answer.text, g), "repair": score_text(repaired_text, g), "abstain": "abstained"},
            repair_status=rep.status,
            repair_text=repaired_text,
        )


def summary(records: list[ReplayRecord]) -> dict:
    """Headline numbers for a replay: the policy's outcomes, fixed strategies, and the flip matrix."""
    out = {
        "policy": policy_metrics(r.final_state for r in records),
        "always_send": policy_metrics(r.outcomes["send"] for r in records),
        "always_repair": policy_metrics(r.outcomes["repair"] for r in records),
        "flip_matrix": flip_matrix((r.outcomes["send"], r.outcomes["repair"]) for r in records),
    }
    expected = [r for r in records if r.expected_action]
    if expected:
        out["action_accuracy"] = sum(r.decision == r.expected_action for r in expected) / len(expected)
    return out
