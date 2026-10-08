"""Repair evaluation: correction against harm, for any repairer.

Per item, the original answer and the repaired one are scored against gold:

    correction rate   wrong originals turned into fully supported, useful answers
    new-error rate    sent repairs containing a wrong number the original did not have
    damage rate       correct originals made wrong
    abstention        repairs withheld (CANNOT_FIX or gate failure); right for missing-operand items
    valid programs    model replies that parsed into an edit program (model repairers)
"""

from __future__ import annotations

import time
from collections import Counter, defaultdict
from typing import Callable, Iterable

from faithguard.detect import detect as default_detect
from faithguard.evaluate.score import score_text, wrong_numbers
from faithguard.gold import GoldStore
from faithguard.records import DetectorOutput, Item, RepairOutput


def evaluate_repairer(
    items: Iterable[Item], gold: GoldStore, repairer: Callable[[Item, DetectorOutput], RepairOutput],
    detector: Callable[[Item], DetectorOutput] = default_detect,
) -> dict:
    rows = []
    t0 = time.time()
    for item in items:
        g = gold.questions[item.question.id]
        injection = gold.injections.get(item.id)
        det = detector(item)
        out = repairer(item, det)
        sent = out.text if out.status in ("repaired", "nothing_to_fix") else None
        before_wrong = set(wrong_numbers(item.answer.text, g))
        after_wrong = wrong_numbers(sent, g)
        rows.append({
            "item_id": item.id,
            "error": injection.error if injection else None,
            "before": score_text(item.answer.text, g),
            "after": score_text(sent, g),
            "status": out.status,
            "attempts": out.attempts,
            "new_errors": [w for w in after_wrong if w not in before_wrong],
            "program": out.program is not None,
        })
    seconds = time.time() - t0
    return {"summary": summarise(rows), "by_error": by_error(rows), "seconds": round(seconds, 1), "rows": rows}


def summarise(rows: list[dict]) -> dict:
    n = len(rows)
    needs = [r for r in rows if r["before"] == "unsupported"]
    clean = [r for r in rows if r["before"] != "unsupported"]
    sent = [r for r in rows if r["after"] != "abstained"]
    attempted = [r for r in rows if r["status"] != "nothing_to_fix"]
    return {
        "items": n,
        "needing_repair": len(needs),
        "correction_rate": _share(needs, lambda r: r["after"] == "supported_useful"),
        "abstained_when_needed": _share(needs, lambda r: r["after"] == "abstained"),
        "still_wrong_when_sent": _share([r for r in needs if r["after"] != "abstained"], lambda r: r["after"] == "unsupported"),
        "new_error_rate": _share(sent, lambda r: bool(r["new_errors"])),
        "damage_rate": _share(clean, lambda r: r["after"] == "unsupported"),
        "valid_program_rate": _share(attempted, lambda r: r["program"] or r["status"] == "cannot_fix"),
        "gate_pass_rate": _share([r for r in attempted if r["status"] in ("repaired", "gate_failed")], lambda r: r["status"] == "repaired"),
        "mean_attempts": round(sum(r["attempts"] for r in attempted) / len(attempted), 3) if attempted else 0.0,
        "status": dict(Counter(r["status"] for r in rows)),
    }


def by_error(rows: list[dict]) -> dict:
    groups = defaultdict(list)
    for r in rows:
        groups[r["error"]].append(r)
    return {e: summarise(rs) for e, rs in sorted(groups.items(), key=lambda kv: str(kv[0]))}


def _share(rows: list[dict], pred) -> float | None:
    return round(sum(1 for r in rows if pred(r)) / len(rows), 4) if rows else None


def report(name: str, result: dict) -> str:
    s = result["summary"]
    pct = lambda x: "–" if x is None else f"{100 * x:.1f}%"
    lines = [
        f"# Repair evaluation: {name}",
        "",
        f"{s['items']:,} items ({s['needing_repair']:,} with a wrong original). Run time {result['seconds']} s.",
        "",
        "| Measure | Value |",
        "| --- | --- |",
        f"| Correction rate (wrong originals made fully correct) | {pct(s['correction_rate'])} |",
        f"| Withheld when a fix was needed | {pct(s['abstained_when_needed'])} |",
        f"| Still wrong when sent | {pct(s['still_wrong_when_sent'])} |",
        f"| New-error rate (sent repairs with a new wrong number) | {pct(s['new_error_rate'])} |",
        f"| Damage rate (correct originals made wrong) | {pct(s['damage_rate'])} |",
        f"| Valid programs | {pct(s['valid_program_rate'])} |",
        f"| Gate pass rate | {pct(s['gate_pass_rate'])} |",
        f"| Mean attempts | {s['mean_attempts']} |",
        "",
        "| Planted error | Items | Correction | Withheld | New errors | Damage |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for e, m in result["by_error"].items():
        lines.append(f"| {e} | {m['items']} | {pct(m['correction_rate'])} | {pct(m['abstained_when_needed'])} | {pct(m['new_error_rate'])} | {pct(m['damage_rate'])} |")
    return "\n".join(lines) + "\n"
