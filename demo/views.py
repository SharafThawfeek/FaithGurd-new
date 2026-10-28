"""What the demo shows for one answer: plain JSON for each step (Catch, Control, Correct, Output).

Everything here is computed from the pipeline's own records; nothing reads gold. The trained models'
outputs (Channel A's token probabilities, the trained repairer's program) are passed in, whether they
were computed live, earlier on this laptop, or on Kaggle, with a label saying which.
"""

from __future__ import annotations

from collections import Counter
from decimal import Decimal

from faithguard.calc import expr
from faithguard.calc.numbers import render
from faithguard.claims import mention_of
from faithguard.detect.channel_a import SLOT_NAMES
from faithguard.detect.rules import EvidenceIndex
from faithguard.executor import ExecError, execute
from faithguard.focus import focus_rows
from faithguard.policy import ThresholdPolicy, features
from faithguard.records import Calculate, CannotFix, Copy, DetectorOutput, EditProgram, FinalOutput, Item, Keep, RepairOutput
from faithguard.repair.gate import gate

GATE_CHECKS = [
    ("provenance", "each new number comes from cells of the intended metric, entity and period"),
    ("closure", "growth rates built on a changed number were recomputed too"),
    ("envelope", "nothing outside the edited numbers changed"),
    ("recheck", "the rule checker supports every number in the repaired answer"),
    ("relevance", "the repaired answer still answers the question"),
]


def _num(x) -> float | None:
    return None if x is None else float(x)


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------


def evidence_view(item: Item, det: DetectorOutput) -> dict:
    """Tables as grids, with the rows the learned models see (focus) marked."""
    focus = focus_rows(item.evidence, det, item.question.text)
    tables = []
    for t in item.evidence.tables:
        cols = sorted({c.col for c in t.cells})
        header = {}
        rows: dict[int, dict] = {}
        for c in t.cells:
            header.setdefault(c.col, c.column_label)
            row = rows.setdefault(c.row, {"row": c.row, "label": c.row_label or c.metric or "", "cells": {}})
            row["cells"][c.col] = {"id": c.id, "text": c.text}
        tables.append({
            "id": t.id, "title": t.title, "page": t.page, "source": t.source, "scale": t.scale, "currency": t.currency,
            "columns": [{"col": col, "label": header.get(col, "")} for col in cols],
            "rows": [{**rows[r], "cells": [rows[r]["cells"].get(col) for col in cols],
                      "focus": focus is None or r in focus.get(t.id, set())} for r in sorted(rows)],
        })
    return {"tables": tables, "passages": [{"id": p.id, "text": p.text, "page": p.page} for p in item.evidence.passages],
            "focused": focus is not None}


def cell_label(item: Item, cell_id: str) -> str:
    """'Group, profit after tax, 2025: 14,212,560' for a cell; the passage start for a text passage."""
    passage = next((p for p in item.evidence.passages if p.id == cell_id), None)
    if passage is not None:
        return f"text passage {cell_id}: {passage.text[:80]}"
    try:
        c = item.evidence.cell(cell_id)
    except KeyError:
        return cell_id
    where = ", ".join(x for x in (c.row_label or c.metric, c.column_label) if x)
    return f"{where}: {c.text}"


# ---------------------------------------------------------------------------
# 1. Catch
# ---------------------------------------------------------------------------


def _refs(expression: str | None) -> list[str]:
    if not expression:
        return []
    try:
        return expr.refs(expr.parse(expression))
    except Exception:
        return []


COMPUTED = ("growth", "diff", "share", "ratio")
MISREAD = {"scale_currency": "the right cell, read at the wrong scale", "sign": "the right cells, but the wrong direction",
           "unit": "the right cell, in the wrong unit"}


