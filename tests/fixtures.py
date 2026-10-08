"""Shared test items: a fictional Sri Lankan bank (the plan's worked example) and a US company.

All figures are made up. Group PAT growth FY2025 = 9.29%; Bank PAT growth = 7.00%.
"""

from faithguard.records import Answer, Evidence, Item, Passage, Question
from faithguard.tables import table_from_grid

BANK_GRID = [
    ["Income statement extract", "Group", "Group", "Bank", "Bank"],
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


def bank_item(answer: str, question: str = "What was the Group's profit after tax in FY2025?", drop=()) -> Item:
    evidence = Evidence(tables=[table_from_grid("t1", BANK_GRID, currency="LKR")])
    if drop:
        evidence = evidence.without(drop)
    return Item(
        id="demo-bank",
        question=Question(id="q-bank", issuer="demo-bank", country="LK", text=question, question_type="lookup"),
        evidence=evidence,
        answer=Answer(id="demo-bank", question_id="q-bank", generator="hand", text=answer),
    )


def us_item(answer: str, question: str = "What was Example Industries' revenue in FY2025?", passages=()) -> Item:
    evidence = Evidence(
        tables=[table_from_grid("t1", US_GRID, currency="USD")],
        passages=[Passage(id=f"p{i + 1}", text=t) for i, t in enumerate(passages)],
    )
    return Item(
        id="demo-us",
        question=Question(id="q-us", issuer="demo-us", country="US", text=question),
        evidence=evidence,
        answer=Answer(id="demo-us", question_id="q-us", generator="hand", text=answer),
    )


# Cell ids in BANK_GRID: rows 2-4 are NII, PAT, total assets; columns 1-4 are Group 2025, Group 2024, Bank 2025, Bank 2024.
GROUP_PAT_2025, GROUP_PAT_2024, BANK_PAT_2025 = "t1r3c1", "t1r3c2", "t1r3c3"
