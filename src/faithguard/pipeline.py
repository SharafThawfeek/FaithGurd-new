"""The end-to-end pipeline: detect, decide, then send, repair or abstain.

    question + evidence + answer -> detector -> policy -> send original
                                                       -> repair -> gate -> send fixed answer
                                                       -> abstain with evidence and a reason

Each stage is a plain function or object, so phase-4 components (learned detector,
outcome-aware policy, trained repairer) drop in without changing this file.
"""

from __future__ import annotations

from typing import Callable, Protocol

from faithguard.calc.numbers import default_style, render
from faithguard.detect import detect
from faithguard.policy import ThresholdPolicy
from faithguard.records import Decision, DetectorOutput, FinalOutput, Item, RepairOutput
from faithguard.repair import repair

Detector = Callable[[Item], DetectorOutput]
Repairer = Callable[[Item, DetectorOutput], RepairOutput]


class Policy(Protocol):
    name: str

    def decide(self, item: Item, det: DetectorOutput) -> Decision: ...


def evidence_note(item: Item, cell_ids: list[str]) -> str:
    """A short, human-readable list of the cells behind a decision."""
    parts = []
    for cell_id in cell_ids:
        cell = item.evidence.cell(cell_id)
        label = " ".join(x for x in (cell.entity, cell.metric, cell.period) if x) or f"{cell.row_label} {cell.column_label}"
        shown = render(cell.value, default_style(cell.kind if cell.kind != "text" else "amount", cell.scale, cell.currency, 0)) if cell.value is not None else cell.text
        parts.append(f"{label}: {shown}")
    return "; ".join(parts)


def run(
    item: Item,
    detector: Detector = detect,
    policy: Policy | None = None,
    repairer: Repairer = repair,
) -> FinalOutput:
    policy = policy or ThresholdPolicy()
    det = detector(item)
    decision = policy.decide(item, det)
    traced = [cell for check in det.checks for cell in check.cells]

    if decision.action == "send":
        return FinalOutput(item_id=item.id, action="send", text=item.answer.text, reason=decision.reason, evidence_cells=traced, detector=det, decision=decision)

    rep = None
    if decision.action == "repair":
        rep = repairer(item, det)
        if rep.status in ("repaired", "nothing_to_fix"):
            return FinalOutput(
                item_id=item.id, action="repair", text=rep.text, reason=f"fixed: {decision.reason}",
                evidence_cells=traced, detector=det, decision=decision, repair=rep,
            )
        reason = f"could not fix safely ({rep.reason})"
    else:
        reason = decision.reason

    shown = [c for check in det.checks if check.verdict != "supported" for c in check.cells]
    note = evidence_note(item, shown) if shown else ""
    return FinalOutput(
        item_id=item.id, action="abstain", text=None, reason=reason + (f". The report shows: {note}" if note else ""),
        evidence_cells=shown, detector=det, decision=decision, repair=rep,
    )
