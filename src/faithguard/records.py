"""Record format v1: the one shape every FaithGuard component reads and writes.

An Item is one answer to check: the question, the frozen evidence and the answer.
Detector output, policy decisions, repair programs and final outputs all refer
back to an item by its id. Gold answers and labels are *not* here; they live in
faithguard.gold, which no component reads at decision time.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any, Iterable, Iterator, Literal, TypeVar, Union

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1.0"
CELL_ID = r"^[A-Za-z][A-Za-z0-9_]*$"  # usable as a name in the cell expression language

Country = Literal["US", "LK"]
Split = Literal["train", "dev", "calibration", "test", "future"]
QuestionType = Literal[
    "lookup", "difference", "growth", "ratio", "share", "sum", "average", "comparison", "count", "narrative", "other"
]
CellKind = Literal["amount", "percent", "ratio", "number", "text"]
ClaimKind = Literal["amount", "percent", "ratio", "number"]
Slot = Literal[
    "entity_scope", "metric", "period", "unit", "scale_currency", "sign", "basis", "missing_operand", "value"
]
SLOTS: tuple[str, ...] = Slot.__args__  # type: ignore[attr-defined]
Action = Literal["send", "repair", "abstain"]
Verdict = Literal["supported", "unsupported", "unverifiable"]
ReasonCode = Literal["missing_operand", "ambiguous_evidence", "non_numeric", "conflicting_evidence", "gate_failed"]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------


class Cell(Record):
    id: str = Field(pattern=CELL_ID)
    table_id: str
    row: int
    col: int
    row_label: str = ""
    column_label: str = ""
    text: str
    raw: Decimal | None = None  # the number as printed, sign applied; None for text cells
    kind: CellKind = "amount"
    scale: int = 0  # power of ten the printed number is in, e.g. 3 for Rs. '000
    currency: str | None = None
    metric: str | None = None  # normalised row label, e.g. "profit after tax"
    entity: str | None = None  # e.g. "group", "bank", "company"
    period: str | None = None  # fiscal year as "2025"

    @property
    def value(self) -> Decimal | None:
        """Base units for amounts and numbers; percentage points for percentages."""
        if self.raw is None:
            return None
        return self.raw.scaleb(self.scale) if self.kind in ("amount", "number") else self.raw


class Passage(Record):
    id: str
    text: str
    page: int | None = None


class Table(Record):
    id: str
    title: str = ""
    page: int | None = None
    source: str | None = None
    scale: int = 0
    currency: str | None = None
    cells: list[Cell]


class Evidence(Record):
    tables: list[Table] = []
    passages: list[Passage] = []

    def cells(self) -> list[Cell]:
        return [c for t in self.tables for c in t.cells]

    def cell(self, cell_id: str) -> Cell:
        for c in self.cells():
            if c.id == cell_id:
                return c
        raise KeyError(cell_id)

    def without(self, cell_ids: Iterable[str]) -> "Evidence":
        """A copy with some cells removed (used to build missing-operand items)."""
        drop = set(cell_ids)
        tables = [t.model_copy(update={"cells": [c for c in t.cells if c.id not in drop]}) for t in self.tables]
        return self.model_copy(update={"tables": tables})

    def digest(self) -> str:
        """A stable hash, so frozen evidence can be checked later."""
        canonical = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Questions, answers, items
# ---------------------------------------------------------------------------


class Question(Record):
    id: str
    issuer: str
    country: Country | None = None
    split: Split | None = None
    text: str
    question_type: QuestionType = "other"
    period: str | None = None
    source: str = "team"  # team, finqa, tatqa, ragtruth, synthetic


class Answer(Record):
    id: str
    question_id: str
    generator: str  # model id, "template", or "injected:<error>"
    text: str
    settings: dict[str, Any] = {}


class Item(Record):
    schema_version: str = SCHEMA_VERSION
    id: str
    question: Question
    evidence: Evidence
    answer: Answer


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


class Context(Record):
    metric: str | None = None
    entity: str | None = None
    period: str | None = None
    base_period: str | None = None  # for a change, the period it is measured from ("from 2017 to 2019")


class Claim(Record):
    id: str
    start: int
    end: int
    text: str
    kind: ClaimKind
    value: Decimal  # base units, or percentage points; sign included
    decimals: int
    scale: int = 0
    currency: str | None = None
    direction: Literal["up", "down"] | None = None
    direction_span: tuple[int, int] | None = None


class ClaimCheck(Record):
    claim_id: str
    verdict: Verdict
    slots: list[Slot] = []
    cells: list[str] = []  # cells the claim was traced to
    intended: Context = Context()
    relation: Literal["cell", "growth", "diff", "share", "ratio"] | None = None
    expected: Decimal | None = None  # what the evidence supports for the intended context
    fix: str | None = None  # cell expression giving `expected`, e.g. "t1r3c1" or "growth(t1r3c1, t1r3c2)"
    note: str = ""


class Span(Record):
    """A span flagged by a learned detector (Channel A)."""

    start: int
    end: int
    score: float
    slot: Slot | None = None


class DetectorOutput(Record):
    item_id: str
    detector: str
    claims: list[Claim] = []
    checks: list[ClaimCheck] = []
    spans: list[Span] = []
    risk: float
    answers_question: bool | None = None

    def check(self, claim_id: str) -> ClaimCheck:
        return next(c for c in self.checks if c.claim_id == claim_id)

    def claim(self, claim_id: str) -> Claim:
        return next(c for c in self.claims if c.id == claim_id)


# ---------------------------------------------------------------------------
# Decisions and repair
# ---------------------------------------------------------------------------


class Decision(Record):
    item_id: str
    policy: str
    action: Action
    reason: str
    scores: dict[str, float] = {}


class Keep(Record):
    op: Literal["KEEP"] = "KEEP"
    claim: str


class Copy(Record):
    op: Literal["COPY"] = "COPY"
    claim: str
    cell: str


class Calculate(Record):
    op: Literal["CALCULATE"] = "CALCULATE"
    claim: str
    expr: str  # cell expression language, e.g. "growth(t1r3c1, t1r3c2)"


class CannotFix(Record):
    op: Literal["CANNOT_FIX"] = "CANNOT_FIX"
    reason: ReasonCode
    claim: str | None = None
    note: str = ""


Edit = Annotated[Union[Keep, Copy, Calculate, CannotFix], Field(discriminator="op")]


class EditProgram(Record):
    edits: list[Edit]


class GateResult(Record):
    passed: bool
    failures: list[str] = []


class RepairOutput(Record):
    item_id: str
    repairer: str
    status: Literal["repaired", "cannot_fix", "gate_failed", "nothing_to_fix"]
    program: EditProgram | None = None
    text: str | None = None
    gate: GateResult | None = None
    attempts: int = 0
    reason: str = ""


class FinalOutput(Record):
    item_id: str
    action: Action
    text: str | None  # what the user sees; None when abstaining
    reason: str
    evidence_cells: list[str] = []  # shown with an abstention, or traced for a fixed answer
    detector: DetectorOutput
    decision: Decision
    repair: RepairOutput | None = None


# ---------------------------------------------------------------------------
# JSON Lines
# ---------------------------------------------------------------------------

M = TypeVar("M", bound=BaseModel)


def write_jsonl(path: str | Path, records: Iterable[BaseModel]) -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for r in records:
            f.write(r.model_dump_json() + "\n")
            n += 1
    return n


def read_jsonl(path: str | Path, model: type[M]) -> Iterator[M]:
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield model.model_validate_json(line)
