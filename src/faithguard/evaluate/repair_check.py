"""The repair check (pre-registration §6, D-100; Claude takes the people's part, D-103, D-106).

Code scores every repair. A blind labelling pass checks a random sample of the changed repairs on test
answers: 50 from each R-H1 arm (repairer v1's edit programs and the free-rewrite baseline, both on the
labelled spans) and 50 across the other trained-repairer variants. If code and the labels disagree on more
than 10% of a group's checked repairs, every changed repair of that group is labelled.

A repair is identified as "item id@system, span source" (e.g. "DIAL-2025-03:qwen@repair-v1, gold_spans");
its labels go to the gold store with target "repair" under that id.

The same sample also gets the information-preserved check (pre-registration §5, D-109): a separate blind
Claude pass sees the original answer beside the repaired one and says whether the repair kept every piece
of the original's information that the evidence supports.
"""

from __future__ import annotations

import random
from typing import Sequence

from faithguard.gold import GoldLabel, GoldStore
from faithguard.records import Item, RepairOutput

R_H1_ARMS = ("repair-v1, gold_spans", "rewrite-v1, gold_spans")
OTHERS = "other variants"
SAMPLE = 50
MAX_DISAGREE = 0.10
SEED = 2026
SOURCES = (("rule_spans", "repair_rule_spans"), ("channel_a_spans", "repair_channel_a_spans"), ("gold_spans", "repair_gold_spans"))


def changed(items: Sequence[Item], outputs: dict[str, dict[str, dict]]) -> dict[str, dict[str, str]]:
    """{"system, span source": {item id: repaired text}} for every numeric test answer a trained repairer sent changed."""
    out: dict[str, dict[str, str]] = {}
    for system, o in sorted(outputs.items()):
        for source, kind in SOURCES:
            for item in items:
                row = o.get(kind, {}).get(item.id)
                if row is None or item.question.split != "test" or item.question.question_type == "narrative":
                    continue
                rep = RepairOutput.model_validate(row)
                if rep.status in ("repaired", "nothing_to_fix") and rep.text and rep.text != item.answer.text:
                    out.setdefault(f"{system}, {source}", {})[item.id] = rep.text
    return out


def group_of(arm: str) -> str:
    return arm if arm in R_H1_ARMS else OTHERS


def draw(changes: dict[str, dict[str, str]], n: int = SAMPLE, seed: int = SEED) -> dict[str, list[str]]:
    """{group: [repair id]}: n changed repairs from each R-H1 arm and n pooled across the other arms."""
    rng = random.Random(seed)
    pools: dict[str, list[str]] = {}
    for arm in sorted(changes):
        pools.setdefault(group_of(arm), []).extend(f"{i}@{arm}" for i in sorted(changes[arm]))
    return {g: sorted(rng.sample(ids, min(n, len(ids)))) for g, ids in sorted(pools.items())}


def repair_items(items: Sequence[Item], changes: dict[str, dict[str, str]], repair_ids: Sequence[str]) -> list[Item]:
    """Each repair as an item of its own, for blinded tasks: the original's question and evidence, the repaired text."""
    by_id = {i.id: i for i in items}
    out = []
    for rid in repair_ids:
        item_id, arm = rid.split("@", 1)
        item = by_id[item_id]
        out.append(item.model_copy(update={"id": rid, "answer": item.answer.model_copy(update={"text": changes[arm][item_id]})}))
    return out


def info_tasks(items: Sequence[Item], changes: dict[str, dict[str, str]], repair_ids: Sequence[str], salt: str | None = None) -> tuple[list[dict], dict[str, str]]:
    """Blinded tasks for the information-preserved check (D-109): the question, the evidence, the original answer and the
    repaired one, for the repairs the check sampled; (tasks, key -> repair id)."""
    from faithguard import labelling

    by_id = {i.id: i for i in items}
    tasks, mapping = labelling.build_tasks(repair_items(items, changes, repair_ids), salt)
    for t in tasks:
        t["data"]["original"] = by_id[mapping[t["data"]["task_key"]].split("@", 1)[0]].answer.text
        t["data"]["repaired"] = t["data"].pop("answer")
    return tasks, mapping


def info_summary(items: Sequence[Item], results: Sequence[dict], mapping: dict[str, str], sample: dict[str, list[str]], seed: int = 0) -> dict:
    """Per group of the repair check: how many sampled repairs were judged, and the share that keep every piece of the
    original's information the evidence supports, with its issuer-clustered interval. results: [{task_key, preserved}]."""
    from faithguard.evaluate.analysis import paired

    by_id = {i.id: i for i in items}
    got = {mapping[r["task_key"]]: bool(r["preserved"]) for r in results if r["task_key"] in mapping}
    out = {}
    for group, ids in sorted(sample.items()):
        checked = [by_id[rid.split("@", 1)[0]].model_copy(update={"id": rid}) for rid in ids if rid in got]
        out[group] = {"planned": len(ids), "checked": len(checked),
                      "preserved": paired(checked, lambda s: sum(got[i.id] for i in s) / len(s) if s else None, seed)}
    return out


def repair_label(gold: GoldStore, repair_id: str) -> GoldLabel | None:
    """The deciding label of a checked repair: the adjudicated one, else the first."""
    from faithguard.evaluate.pilot import AI_ANNOTATORS

    labels = [x for x in gold.labels.get(repair_id, []) if x.target == "repair" and x.annotator not in AI_ANNOTATORS]
    return next((x for x in labels if x.adjudicated), (labels or [None])[0])


def compare(items: Sequence[Item], gold: GoldStore, changes: dict[str, dict[str, str]], sample: dict[str, list[str]]) -> dict:
    """Per group: checked repairs, how many code and the labels disagree on, and whether the whole group must be labelled."""
    from faithguard.evaluate.score import score_text
    from faithguard.evaluate.systems import LABEL_STATE

    by_id = {i.id: i for i in items}
    out = {}
    for group, ids in sorted(sample.items()):
        disagree, labelled = [], 0
        for rid in ids:
            label = repair_label(gold, rid)
            if label is None:
                continue
            labelled += 1
            item_id, arm = rid.split("@", 1)
            item = by_id[item_id]
            code = score_text(changes[arm][item_id], gold.questions[item.question.id], item.evidence)
            if code != LABEL_STATE[label.status]:
                disagree.append({"repair": rid, "code": code, "label": LABEL_STATE[label.status]})
        rate = len(disagree) / labelled if labelled else None
        out[group] = {"planned": len(ids), "labelled": labelled, "disagree": len(disagree), "rate": rate,
                      "label_every_changed_repair": rate is not None and labelled == len(ids) and rate > MAX_DISAGREE,
                      "disagreements": disagree}
    return out
