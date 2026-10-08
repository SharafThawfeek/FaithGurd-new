"""Repairer v0: rule-only COPY and CALCULATE programs, checked by the executor and the gate.

For each claim the rule checker did not support, use the checker's fix: the cell
of the intended metric, entity and period (COPY), or the growth rate or change
computed from the intended cells (CALCULATE). Growth rates built on a changed
number are recomputed too (dependency closure). Claims with no fix get CANNOT_FIX.
One retry drops edits whose cells failed the gate.
"""

from __future__ import annotations

from faithguard.calc import expr
from faithguard.detect.rules import EvidenceIndex
from faithguard.executor import ExecError, execute
from faithguard.records import Calculate, CannotFix, Copy, DetectorOutput, EditProgram, Item, Keep, RepairOutput
from faithguard.repair.gate import gate

NAME = "rules-v0"


def _edit(claim_id: str, fix: str):
    return Copy(claim=claim_id, cell=fix) if isinstance(expr.parse(fix), expr.Ref) else Calculate(claim=claim_id, expr=fix)


def write_program(item: Item, det: DetectorOutput, avoid: frozenset[str] = frozenset()) -> EditProgram:
    edits: dict[str, object] = {}
    changed: set[tuple[str | None, str | None]] = set()
    for claim in det.claims:
        check = det.check(claim.id)
        if check.verdict == "supported":
            edits[claim.id] = Keep(claim=claim.id)
            continue
        if check.fix is None or avoid & set(expr.refs(expr.parse(check.fix))):
            reason = "missing_operand" if "missing_operand" in check.slots or check.verdict == "unverifiable" else "ambiguous_evidence"
            return EditProgram(edits=[CannotFix(reason=reason, claim=claim.id, note=check.note)])
        edits[claim.id] = _edit(claim.id, check.fix)
        if claim.kind in ("amount", "number"):
            changed.add((check.intended.metric, check.intended.entity))

    # Dependency closure: a growth rate or change built on a changed number is recomputed.
    for claim in det.claims:
        check = det.check(claim.id)
        key = (check.intended.metric, check.intended.entity)
        if claim.kind == "percent" and claim.direction and key in changed and isinstance(edits.get(claim.id), Keep):
            if check.relation in ("growth", "diff") and len(check.cells) == 2:
                fn = "growth" if check.relation == "growth" else "diff"
                edits[claim.id] = Calculate(claim=claim.id, expr=f"{fn}({check.cells[0]}, {check.cells[1]})")
    return EditProgram(edits=list(edits.values()))


def repair(item: Item, det: DetectorOutput) -> RepairOutput:
    if det.claims and all(c.verdict == "supported" for c in det.checks):
        return RepairOutput(item_id=item.id, repairer=NAME, status="nothing_to_fix", text=item.answer.text)
    if not det.claims:
        return RepairOutput(item_id=item.id, repairer=NAME, status="cannot_fix", reason="non_numeric: no numbers to repair")
    index = EvidenceIndex(item)
    avoid: frozenset[str] = frozenset()
    last = None
    for attempt in (1, 2):
        program = write_program(item, det, avoid)
        stop = next((e for e in program.edits if isinstance(e, CannotFix)), None)
        if stop is not None:
            return RepairOutput(
                item_id=item.id, repairer=NAME, status="cannot_fix", program=program, attempts=attempt,
                reason=f"{stop.reason}: {stop.note}".rstrip(": "),
            )
        try:
            result = execute(item, det.claims, program)
        except ExecError as err:
            return RepairOutput(item_id=item.id, repairer=NAME, status="gate_failed", program=program, attempts=attempt, reason=str(err))
        verdict = gate(item, det, program, result, index)
        if verdict.passed:
            return RepairOutput(
                item_id=item.id, repairer=NAME, status="repaired", program=program, text=result.text, gate=verdict, attempts=attempt
            )
        last = (program, verdict)
        # Retry once with the failure reason: avoid the cells used by edits that changed the text.
        avoid = avoid | {cell for change in result.changes if change.new != change.old for cell in change.cells}
    program, verdict = last
    return RepairOutput(
        item_id=item.id, repairer=NAME, status="gate_failed", program=program, gate=verdict, attempts=2,
        reason="; ".join(verdict.failures),
    )
