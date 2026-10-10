"""Score the stored outputs of the GPU systems (faithguard.train.systems) against the gold store (phase 6, step 2).

For every item and both span sources (the rule checker's flags, Channel A's), the trained repairer's
stored output is scored as the controlled-track repair evaluation scores it: wrong originals corrected,
new wrong numbers, correct originals damaged, repairs withheld. The rule-only repairer is replayed here
on the same flags, for comparison. An original answer's state comes from its label where one exists
(the labels decide) and from the strict gold scorer otherwise; a repair's state always comes from the
gold scorer, as the plan has code score every repair. Counts only, so the summary can be published.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Sequence

from faithguard.detect import detect
from faithguard.evaluate.repair import summarise
from faithguard.evaluate.score import score_text, wrong_numbers
from faithguard.gold import GoldStore
from faithguard.records import Item, RepairOutput

LABEL_STATE = {"correct": "supported_useful", "unhelpful": "supported_unhelpful", "incorrect": "unsupported"}


def _row(item: Item, gold: GoldStore, out: RepairOutput, before: str) -> dict:
    g = gold.questions[item.question.id]
    sent = out.text if out.status in ("repaired", "nothing_to_fix") else None
    before_wrong = set(wrong_numbers(item.answer.text, g))
    # an answer sent unchanged keeps its own state: the strict scorer must not overrule the label on the same text
    after = before if sent == item.answer.text else score_text(sent, g)
    return {
        "item_id": item.id, "error": None, "before": before, "after": after, "status": out.status,
        "attempts": out.attempts, "program": out.program is not None,
        "new_errors": [w for w in wrong_numbers(sent, g) if w not in before_wrong],
    }


def score(items: Sequence[Item], gold: GoldStore, detector_rows: dict[str, dict], repairs: dict[str, dict[str, dict]],
          label_state: dict[str, str] | None = None) -> dict:
    """repairs: {"rule_spans": {item_id: RepairOutput dict}, "channel_a_spans": {...}}; label_state: item id -> state."""
    from faithguard.detect.channel_a import flag_claims
    from faithguard.repair.rules import repair as rule_repair

    label_state = label_state or {}
    rows: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        if item.question.question_type == "narrative" or item.id not in detector_rows:
            continue
        g = gold.questions[item.question.id]
        before = label_state.get(item.id) or score_text(item.answer.text, g)
        det_b = detect(item)
        rec = detector_rows[item.id]
        a_max = {c["claim_id"]: c["a_max"] for c in rec["claims"]}  # Channel A's probability over each claim
        tokens = [(c.start, c.end, a_max.get(c.id, 0.0), 0) for c in det_b.claims]
        det_a = flag_claims(det_b, tokens, rec["threshold"])
        for source, det in (("rule_spans", det_b), ("channel_a_spans", det_a)):
            if item.id in repairs.get(source, {}):
                rows[f"trained repairer, {source}"].append(_row(item, gold, RepairOutput.model_validate(repairs[source][item.id]), before))
            rows[f"rule repairer, {source}"].append(_row(item, gold, rule_repair(item, det), before))
    return {name: summarise(rs) for name, rs in sorted(rows.items())}


def report(summary: dict, title: str = "Repair on natural answers") -> str:
    def pct(x) -> str:
        return "-" if x is None else f"{100 * x:.1f}%"

    lines = [f"# {title}", "",
             "Counts only. Original answers are judged by their labels where they exist, repairs by the gold scorer. "
             "Narrative questions are left out. See `faithguard.evaluate.systems`.", "",
             "| Repairer, spans | Items | Wrong originals | Corrected | Withheld when needed | New errors | Damage | Gate pass |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for name, s in summary.items():
        lines.append(f"| {name} | {s['items']} | {s['needing_repair']} | {pct(s['correction_rate'])} | {pct(s['abstained_when_needed'])} | "
                     f"{pct(s['new_error_rate'])} | {pct(s['damage_rate'])} | {pct(s['gate_pass_rate'])} |")
    return "\n".join(lines) + "\n"
