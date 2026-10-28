"""The Results screen: the committed development tables, read from runs/ at run time."""

from __future__ import annotations

import json
from pathlib import Path

DETECTORS = [  # folder under runs/detector/kaggle, label
    ("base-hhem", "HHEM (off the shelf)"), ("base-granite", "Granite Guardian (off the shelf)"),
    ("base-lettuce-v1", "LettuceDetect v1 (off the shelf)"), ("base-lettuce-v2", "LettuceDetect v2 mmBERT (off the shelf)"),
    ("eval-channel-a-noslot", "Channel A without the slot head"), ("eval-channel-a-noxbrl", "Channel A without XBRL data"),
    ("eval-channel-a", "Channel A (fine-tuned)"),
]
# The same 500 tune-track items (411 with a wrong original) for every row; stage A under the current gate (D-095)
REPAIRERS = [  # results file under runs/repair, label, has a gate
    ("rules/results.json", "Rule repairer v0 (no training; run on the laptop)", True),
    ("kaggle/eval-zero-shot-2b/results.json", "Qwen3.5-2B zero-shot (edit programs)", True),
    ("kaggle/eval-zero-shot-9b-free/results.json", "Qwen3.5-9B zero-shot (edit programs, free replies)", True),
    ("kaggle/eval-rewrite-sft/results.json", "Free rewriting, fine-tuned (baseline, no gate)", False),
    ("kaggle/eval-sft-current/results.json", "Stage A: fine-tuned edit programs", True),
    ("kaggle/eval-v1/results.json", "Repairer v1 candidate (stage A + arithmetic slips)", True),
]
PILOT = "runs/pilot/v1run-repair-v1/summary.json"  # natural answers, counts only (D-095 adapter, current code)


def _json(path: Path) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _text(path: Path) -> str | None:
    return path.read_text(encoding="utf-8") if path.exists() else None


KEYS = ("items", "needing_repair", "correction_rate", "abstained_when_needed", "new_error_rate", "damage_rate", "gate_pass_rate")


def results(root: Path) -> dict:
    det_rows = []
    for folder, label in DETECTORS:
        r = _json(root / "runs/detector/kaggle" / folder / "results.json")
        if r is None:
            continue
        a = r.get("channel_a", r)
        det_rows.append({"label": label, "auroc": a.get("auroc"), "false_alarm_clean": a.get("false_alarm_clean"),
                         "wrong_context_recall": a.get("wrong_context_recall"), "items": r.get("items"),
                         "ours": folder.startswith("eval-channel-a")})
        if folder == "eval-channel-a" and "channel_b" in r:
            b = r["channel_b"]
            det_rows.append({"label": "Channel B (rules)", "auroc": b.get("auroc"), "false_alarm_clean": b.get("false_alarm_clean"),
                             "wrong_context_recall": b.get("wrong_context_recall"), "items": r.get("items"), "ours": True})
    rep_rows = []
    for path, label, gated in REPAIRERS:
        r = _json(root / "runs/repair" / path)
        if r is not None:
            row = {"label": label, **{k: r["summary"].get(k) for k in KEYS}, "ours": "v1" in label or "Rule" in label}
            if not gated:
                row["gate_pass_rate"] = None
            rep_rows.append(row)
    pilot = _json(root / PILOT)
    pilot_rows = [{"label": name.replace("rule_spans", "rule checker's flags").replace("channel_a_spans", "Channel A's flags"),
                   **{k: s.get(k) for k in KEYS}} for name, s in sorted((pilot or {}).items())]
    reports = {
        "fusion": _text(root / "runs/detector/fusion/report.md"),
        "policy": _text(root / "runs/policy/controlled/report.md"),
    }
    return {"detectors": det_rows, "repairers": rep_rows, "pilot_repair": pilot_rows, "reports": reports,
            "repair_reports": {p.parent.name: _text(p) for p in sorted((root / "runs/repair/kaggle").glob("*/report.md"))}}