def claim_views(item: Item, det: DetectorOutput) -> list[dict]:
    """Each claim with the cells the question asks for (green) and the cells its number matched (red).

    For a scale, sign or unit error they are the same cells, read wrongly. For an unsupported number the
    checker reports the closest match it found, which for a computed value can be a coincidence."""
    out = []
    for claim in det.claims:
        check = det.check(claim.id)
        slots = set(check.slots)
        if check.verdict == "supported":
            asked, came_from = list(check.cells), []
        else:
            asked = _refs(check.fix)
            if not asked and check.cells and slots and slots <= {"value", *MISREAD}:
                asked = list(check.cells)  # the right cells, read wrongly
            # with only a "value" slot, check.cells are the intended cells, not where the number came from
            came_from = [] if slots == {"value"} else list(check.cells)
        same_cell = bool(came_from) and set(came_from) <= set(asked)
        expected = None
        if check.expected is not None and claim.kind != "ratio":
            try:
                value = check.expected
                shown = render(abs(value) if claim.direction is not None else value, mention_of(claim, item.answer.text).style)
                expected = (f"a {'fall' if value < 0 else 'rise'} of {shown}" if claim.direction is not None else shown)
            except Exception:
                expected = str(check.expected)
        out.append({
            "id": claim.id, "start": claim.start, "end": claim.end, "text": claim.text, "kind": claim.kind,
            "direction": claim.direction, "direction_span": list(claim.direction_span) if claim.direction_span else None,
            "verdict": check.verdict, "slots": list(check.slots), "intended": check.intended.model_dump(),
            "relation": check.relation, "fix": check.fix, "expected": expected, "note": check.note,
            "cells": list(check.cells), "asked": asked, "came_from": came_from, "same_cell": same_cell,
            "misread": next((text for slot, text in MISREAD.items() if slot in slots), None) if same_cell else None,
            # a computed value over other line items (or when the metric is not recognised) may match by chance
            "loose_match": bool(came_from) and not same_cell and check.relation in COMPUTED
                           and ("metric" in slots or check.intended.metric is None),
            "missing": "missing_operand" in slots,
            "cell_labels": {c: cell_label(item, c) for c in {*check.cells, *asked}},
        })
    return out


def channel_a_view(item: Item, tokens: list | None, source: str | None, threshold: float = 0.5, note: str = "",
                   det: DetectorOutput | None = None) -> dict:
    """Per-token P(unsupported) and slot; spans are runs of tokens at or above the threshold, widened to the
    whole number when they touch one (a span over ",627,060,300" reads as the claim it belongs to)."""
    if tokens is None:
        return {"source": None, "note": note}
    tokens = [[int(s), int(e), float(p), SLOT_NAMES[k] if isinstance(k, int) else k] for s, e, p, k in tokens]
    claims = [(c.start, c.end) for c in det.claims] if det is not None else []
    spans, current = [], []
    for tok in tokens + [[10**9, 10**9, 0.0, None]]:
        if tok[2] >= threshold and (not current or tok[0] - current[-1][1] <= 1):
            current.append(tok)
            continue
        if current:
            slots = [t[3] for t in current]
            start, end = current[0][0], current[-1][1]
            for a, b in claims:
                if start < b and end > a:
                    start, end = min(start, a), max(end, b)
            text = item.answer.text
            while start < end and text[start].isspace():
                start += 1
            while end > start and text[end - 1].isspace():
                end -= 1
            span = {"start": start, "end": end, "score": max(t[2] for t in current),
                    "slot": Counter(slots).most_common(1)[0][0], "text": item.answer.text[start:end]}
            if spans and spans[-1]["start"] == start and spans[-1]["end"] == end:
                spans[-1]["score"] = max(spans[-1]["score"], span["score"])
            else:
                spans.append(span)
        current = [tok] if tok[2] >= threshold else []
    return {"source": source, "tokens": tokens, "spans": spans, "threshold": threshold, "note": note}


def catch_view(item: Item, det: DetectorOutput, channel_a: dict) -> dict:
    return {"claims": claim_views(item, det), "risk": det.risk, "answers_question": det.answers_question,
            "detector": det.detector, "channel_a": channel_a}


# ---------------------------------------------------------------------------
# 2. Control
# ---------------------------------------------------------------------------

