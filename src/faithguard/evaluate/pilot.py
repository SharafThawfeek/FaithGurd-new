"""The pilot answers at a glance (phase 3): two automatic readings, then the labels once they exist.

Two automatic readings of every answer:

- the gold scorer (`score_text`): does every figure in the answer match a gold value?
  This is strict. A correct answer that adds a figure from outside the gold
  program (another year, another entity, a figure it worked out) counts as
  unsupported, so the automatic error rate is an upper bound;
- FaithGuard's rule checker (Channel B): which claims it flags, and why.

Their agreement is an early, rough signal for the detector; the labels decide.
Once answers are labelled, the summary adds the label counts (the pilot's error
rate) and how the checker and the scorer agree with the labels. It holds counts
only, never question or answer text, so it can go in the public repository. Show
it to a labeller only after labelling, so it cannot steer the labels.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from faithguard.detect.rules import detect
from faithguard.evaluate.score import score_text
from faithguard.gold import GoldLabel, GoldStore
from faithguard.records import Item

# (reading says wrong, label says incorrect) -> count name
_CHECKER = {(True, True): "checker_flagged_and_wrong", (True, False): "checker_flagged_but_right",
            (False, True): "checker_missed_wrong", (False, False): "checker_passed_and_right"}
_SCORER = {(True, True): "scorer_wrong_and_wrong", (True, False): "scorer_wrong_but_right",
           (False, True): "scorer_missed_wrong", (False, False): "scorer_right_and_right"}


def label_of(gold: GoldStore, item_id: str) -> GoldLabel | None:
    """The label that decides an original answer: the adjudicated one if there is one, else the first."""
    labels = [label for label in gold.labels.get(item_id, []) if label.target == "original"]
    return next((label for label in labels if label.adjudicated), labels[0] if labels else None)


def summarise(items: list[Item], gold: GoldStore) -> dict:
    groups: dict[str, Counter] = defaultdict(Counter)
    types: dict[str, Counter] = defaultdict(Counter)
    slots: Counter = Counter()
    labelled: dict[str, Counter] = defaultdict(Counter)
    labelled_types: dict[str, Counter] = defaultdict(Counter)
    labelled_slots: Counter = Counter()
    annotators: Counter = Counter()
    for item in items:
        key = f"{item.question.country} {item.answer.generator}"
        settings = item.answer.settings
        c = groups[key]
        c["answers"] += 1
        c["empty"] += not item.answer.text.strip()
        c["thinking_leaks"] += bool(settings.get("thinking_leak"))
        c["words"] += len(item.answer.text.split())
        label = label_of(gold, item.id)
        lc = labelled[key] if label else Counter()
        if label:
            annotators[label.annotator] += 1
            lc["labelled"] += 1
            lc[label.status] += 1
            lc["useful"] += bool(label.useful)
            labelled_types[item.question.question_type][label.status] += 1
            # unsupported_text, the one span label outside the numeric slots, is stored without a slot
            labelled_slots.update(span.slot or "unsupported_text" for span in label.spans)
        if item.question.question_type == "narrative":
            c["narrative"] += 1
            continue
        state = score_text(item.answer.text, gold.questions[item.question.id])
        flagged_checks = [ch for ch in detect(item).checks if ch.verdict != "supported"]
        flagged = bool(flagged_checks)
        c[state] += 1
        c["checker_flagged"] += flagged
        auto_wrong = state == "unsupported"
        c[{(True, True): "flagged_and_auto_wrong", (True, False): "flagged_but_auto_right",
           (False, True): "missed_auto_wrong", (False, False): "passed_and_auto_right"}[(flagged, auto_wrong)]] += 1
        types[item.question.question_type][state] += 1
        for ch in flagged_checks:
            slots.update(ch.slots or [ch.verdict])
        if label and label.status != "ambiguous":
            wrong = label.status == "incorrect"
            lc["numeric"] += 1
            lc["numeric_incorrect"] += wrong
            lc[_CHECKER[(flagged, wrong)]] += 1
            lc[_SCORER[(auto_wrong, wrong)]] += 1
    for c in groups.values():
        c["mean_words"] = round(c.pop("words") / c["answers"], 1)
    summary = {
        "by_country_and_generator": {k: dict(v) for k, v in sorted(groups.items())},
        "auto_score_by_question_type": {k: dict(v) for k, v in sorted(types.items())},
        "checker_flags_by_slot": dict(slots.most_common()),
    }
    if labelled:
        summary["labels"] = {
            "annotators": dict(annotators.most_common()),
            "by_country_and_generator": {k: dict(v) for k, v in sorted(labelled.items())},
            "by_question_type": {k: dict(v) for k, v in sorted(labelled_types.items())},
            "spans_by_slot": dict(labelled_slots.most_common()),
        }
    return summary


def report(summary: dict) -> str:
    lines = ["# Pilot answers", "",
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
    if "labels" in summary:
        lines += _label_report(summary["labels"])
    return "\n".join(lines) + "\n"


def _label_report(labels: dict) -> list[str]:
    groups = labels["by_country_and_generator"]
    total: Counter = Counter()
    for c in groups.values():
        total.update(c)
    who = ", ".join(f"{name} ({n})" for name, n in labels["annotators"].items())
    lines = ["", "## Labels", "",
             f"Labelled by: {who}. Numeric answers are the answers to every question type but narrative; "
             "ambiguous labels are left out of the agreement counts.", "",
             f"**Error rate:** {total['incorrect']} of {total['labelled']} answers labelled incorrect "
             f"({100 * total['incorrect'] / total['labelled']:.1f}%); {total['numeric_incorrect']} of {total['numeric']} "
             f"numeric answers ({100 * total['numeric_incorrect'] / max(total['numeric'], 1):.1f}%).", ""]
    cols = ["labelled", "correct", "incorrect", "ambiguous", "unhelpful", "useful", "numeric", "numeric_incorrect"]
    lines += ["| Country, generator | " + " | ".join(cols) + " |", "|" + " --- |" * (len(cols) + 1)]
    for key, c in [*groups.items(), ("all", total)]:
        lines.append(f"| {key} | " + " | ".join(str(c.get(col, 0)) for col in cols) + " |")
    lines += ["", "### Rule checker and gold scorer against the labels (numeric answers)", "",
              "| Country, generator | checker flagged, labelled incorrect | flagged, labelled right | missed, labelled incorrect "
              "| passed, labelled right | scorer wrong, labelled incorrect | scorer wrong, labelled right "
              "| scorer right, labelled incorrect |", "|" + " --- |" * 8]
    agreement = [*list(_CHECKER.values()), "scorer_wrong_and_wrong", "scorer_wrong_but_right", "scorer_missed_wrong"]
    for key, c in [*groups.items(), ("all", total)]:
        lines.append(f"| {key} | " + " | ".join(str(c.get(col, 0)) for col in agreement) + " |")
    lines += ["", "### Labels by question type", "", "| Type | correct | incorrect | ambiguous | unhelpful |",
              "| --- | --- | --- | --- | --- |"]
    for qtype, c in labels["by_question_type"].items():
        lines.append(f"| {qtype} | {c.get('correct', 0)} | {c.get('incorrect', 0)} | {c.get('ambiguous', 0)} | {c.get('unhelpful', 0)} |")
    lines += ["", "### Labelled spans by slot", "", "| Slot | Spans |", "| --- | --- |"]
    lines += [f"| {slot} | {n} |" for slot, n in labels["spans_by_slot"].items()]
    return lines
