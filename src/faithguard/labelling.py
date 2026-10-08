"""Label Studio tasks in, gold labels out, with blinding in between.

Tasks hide which system or generator produced an answer: every item gets an
opaque task key, order is shuffled with a fixed seed, and the key -> item mapping
is written to the gold store side, never into the tasks. Exports are converted
back into GoldLabel records, one per annotator per item.
"""

from __future__ import annotations

import hashlib
import html
import json
import random
from pathlib import Path

from faithguard.gold import GoldLabel, GoldSpan
from faithguard.records import Evidence, Item, Table

SLOT_LABELS = {
    "entity_scope", "metric", "period", "unit", "scale_currency", "sign", "basis", "missing_operand", "value",
}


def table_html(table: Table) -> str:
    rows: dict[int, dict[int, str]] = {}
    labels: dict[int, str] = {}
    headers: dict[int, str] = {}
    for c in table.cells:
        rows.setdefault(c.row, {})[c.col] = c.text
        labels[c.row] = c.row_label
        headers[c.col] = c.column_label
    cols = sorted(headers)
    head = "<tr><th>{}</th>{}</tr>".format(html.escape(table.title), "".join(f"<th>{html.escape(headers[c])}</th>" for c in cols))
    body = "".join(
        "<tr><td>{}</td>{}</tr>".format(html.escape(labels[r]), "".join(f"<td>{html.escape(rows[r].get(c, ''))}</td>" for c in cols))
        for r in sorted(rows)
    )
    return f"<table>{head}{body}</table>"


def evidence_html(evidence: Evidence) -> str:
    parts = [table_html(t) for t in evidence.tables]
    parts += [f"<p>{html.escape(p.text)}</p>" for p in evidence.passages]
    return "".join(parts)


def task_key(item_id: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{item_id}".encode()).hexdigest()[:12]


def build_tasks(items: list[Item], salt: str, seed: int = 7) -> tuple[list[dict], dict[str, str]]:
    """(tasks, key -> item id). The mapping belongs with the gold store, not with the annotators."""
    tasks, mapping = [], {}
    for item in items:
        key = task_key(item.id, salt)
        mapping[key] = item.id
        tasks.append({
            "data": {
                "task_key": key,
                "question": item.question.text,
                "evidence_html": evidence_html(item.evidence),
                "answer": item.answer.text,
            }
        })
    random.Random(seed).shuffle(tasks)
    return tasks, mapping


def write_tasks(items: list[Item], tasks_path: str | Path, mapping_path: str | Path, salt: str) -> int:
    tasks, mapping = build_tasks(items, salt)
    Path(tasks_path).parent.mkdir(parents=True, exist_ok=True)
    Path(mapping_path).parent.mkdir(parents=True, exist_ok=True)
    Path(tasks_path).write_text(json.dumps(tasks, ensure_ascii=False, indent=1), encoding="utf-8")
    Path(mapping_path).write_text(json.dumps(mapping, indent=1, sort_keys=True), encoding="utf-8")
    return len(tasks)


def labels_from_export(export: list[dict], mapping: dict[str, str], target: str = "original") -> list[GoldLabel]:
    """Label Studio JSON export -> GoldLabel per (item, annotator). Skipped or cancelled annotations are dropped."""
    out = []
    for task in export:
        item_id = mapping[task["data"]["task_key"]]
        for ann in task.get("annotations", []):
            if ann.get("was_cancelled"):
                continue
            spans, status, useful, note = [], None, None, ""
            for r in ann.get("result", []):
                value = r.get("value", {})
                if r.get("type") == "labels":
                    label = value["labels"][0]
                    spans.append(GoldSpan(start=value["start"], end=value["end"], slot=label if label in SLOT_LABELS else None))
                elif r.get("from_name") == "status":
                    status = value["choices"][0]
                elif r.get("from_name") == "useful":
                    useful = value["choices"][0] == "useful"
                elif r.get("from_name") == "note":
                    note = " ".join(value.get("text", []))
            if status is None:
                continue  # incomplete annotation
            annotator = str(ann.get("completed_by", {}).get("email") if isinstance(ann.get("completed_by"), dict) else ann.get("completed_by"))
            out.append(GoldLabel(item_id=item_id, target=target, status=status, spans=spans, useful=useful, annotator=annotator, note=note))
    return out
