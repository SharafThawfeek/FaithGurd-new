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


DECISION_TIME = ("detect", "policy", "repair", "executor.py", "claims.py", "pipeline.py", "calc", "tables.py", "records.py")


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
