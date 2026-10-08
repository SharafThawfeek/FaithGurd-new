"""Pre-action features for the decision policy.

Only what is known before any action is taken: the detector's output and the
evidence. Nothing from the gold store, and nothing from a repair attempt.
"""

from __future__ import annotations

from faithguard.records import SLOTS, DetectorOutput, Item

QUESTION_TYPES = ("lookup", "difference", "growth", "ratio", "share", "sum", "average", "comparison", "count", "narrative", "other")


def features(item: Item, det: DetectorOutput) -> dict[str, float]:
    checks = det.checks
    failing = [c for c in checks if c.verdict != "supported"]
    out: dict[str, float] = {
        "risk": det.risk,
        "n_claims": len(det.claims),
        "n_supported": sum(c.verdict == "supported" for c in checks),
        "n_unsupported": sum(c.verdict == "unsupported" for c in checks),
        "n_unverifiable": sum(c.verdict == "unverifiable" for c in checks),
        "n_links": sum(len(c.cells) for c in checks),
        "missing_operands": sum("missing_operand" in c.slots for c in checks),
        # every failing claim has a value the evidence supports for its intended context
        "evidence_sufficient": float(bool(failing) and all(c.expected is not None for c in failing)),
        "answers_question": float(bool(det.answers_question)),
        "n_cells": len(item.evidence.cells()),
        "n_passages": len(item.evidence.passages),
        "n_percent_claims": sum(c.kind == "percent" for c in det.claims),
        "n_directional_claims": sum(c.direction is not None for c in det.claims),
        "learned_span_max": max((s.score for s in det.spans), default=0.0),
    }
    for slot in SLOTS:
        out[f"slot_{slot}"] = sum(slot in c.slots for c in checks)
    for qt in QUESTION_TYPES:
        out[f"qtype_{qt}"] = float(item.question.question_type == qt)
    return out
