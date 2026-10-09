"""A first look at the pilot answers before anyone labels them (phase 3).

Two automatic readings of every answer:

- the gold scorer (`score_text`): does every figure in the answer match a gold value?
  This is strict. A correct answer that adds a figure from outside the gold
  program (another year, another entity, a figure it worked out) counts as
  unsupported, so the automatic error rate is an upper bound;
- FaithGuard's rule checker (Channel B): which claims it flags, and why.

Their agreement is an early, rough signal for the detector; the labels decide.
The summary holds counts only, never question or answer text, so it can go in
the public repository. Show it to the labeller only after labelling, so it cannot
steer the labels.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from faithguard.detect.rules import detect
from faithguard.evaluate.score import score_text
from faithguard.gold import GoldStore
from faithguard.records import Item


def summarise(items: list[Item], gold: GoldStore) -> dict:
    groups: dict[str, Counter] = defaultdict(Counter)
    types: dict[str, Counter] = defaultdict(Counter)
    slots: Counter = Counter()
    for item in items:
        key = f"{item.question.country} {item.answer.generator}"
        settings = item.answer.settings
        c = groups[key]
        c["answers"] += 1
        c["empty"] += not item.answer.text.strip()
        c["thinking_leaks"] += bool(settings.get("thinking_leak"))
        c["words"] += len(item.answer.text.split())
        if item.question.question_type == "narrative":
            c["narrative"] += 1
            continue
        state = score_text(item.answer.text, gold.questions[item.question.id])
        flagged_checks = [ch for ch in detect(item).checks if ch.verdict != "supported"]
        flagged = bool(flagged_checks)
        c[state] += 1
        c["checker_flagged"] += flagged
        wrong = state == "unsupported"
        c[{(True, True): "flagged_and_auto_wrong", (True, False): "flagged_but_auto_right",
           (False, True): "missed_auto_wrong", (False, False): "passed_and_auto_right"}[(flagged, wrong)]] += 1
        types[item.question.question_type][state] += 1
        for ch in flagged_checks:
            slots.update(ch.slots or [ch.verdict])
    for c in groups.values():
        c["mean_words"] = round(c.pop("words") / c["answers"], 1)
    return {
        "by_country_and_generator": {k: dict(v) for k, v in sorted(groups.items())},
        "auto_score_by_question_type": {k: dict(v) for k, v in sorted(types.items())},
        "checker_flags_by_slot": dict(slots.most_common()),
    }


def report(summary: dict) -> str:
    lines = ["# Pilot answers: automatic first look", "",
             "Counts only. The gold scorer is strict (any figure outside the gold program counts as unsupported), "
             "so its error rate is an upper bound; the labels decide. See `faithguard.evaluate.pilot`.", ""]
    cols = ["answers", "empty", "thinking_leaks", "mean_words", "narrative", "supported_useful", "supported_unhelpful",
            "unsupported", "checker_flagged", "flagged_and_auto_wrong", "flagged_but_auto_right", "missed_auto_wrong"]
    lines += ["| Country, generator | " + " | ".join(cols) + " |", "|" + " --- |" * (len(cols) + 1)]
    for key, c in summary["by_country_and_generator"].items():
        lines.append(f"| {key} | " + " | ".join(str(c.get(col, 0)) for col in cols) + " |")
    lines += ["", "## Automatic score by question type", "", "| Type | supported_useful | supported_unhelpful | unsupported |",
              "| --- | --- | --- | --- |"]
    for qtype, c in summary["auto_score_by_question_type"].items():
        lines.append(f"| {qtype} | {c.get('supported_useful', 0)} | {c.get('supported_unhelpful', 0)} | {c.get('unsupported', 0)} |")
    lines += ["", "## What the rule checker flagged", "", "| Slot or verdict | Claims |", "| --- | --- |"]
    lines += [f"| {slot} | {n} |" for slot, n in summary["checker_flags_by_slot"].items()]
    return "\n".join(lines) + "\n"
