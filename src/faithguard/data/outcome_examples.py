"""Inputs for the neural outcome model (D-096): one row per controlled-track replay record.

Each row holds the record's track split, the text pair the encoder reads (faithguard.policy.neural)
and, for the fit and tune splits only, the targets: the original answer is unsupported, and repair
returns a supported, useful answer. Calibration and test rows carry no targets, so the GPU run that
trains on these rows cannot see the labels the policy is certified and reported on.

Offline code: the targets come from replay outcomes, scored against the gold store.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Iterator, Sequence

from faithguard.records import Item

LABELLED = ("fit", "tune")


def rows(items: Iterable[Item], records: Sequence) -> Iterator[dict]:
    from faithguard.detect import detect
    from faithguard.focus import focus_rows
    from faithguard.policy.neural import inputs

    by_id = {r.item_id: r for r in records}
    for item in items:
        r = by_id.get(item.id)
        if r is None:
            continue
        focus = focus_rows(item.evidence, detect(item), item.question.text)  # the rule checker, as in the replay
        row = {"item_id": r.item_id, "split": r.split, "text": inputs(item, r.features, focus)}
        if r.split in LABELLED:
            row["labels"] = [int(r.outcomes["send"] == "unsupported"), int(r.outcomes["repair"] == "supported_useful")]
        yield row


def write(path: str | Path, rows: Iterable[dict]) -> dict[str, int]:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            counts[row["split"]] = counts.get(row["split"], 0) + 1
    return counts
