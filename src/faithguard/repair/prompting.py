"""The repair prompt and the parser for the model's edit program.

The prompt shows the evidence with a cell id on every number, the question, and the
answer with each number marked by its claim id. It lists the claims that may be
edited (flagged by the detector, plus anything computed from them) and asks for a
JSON edit program. Unlisted claims are kept as they are.
"""

from __future__ import annotations

import json
import re

from pydantic import ValidationError

from faithguard.focus import FOCUS_ABOVE_ROWS, focus_rows  # noqa: F401 (FOCUS_ABOVE_ROWS re-exported)
from faithguard.records import Claim, DetectorOutput, EditProgram, Evidence, Item

SYSTEM = (
    "You correct wrong numbers in answers about financial reports. Use only the evidence. "
    "Reply with a JSON edit program and nothing else."
)

INSTRUCTIONS = """Write a JSON edit program for the flagged claims. Each edit is one of:
  {"op":"KEEP","claim":"k1"}                                   the claim is right as written
  {"op":"COPY","claim":"k2","cell":"t1r3c1"}                    replace the number with a cell's value
  {"op":"CALCULATE","claim":"k1","expr":"growth(t1r3c1, t1r3c2)"}  replace it with a calculation on cells
  {"op":"CANNOT_FIX","reason":"missing_operand","claim":"k2"}   the evidence lacks what is needed
Expressions use cell ids, numbers, + - * / and the functions growth(now, before) (percent change),
share(part, whole) (percent), ratio, diff(a, b), sum, avg, abs. Direction words such as "rose" or
"fell" are corrected automatically from the sign of a calculation.
Reply only with {"edits": [...]}."""

SCALE_WORDS = {3: "thousands", 6: "millions", 9: "billions"}
MAX_PASSAGE_CHARS = 400
MAX_EVIDENCE_CHARS = 7000


def render_evidence(evidence: Evidence, focus: dict[str, set[int]] | None = None) -> str:
    lines: list[str] = []
    left_out = 0
    for t in evidence.tables:
        rows: dict[int, list] = {}
        for c in t.cells:
            rows.setdefault(c.row, []).append(c)
        shown = sorted(r for r in rows if focus is None or r in focus.get(t.id, set()))
        left_out += len(rows) - len(shown)
        if not shown:
            continue
        unit = f", amounts in {SCALE_WORDS[t.scale]}" if t.scale in SCALE_WORDS else ""
        lines.append(f"Table {t.id}{': ' + t.title if t.title else ''}{unit}")
        for r in shown:
            cells = rows[r]
            label = cells[0].row_label or cells[0].metric or f"row {r}"
            parts = [f"{c.id} {c.column_label}: {c.text}" for c in cells]
            lines.append(f"- {label} | " + " | ".join(parts))
    if left_out:
        lines.append(f"({left_out} other rows of these statements are not shown: only rows related to the answer's numbers and the question.)")
    used = sum(len(x) for x in lines)
    for p in evidence.passages:
        if used > MAX_EVIDENCE_CHARS:
            break
        text = p.text if len(p.text) <= MAX_PASSAGE_CHARS else p.text[:MAX_PASSAGE_CHARS] + "..."
        lines.append(f"[{p.id}] {text}")
        used += len(text)
    return "\n".join(lines)


def mark_claims(text: str, claims: list[Claim]) -> str:
    """'rose 7.0% to Rs. 12,450 million' -> 'rose [k1: 7.0%] to [k2: Rs. 12,450 million]'."""
    out, pos = [], 0
    for c in claims:
        out.append(text[pos : c.start])
        out.append(f"[{c.id}: {text[c.start:c.end]}]")
        pos = c.end
    out.append(text[pos:])
    return "".join(out)


def editable_claims(det: DetectorOutput) -> list[str]:
    """Flagged claims, plus growth rates built on a flagged amount (dependency closure)."""
    flagged = {c.claim_id for c in det.checks if c.verdict != "supported"}
    keys = {(det.check(cid).intended.metric, det.check(cid).intended.entity) for cid in flagged if det.claim(cid).kind in ("amount", "number")}
    for claim in det.claims:
        check = det.check(claim.id)
        if claim.kind == "percent" and claim.direction and (check.intended.metric, check.intended.entity) in keys:
            flagged.add(claim.id)
    return [c.id for c in det.claims if c.id in flagged]


def build_prompt(item: Item, claims: list[Claim], editable: list[str], det: DetectorOutput | None = None) -> str:
    """The repair prompt; with the detector's output, large evidence is focused (focus_rows)."""
    focus = focus_rows(item.evidence, det, item.question.text)
    return (
        f"EVIDENCE\n{render_evidence(item.evidence, focus)}\n\n"
        f"QUESTION\n{item.question.text}\n\n"
        f"ANSWER\n{mark_claims(item.answer.text, claims)}\n\n"
        f"FLAGGED CLAIMS: {', '.join(editable)}\n\n"
        f"{INSTRUCTIONS}"
    )


def program_json(program: EditProgram) -> str:
    """Compact JSON, as the model is trained to write it."""
    edits = []
    for e in program.edits:
        d = e.model_dump(exclude_defaults=False)
        if d.get("note") == "":
            d.pop("note")
        if d.get("claim") is None:
            d.pop("claim", None)
        edits.append(d)
    return json.dumps({"edits": edits}, separators=(",", ":"))


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _first_json_object(text: str) -> str | None:
    start = text.find("{")
    while start != -1:
        depth, in_str, escape = 0, False, False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                escape = (ch == "\\") and not escape
                if ch == '"' and not escape:
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
        start = text.find("{", start + 1)
    return None


def parse_program(text: str) -> EditProgram | None:
    """The first valid edit program in a model's reply, or None."""
    fenced = _FENCE.search(text)
    candidates = [fenced.group(1)] if fenced else []
    candidates.append(text)
    for chunk in candidates:
        raw = _first_json_object(chunk)
        if raw is None:
            stripped = chunk.strip()
            if stripped.startswith("["):
                raw = json.dumps({"edits": json.loads(stripped)}) if _is_json(stripped) else None
        if raw is None:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and "edits" not in data and "op" in data:
            data = {"edits": [data]}
        try:
            return EditProgram.model_validate(data)
        except ValidationError:
            continue
    return None


def _is_json(text: str) -> bool:
    try:
        json.loads(text)
        return True
    except json.JSONDecodeError:
        return False


def json_schema() -> dict:
    """JSON schema of an edit program, for constrained decoding (llama.cpp response_format)."""
    return EditProgram.model_json_schema()
