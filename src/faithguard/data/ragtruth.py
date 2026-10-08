"""RAGTruth (Niu et al., 2024; MIT licence) as Items with span labels.

General-domain answers from six models with human-marked unsupported spans. Used
in phase 4 for Channel A's span head; here it is only loaded and checked.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

from faithguard.gold import GoldLabel, GoldSpan
from faithguard.records import Answer, Evidence, Item, Passage, Question


def _context(task: str, info) -> tuple[str, str]:
    """(question text, source text) for each RAGTruth task type."""
    if task == "QA" and isinstance(info, dict):
        return info.get("question", ""), info.get("passages", "")
    if task == "Summary":
        return "Summarise the passage.", info if isinstance(info, str) else json.dumps(info)
    return "Describe the structured data.", json.dumps(info, ensure_ascii=False)


def load(root: str | Path, split: str | None = None, limit: int | None = None) -> Iterator[tuple[Item, GoldLabel]]:
    root = Path(root)
    sources = {}
    with open(root / "source_info.jsonl", encoding="utf-8") as f:
        for line in f:
            s = json.loads(line)
            sources[s["source_id"]] = s
    n = 0
    with open(root / "response.jsonl", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if split and r["split"] != split:
                continue
            if limit is not None and n >= limit:
                return
            src = sources[r["source_id"]]
            question_text, source_text = _context(src["task_type"], src["source_info"])
            item_id = f"ragtruth:{r['id']}"
            item = Item(
                id=item_id,
                question=Question(id=f"ragtruth:{r['source_id']}", issuer=f"ragtruth:{r['source_id']}", text=question_text or "", question_type="narrative", source="ragtruth"),
                evidence=Evidence(passages=[Passage(id="p1", text=source_text)]),
                answer=Answer(id=item_id, question_id=f"ragtruth:{r['source_id']}", generator=r["model"], text=r["response"], settings={"temperature": r.get("temperature")}),
            )
            spans = [GoldSpan(start=lab["start"], end=lab["end"]) for lab in r["labels"]]
            label = GoldLabel(item_id=item_id, status="incorrect" if spans else "correct", spans=spans, annotator="ragtruth", note=src["task_type"])
            n += 1
            yield item, label