SHOWN_FEATURES = [
    ("risk", "Channel B risk"), ("n_claims", "numbers in the answer"), ("n_supported", "supported"),
    ("n_unsupported", "unsupported"), ("n_unverifiable", "unverifiable"), ("missing_operands", "missing operands"),
    ("evidence_sufficient", "evidence holds every fix"), ("answers_question", "answers the question"),
    ("n_percent_claims", "percentages"), ("n_directional_claims", "with a direction word"), ("n_cells", "evidence cells"),
]


def control_view(item: Item, det: DetectorOutput, final: FinalOutput, outcome_policy, certificate: dict) -> dict:
    f = features(item, det)
    shown = [{"name": n, "label": label, "value": f[n]} for n, label in SHOWN_FEATURES]
    shown += [{"name": n, "label": f"failing slot: {n[5:]}", "value": v} for n, v in f.items() if n.startswith("slot_") and v]
    shown += [{"name": n, "label": "question type", "value": n[6:]} for n, v in f.items() if n.startswith("qtype_") and v]
    baseline = ThresholdPolicy().decide(item, det)
    view = {
        "features": shown, "action": final.decision.action, "reason": final.decision.reason, "policy": final.decision.policy,
        "baseline": {"name": baseline.policy, "action": baseline.action, "reason": baseline.reason},
        "certificate": certificate,
    }
    if outcome_policy is not None:
        p_unsafe, p_fix = outcome_policy.scores(item, det)
        view["outcome"] = {"p_unsafe": p_unsafe, "p_fix": p_fix, "tau_send": outcome_policy.tau_send, "tau_fix": outcome_policy.tau_fix,
                           "source": "live"}
    return view


# ---------------------------------------------------------------------------
# 3. Correct
# ---------------------------------------------------------------------------


def edit_view(edit) -> dict:
    if isinstance(edit, Keep):
        return {"op": "KEEP", "claim": edit.claim, "text": f"KEEP {edit.claim}"}
    if isinstance(edit, Copy):
        return {"op": "COPY", "claim": edit.claim, "cells": [edit.cell], "text": f"COPY {edit.claim} ← {edit.cell}"}
    if isinstance(edit, Calculate):
        return {"op": "CALCULATE", "claim": edit.claim, "cells": _refs(edit.expr), "text": f"CALCULATE {edit.claim} = {edit.expr}"}
    if isinstance(edit, CannotFix):
        return {"op": "CANNOT_FIX", "claim": edit.claim, "reason": edit.reason, "note": edit.note,
                "text": f"CANNOT_FIX {edit.claim or ''} ({edit.reason})".replace("  ", " ")}
    return {"op": "?", "text": str(edit)}


def program_check(item: Item, det: DetectorOutput, program: EditProgram | None) -> dict:
    """Run a program through the executor and the hard gate again, to show each check and the new numbers' cells."""
    if program is None:
        return {"ran": False}
    if any(isinstance(e, CannotFix) for e in program.edits):
        return {"ran": False, "cannot_fix": True}
    try:
        result = execute(item, det.claims, program)
    except (ExecError, KeyError, ValueError) as err:
        return {"ran": True, "executor_error": str(err)}
    verdict = gate(item, det, program, result, EvidenceIndex(item))
    checks = []
    for name, about in GATE_CHECKS:
        failures = [f for f in verdict.failures if f.startswith(name)]
        checks.append({"name": name, "about": about, "passed": not failures, "detail": "; ".join(failures)})
    # where each new number sits in the repaired text; a corrected direction word takes its claim's cells
    changes, offset = [], 0
    by_claim = {c.claim_id: c for c in result.changes}
    direction_of = {tuple(c.direction_span): c.id for c in det.claims if c.direction_span}
    for start, end, new in sorted(result.replacements):
        change = next((c for c in result.changes if c.start == start and c.end == end), None)
        owner = change.claim_id if change else direction_of.get((start, end))
        cells = by_claim[owner].cells if owner in by_claim else []
        changes.append({"start": start + offset, "end": start + offset + len(new), "old": item.answer.text[start:end], "new": new,
                        "claim": owner, "cells": cells, "cell_labels": {c: cell_label(item, c) for c in cells},
                        "direction_word": change is None})
        offset += len(new) - (end - start)
    unchanged = [{"claim": c.claim_id, "cells": c.cells} for c in by_claim.values() if c.new == c.old]
    return {"ran": True, "passed": verdict.passed, "checks": checks, "text": result.text, "changes": changes, "unchanged": unchanged}


