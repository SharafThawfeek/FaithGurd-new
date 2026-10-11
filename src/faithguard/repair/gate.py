"""The hard gate: a repaired answer is only released if it passes every check.

    provenance  each copied or calculated number comes from cells of the intended metric, entity and period
                (a share or ratio may also use a line item the question names)
    closure     growth rates and changes built on a changed number were recomputed too
    envelope    nothing outside the edited claims (and their direction words) changed
    recheck     the rule checker supports every claim in the repaired answer
    relevance   the repaired answer still answers the question
"""

from __future__ import annotations

from faithguard.calc import expr
from faithguard.detect.rules import EvidenceIndex, context_slots, detect
from faithguard.executor import ExecResult, apply
from faithguard.records import Calculate, Context, Copy, DetectorOutput, EditProgram, GateResult, Item

# Functions whose operands are two different line items by nature (a part and its whole, or two amounts)
TWO_ITEM_FUNCTIONS = ("share", "ratio")


def relates_two_items(expression: str) -> bool:
    """True for share(part, whole) or ratio(a, b) at the top of the expression."""
    node = expr.parse(expression)
    return isinstance(node, expr.Call) and node.fn in TWO_ITEM_FUNCTIONS


def gate(item: Item, det: DetectorOutput, program: EditProgram, result: ExecResult, index: EvidenceIndex) -> GateResult:
    failures: list[str] = []
    edited = {e.claim: e for e in program.edits if isinstance(e, (Copy, Calculate))}
    named = index.vocab.metrics_named(item.question.text)

    for claim_id, edit in edited.items():
        intended = det.check(claim_id).intended
        cell_ids = [edit.cell] if isinstance(edit, Copy) else expr.refs(expr.parse(edit.expr))
        two_items = isinstance(edit, Calculate) and relates_two_items(edit.expr)
        for cell_id in cell_ids:
            cell = item.evidence.cell(cell_id)
            found = Context(metric=cell.metric, entity=cell.entity, period=None if isinstance(edit, Calculate) else cell.period)
            wrong = context_slots(found, intended)
            if two_items and cell.metric in named:
                # a share or ratio may use the other line item the question names: the claim's own context
                # names only one of the two (natural answers put the share beside either amount)
                wrong.discard("metric")
            if wrong:
                failures.append(f"provenance: {claim_id} uses {cell_id} ({', '.join(sorted(wrong))})")

    changed_amounts = {
        (det.check(c.claim_id).intended.metric, det.check(c.claim_id).intended.entity)
        for c in result.changes
        if det.claim(c.claim_id).kind in ("amount", "number") and c.new != c.old
    }
    for claim in det.claims:
        check = det.check(claim.id)
        key = (check.intended.metric, check.intended.entity)
        if claim.kind == "percent" and claim.direction and key in changed_amounts and claim.id not in edited:
            failures.append(f"closure: {claim.id} depends on a changed number but was not recomputed")

    allowed = {(c.start, c.end) for c in det.claims} | {c.direction_span for c in det.claims if c.direction_span}
    outside = [(s, e) for s, e, _ in result.replacements if (s, e) not in allowed]
    if outside or apply(item.answer.text, result.replacements) != result.text:
        failures.append("envelope: text outside the edited claims changed")

    repaired = item.model_copy(update={"answer": item.answer.model_copy(update={"text": result.text})})
    after = detect(repaired)
    bad = [c for c in after.checks if c.verdict != "supported"]
    if bad:
        failures.append("recheck: " + "; ".join(f"{c.claim_id} {c.verdict} {','.join(c.slots)}" for c in bad))
    if det.answers_question and not after.answers_question:
        failures.append("relevance: the repaired answer no longer answers the question")
    return GateResult(passed=not failures, failures=failures)
