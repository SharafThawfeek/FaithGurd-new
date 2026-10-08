"""Training examples for Channel A: answer spans that are wrong, with the slot that is wrong.

Sources (decision D-005 plan, detection paper):
    controlled  injected FinQA/TAT-QA errors; spans are the numbers the gold program edits
                (plus the direction word for sign errors); correct answers give clean negatives
    ragtruth    general human-labelled unsupported spans, no slot
    xbrl        XBRL-mined wrong-context negatives (faithguard.data.xbrl_mining), with slots

Offline code: it reads the gold store, so it never runs at decision time.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Iterator

from faithguard.calc.numbers import find_numbers
from faithguard.claims import extract_claims
from faithguard.detect.channel_a import item_prompt, lettuce_prompt
from faithguard.evaluate.score import claim_matches, claims_with_change
from faithguard.gold import GoldStore
from faithguard.records import Calculate, Copy, Item

ERROR_SLOT = {
    "period": "period", "metric": "metric", "entity": "entity_scope", "scale": "scale_currency",
    "sign": "sign", "basis": "basis",
}


def controlled_spans(item: Item, gold: GoldStore) -> list[tuple[int, int, str | None]] | None:
    injection = gold.injections.get(item.id)
    if injection is None or injection.target_program is None:
        return None
    text = item.answer.text
    claims = {c.id: c for c in extract_claims(text)}
    spans: list[tuple[int, int, str | None]] = []
    if injection.error == "none":
        return spans
    if injection.error == "missing_operand":
        g = gold.questions[item.question.id]
        mentions = {(m.start, m.end): m for m in find_numbers(text)}
        slot = injection.detail or "missing_operand"  # the wrong figure came from another period or line item
        for c, change in claims_with_change(text):
            if not any(claim_matches(c, mentions[(c.start, c.end)], v, change) for v in g.values):
                spans.append((c.start, c.end, slot))
        return spans
    slot = ERROR_SLOT.get(injection.error)
    for edit in injection.target_program.edits:
        if isinstance(edit, (Copy, Calculate)) and edit.claim in claims:
            c = claims[edit.claim]
            spans.append((c.start, c.end, slot))
            if injection.error == "sign" and c.direction_span:
                spans.append((c.direction_span[0], c.direction_span[1], slot))
    return spans


def controlled_examples(items: Iterable[Item], gold: GoldStore) -> Iterator[dict]:
    for item in items:
        spans = controlled_spans(item, gold)
        if spans is None:
            continue
        yield {
            "id": item.id, "source": "controlled", "error": gold.injections[item.id].error,
            "prompt": item_prompt(item), "answer": item.answer.text, "spans": spans,
        }


def ragtruth_examples(root: str | Path, split: str = "train", limit: int | None = None) -> Iterator[dict]:
    from faithguard.data import ragtruth

    for item, label in ragtruth.load(root, split=split, limit=limit):
        yield {
            "id": item.id, "source": "ragtruth", "error": "unsupported" if label.spans else "none",
            "prompt": lettuce_prompt(item.question.text, [p.text for p in item.evidence.passages]),
            "answer": item.answer.text, "spans": [(s.start, s.end, None) for s in label.spans],
        }


def write(path: str | Path, rows: Iterable[dict]) -> dict:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            key = f"{row['source']}:{row['error']}"
            counts[key] = counts.get(key, 0) + 1
    return counts
