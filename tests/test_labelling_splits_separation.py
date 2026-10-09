import ast
import json
from pathlib import Path

import pytest

from faithguard import splits
from faithguard.labelling import build_tasks, labels_from_export
from fixtures import bank_item

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "faithguard"


def test_tasks_are_blinded_and_labels_come_back():
    items = [bank_item("Group profit after tax rose 7.0% to Rs. 12,450 million.")]
    tasks, mapping = build_tasks(items, salt="s")
    data = tasks[0]["data"]
    assert set(data) == {"task_key", "question", "evidence_html", "answer"}  # no generator, no item id
    assert "<table>" in data["evidence_html"] and "14,212,560" in data["evidence_html"]
    export = [{
        "data": data,
        "annotations": [{
            "completed_by": {"email": "a@x"},
            "result": [
                {"type": "labels", "from_name": "slot", "value": {"start": 38, "end": 56, "labels": ["entity_scope"]}},
                {"type": "choices", "from_name": "status", "value": {"choices": ["incorrect"]}},
                {"type": "choices", "from_name": "useful", "value": {"choices": ["not useful"]}},
            ],
        }],
    }]
    (label,) = labels_from_export(export, mapping)
    assert label.item_id == items[0].id and label.status == "incorrect" and label.useful is False
    assert label.spans[0].slot == "entity_scope" and label.annotator == "a@x"


def test_pilot_summary_counts_labels_against_the_checker_and_scorer(tmp_path):
    from decimal import Decimal

    from faithguard.evaluate import pilot
    from faithguard.gold import GoldLabel, GoldQuestion, GoldSpan, GoldStore, GoldValue

    right = bank_item("The Group's profit after tax was Rs. 14,212,560 thousand in FY2025.")
    wrong = bank_item("The Group's profit after tax was Rs. 12,450,330 thousand in FY2025.").model_copy(update={"id": "demo-bank-2"})
    gold = GoldStore(tmp_path)
    gold.add_question(GoldQuestion(question_id="q-bank", answer_text="Rs. 14,212,560 thousand", cells=["t1r3c1"],
                                   values=[GoldValue(value=Decimal("14212560000"), kind="amount")], source="test"))
    gold.add_label(GoldLabel(item_id=right.id, status="correct", useful=True, annotator="a"))
    gold.add_label(GoldLabel(item_id=wrong.id, status="incorrect", useful=True, annotator="a",
                             spans=[GoldSpan(start=37, end=55, slot="entity_scope")]))
    gold.add_label(GoldLabel(item_id=right.id, status="unhelpful", annotator="b"))  # not adjudicated: the first label decides
    gold.add_label(GoldLabel(item_id=wrong.id, status="correct", annotator="claude"))  # a person's label wins over an AI label
    summary = pilot.summarise([right, wrong], gold)
    counts = summary["labels"]["by_country_and_generator"]["LK hand"]
    assert counts["labelled"] == 2 and counts["incorrect"] == 1 and counts["numeric_incorrect"] == 1
    assert counts["checker_flagged_and_wrong"] == 1 and counts["checker_passed_and_right"] == 1
    assert counts["scorer_wrong_and_wrong"] == 1 and counts["scorer_right_and_right"] == 1
    assert summary["labels"]["spans_by_slot"] == {"entity_scope": 1}
    assert "1 of 2 answers labelled incorrect (50.0%)" in pilot.report(summary)
    review = GoldStore(tmp_path)
    review.add_label(GoldLabel(item_id=wrong.id, status="correct", annotator="claude"))
    review.add_label(GoldLabel(item_id=wrong.id, status="incorrect", annotator="person@x"))
    assert pilot.label_of(review, wrong.id).annotator == "person@x"


def test_label_config_is_valid_xml_and_names_every_slot():
    import xml.etree.ElementTree as ET

    root = ET.parse(ROOT / "labelling" / "label_config.xml").getroot()
    labels = {el.get("value") for el in root.iter("Label")}
    assert {"entity_scope", "metric", "period", "scale_currency", "sign", "basis", "missing_operand", "value"} <= labels


def test_split_manifest_is_frozen_and_disjoint():
    manifest = json.loads((ROOT / "manifests" / "splits.json").read_text(encoding="utf-8"))
    assert splits.verify(manifest)
    for country in ("US", "LK"):
        counts = {s: sum(1 for k, v in manifest["splits"].items() if k.startswith(country) and v == s) for s in ("test", "calibration", "dev")}
        assert counts == {"test": 12, "calibration": 12, "dev": 4}
    # rebuilding with the same seed gives the same assignment
    again = splits.assign(splits.read_issuers(ROOT / "manifests" / "issuers.csv"), manifest["seed"])
    assert again == manifest["splits"]


def test_finqa_companies_cannot_enter_test_or_calibration(tmp_path):
    csv = tmp_path / "issuers.csv"
    csv.write_text("country,issuer,name,sector,cik,status,notes\n" + "".join(f"US,T{i},n,s,,c,\n" for i in range(30)), encoding="utf-8")
    finqa = {f"T{i}" for i in range(30)}
    with pytest.raises(ValueError):
        splits.build(csv, finqa)


# Code that runs while answering a user. Offline training and certification code
# (policy/study.py, policy/certify.py, policy/outcome.py fitting) may read replay outcomes.
DECISION_TIME = (
    "detect", "repair", "executor.py", "claims.py", "pipeline.py", "calc", "tables.py", "records.py",
    "policy/features.py", "policy/threshold.py", "policy/deployed.py",
)


def test_decision_time_code_never_reads_gold():
    """Gold answers and labels must stay out of detection, policy and repair."""
    offenders = []
    for path in SRC.rglob("*.py"):
        rel = path.relative_to(SRC).as_posix()
        if not rel.startswith(DECISION_TIME):
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = []
            if isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            elif isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            for name in names:
                if name.startswith(("faithguard.gold", "faithguard.data", "faithguard.evaluate", "faithguard.inject", "faithguard.replay")):
                    offenders.append(f"{rel} imports {name}")
    assert offenders == []