REASONS = {
    "missing_operand": "the evidence holds no value for what this number is about, so it can be neither confirmed nor computed",
    "ambiguous_evidence": "the rules cannot tell which cells the question needs, and they do not guess",
    "non_numeric": "the answer has no number to repair",
    "conflicting_evidence": "the evidence disagrees with itself",
    "gate_failed": "no program passed the hard gate",
}


def report_rows(item: Item, limit: int = 12) -> list[str]:
    """The line items the evidence does hold, for an abstention that has no cell to point to."""
    seen: list[str] = []
    for c in item.evidence.cells():
        label = c.row_label or c.metric or ""
        if label and label not in seen:
            seen.append(label)
    return seen[:limit] + ([f"… {len(seen) - limit} more"] if len(seen) > limit else [])


def repair_view(item: Item, det: DetectorOutput, rep: RepairOutput | None, source: str, label: str) -> dict | None:
    if rep is None:
        return None
    view = {"source": source, "label": label, "repairer": rep.repairer, "status": rep.status, "reason": rep.reason,
            "attempts": rep.attempts, "text": rep.text,
            "program": [edit_view(e) for e in rep.program.edits] if rep.program else []}
    stop = next((e for e in (rep.program.edits if rep.program else []) if isinstance(e, CannotFix)), None)
    if stop is not None:
        claim = next((c for c in det.claims if c.id == stop.claim), None)
        check = det.check(claim.id) if claim else None
        cells = list(check.cells) if check else []
        ctx = check.intended if check else None
        view["cannot_fix"] = {
            "reason": stop.reason, "explain": REASONS.get(stop.reason, ""), "claim": stop.claim,
            "claim_text": claim.text if claim else None,
            "about": " · ".join(x for x in (ctx.entity, ctx.metric, ctx.period) if x) if ctx else "",
            "note": "" if stop.note.startswith("traced to") else stop.note,
            "cells": cells, "cell_labels": {c: cell_label(item, c) for c in cells},
            "report_rows": [] if cells else report_rows(item),
        }
    if rep.status in ("repaired", "gate_failed"):
        view["check"] = program_check(item, det, rep.program)
    return view


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def output_view(item: Item, final: FinalOutput) -> dict:
    """What the user sees, with the cells behind each number of the text sent.

    For a repaired answer these are the cells each edit used (and the traced cells of the numbers kept), not
    the cells the original, wrong numbers matched, which is what FinalOutput.evidence_cells holds."""
    det = final.detector
    cells = list(dict.fromkeys(final.evidence_cells))
    if final.action == "repair" and final.repair and final.repair.program:
        try:
            used = {c.claim_id: c.cells for c in execute(item, det.claims, final.repair.program).changes}
        except (ExecError, KeyError, ValueError):
            used = {}
        cells = []
        for claim in det.claims:
            for c in used.get(claim.id, det.check(claim.id).cells):
                if c not in cells:
                    cells.append(c)
    return {"action": final.action, "text": final.text, "reason": final.reason, "changed": final.text not in (None, item.answer.text),
            "evidence_cells": cells, "cell_labels": {c: cell_label(item, c) for c in cells},
            "report_rows": report_rows(item) if final.action == "abstain" and not cells else []}


def jsonable(x):
    """Decimals and tuples to plain JSON values."""
    if isinstance(x, Decimal):
        return float(x)
    if isinstance(x, dict):
        return {k: jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [jsonable(v) for v in x]
    return x
