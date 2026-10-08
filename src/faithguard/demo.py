"""Hand-written items on a fictional Sri Lankan bank and a fictional US company.

All figures are made up and clearly labelled as such. They exercise the error
types typical of Sri Lankan annual reports (Group vs Bank columns, Rs. '000
tables) until real reports are collected and corrected in phase 3.
"""

from __future__ import annotations

from decimal import Decimal

from faithguard.data.example import Example
from faithguard.gold import GoldQuestion, GoldValue, Injection
from faithguard.records import Answer, Evidence, Item, Question
from faithguard.tables import table_from_grid

BANK_GRID = [
    ["Income statement extract (fictional)", "Group", "Group", "Bank", "Bank"],
    ["Rs. '000", "2025", "2024", "2025", "2024"],
    ["Net interest income", "48,215,330", "44,102,870", "45,870,120", "42,015,440"],
    ["Profit after tax", "14,212,560", "13,004,180", "12,450,330", "11,635,900"],
    ["Total assets", "1,284,560,210", "1,190,330,450", "1,201,880,640", "1,112,450,300"],
]

US_GRID = [
    ["(in millions)", "FY2025", "FY2024"],
    ["Revenue", "$ 8,432.5", "$ 7,915.2"],
    ["Operating income", "1,104.7", "1,021.3"],
    ["Net income", "612.4", "655.1"],
]

# (question, answer, error, expected action, gold values as (value, kind, role))
_PAT = Decimal("14212560000")
_PAT_GROWTH = Decimal("9.292229")
BANK_CASES = [
    ("What was the Group's profit after tax in FY2025?", "Group profit after tax rose 9.3% to Rs. 14,213 million in FY2025.", "none", "send"),
    ("What was the Group's profit after tax in FY2025?", "Group profit after tax rose 7.0% to Rs. 12,450 million.", "entity", "repair"),
    ("What was the Group's profit after tax in FY2025?", "Group profit after tax was Rs. 14,212,560 million in FY2025.", "scale", "repair"),
    ("What was the Group's profit after tax in FY2025?", "Group profit after tax was Rs. 13,004 million in FY2025.", "period", "repair"),
    ("How did the Group's profit after tax change in FY2025?", "Group profit after tax fell 9.3% in FY2025.", "sign", "repair"),
    ("What was the Group's return on equity in FY2025?", "The Group's return on equity was 15.2% in FY2025.", "missing_operand", "abstain"),
]


def bank_items() -> list[tuple[Item, GoldQuestion, Injection]]:
    evidence = Evidence(tables=[table_from_grid("t1", BANK_GRID, currency="LKR")])
    out = []
    for i, (question, answer, error, action) in enumerate(BANK_CASES, start=1):
        qid = f"demo-lk-q{i}"
        if "return on equity" in question:
            values = []  # the evidence cannot answer this question
        elif "change" in question:
            values = [GoldValue(value=_PAT_GROWTH, kind="percent", role="answer")]
        else:
            values = [GoldValue(value=_PAT, kind="amount", role="answer"), GoldValue(value=_PAT_GROWTH, kind="percent", role="intermediate")]
        item = Item(
            id=f"demo-lk-{i}:{error}",
            question=Question(id=qid, issuer="demo:fictional-bank", country="LK", text=question, question_type="lookup", source="synthetic"),
            evidence=evidence,
            answer=Answer(id=f"demo-lk-{i}:{error}", question_id=qid, generator="hand" if error == "none" else f"hand:{error}", text=answer),
        )
        gold = GoldQuestion(question_id=qid, answer_text="see values", values=values or [GoldValue(value=Decimal(0), kind="percent", role="intermediate")], source="synthetic")
        out.append((item, gold, Injection(item_id=item.id, error=error, expected_action=action)))
    return out


def demo_examples() -> list[Example]:
    """Not used by the loaders; kept for symmetry with dataset Examples."""
    return []
