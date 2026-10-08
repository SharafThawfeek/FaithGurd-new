"""The gold store: gold answers, human labels and injection records.

Kept apart from the item records on purpose. Only evaluation code (scoring,
replay, statistics) may import this module; detection, policy and repair never
do, and tests/test_separation.py enforces it.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Literal

from faithguard.records import Action, ClaimKind, Record, Slot, read_jsonl, write_jsonl


class GoldValue(Record):
    value: Decimal  # base units, or percentage points
    kind: ClaimKind
    role: Literal["answer", "operand", "intermediate"] = "answer"
    cell: str | None = None


class GoldQuestion(Record):
    question_id: str
    answer_text: str
    values: list[GoldValue]  # the first value with role "answer" is the primary answer
    cells: list[str] = []
    program: str | None = None  # in the cell expression language
    source: str

    @property
    def primary(self) -> GoldValue | None:
        return next((v for v in self.values if v.role == "answer"), None)


class GoldSpan(Record):
    start: int
    end: int
    slot: Slot | None = None


class GoldLabel(Record):
    """A human label for one answer (original or repaired)."""

    item_id: str
    target: Literal["original", "repair"] = "original"
    status: Literal["correct", "incorrect", "ambiguous", "unhelpful"]
    spans: list[GoldSpan] = []
    useful: bool | None = None
    annotator: str
    adjudicated: bool = False
    note: str = ""


class Injection(Record):
    """How an error was planted in a controlled-track item, and what should happen to it."""

    item_id: str
    error: str  # none, period, metric, entity, scale, sign, basis, missing_operand
    expected_action: Action
    changed_cells: list[str] = []
    removed_cells: list[str] = []


class GoldStore:
    """Gold records in their own folder: questions.jsonl, labels.jsonl, injections.jsonl."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.questions: dict[str, GoldQuestion] = {}
        self.labels: dict[str, list[GoldLabel]] = {}
        self.injections: dict[str, Injection] = {}

    @classmethod
    def load(cls, root: str | Path) -> "GoldStore":
        store = cls(root)
        if (store.root / "questions.jsonl").exists():
            store.questions = {g.question_id: g for g in read_jsonl(store.root / "questions.jsonl", GoldQuestion)}
        if (store.root / "labels.jsonl").exists():
            for label in read_jsonl(store.root / "labels.jsonl", GoldLabel):
                store.labels.setdefault(label.item_id, []).append(label)
        if (store.root / "injections.jsonl").exists():
            store.injections = {i.item_id: i for i in read_jsonl(store.root / "injections.jsonl", Injection)}
        return store

    def save(self) -> None:
        write_jsonl(self.root / "questions.jsonl", self.questions.values())
        write_jsonl(self.root / "labels.jsonl", [x for xs in self.labels.values() for x in xs])
        write_jsonl(self.root / "injections.jsonl", self.injections.values())

    def add_question(self, gold: GoldQuestion) -> None:
        self.questions[gold.question_id] = gold

    def add_label(self, label: GoldLabel) -> None:
        self.labels.setdefault(label.item_id, []).append(label)

    def add_injection(self, injection: Injection) -> None:
        self.injections[injection.item_id] = injection
