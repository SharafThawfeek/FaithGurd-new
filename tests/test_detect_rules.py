from decimal import Decimal

import pytest

from faithguard.claims import extract_claims
from faithguard.detect import detect
from fixtures import BANK_PAT_2025, GROUP_PAT_2025, bank_item, us_item


def checks(item):
    out = detect(item)
    return out, [(c.verdict, c.slots) for c in out.checks]


def test_worked_example_names_entity_errors():
    out, got = checks(bank_item("Group profit after tax rose 7.0% to Rs. 12,450 million."))
    assert got == [("unsupported", ["entity_scope"]), ("unsupported", ["entity_scope"])]
    amount = out.checks[1]
    assert amount.cells == [BANK_PAT_2025]
    assert amount.intended.entity == "group" and amount.intended.period == "2025"
    assert amount.expected == Decimal("14212560000")
    assert out.risk == 1.0


def test_correct_answer_is_supported():
    out, got = checks(bank_item("Group profit after tax rose 9.3% to Rs. 14,213 million in FY2025."))
    assert got == [("supported", []), ("supported", [])]
    assert out.risk == 0.0 and out.answers_question
    assert out.checks[1].cells == [GROUP_PAT_2025]


@pytest.mark.parametrize(
    "answer, slots",
    [
        ("Group profit after tax was Rs. 13,004 million in FY2025.", ["period"]),
        ("Group profit after tax was Rs. 14,212,560 million.", ["scale_currency"]),
        ("Group net interest income was Rs. 14,213 million.", ["metric"]),
        ("Group profit after tax fell 9.3% in FY2025.", ["sign"]),
        ("Group profit after tax was Rs. 15,000 million.", ["value"]),
    ],
)
def test_each_slot(answer, slots):
    _, got = checks(bank_item(answer))
    assert got == [("unsupported", slots)]


def test_wrong_base_growth_is_a_basis_error():
    # (14,212,560 - 13,004,180) / 14,212,560 = 8.5%
    _, got = checks(bank_item("Group profit after tax rose 8.5%."))
    assert got == [("unsupported", ["basis"])]


def test_missing_operand_is_unverifiable():
    out, got = checks(bank_item("Group profit after tax was Rs. 12,450 million.", drop=[GROUP_PAT_2025, "t1r3c2"]))
    assert got[0][0] in ("unverifiable", "unsupported")
    assert out.risk >= 0.5


def test_period_named_after_the_number():
    answer = "Group profit after tax was Rs. 13,004 million in FY2024 and Rs. 14,213 million in FY2025."
    _, got = checks(bank_item(answer))
    assert got == [("supported", []), ("supported", [])]


def test_us_answers_with_bare_and_scaled_numbers():
    _, got = checks(us_item("Revenue was $8.43 billion in fiscal 2025."))
    assert got == [("supported", [])]
    _, got = checks(us_item("Operating income was $1,104.7 million, while net income was $612.4 million."))
    assert got == [("supported", []), ("supported", [])]
    _, got = checks(
        us_item("Net income fell 6.5% to $612.4 million.", question="How did Example Industries' net income change in FY2025?")
    )
    assert got == [("supported", []), ("supported", [])]


def test_metric_not_in_evidence_is_unverifiable():
    _, got = checks(bank_item("The Group's return on equity was 15.2% in FY2025."))
    assert got == [("unverifiable", ["missing_operand"])]


def test_no_numbers_gives_middle_risk():
    out = detect(bank_item("The report does not say."))
    assert out.claims == [] and out.risk == 0.5 and not out.answers_question


def test_direction_words_are_attached():
    claims = extract_claims("Profit rose 7.0% to Rs. 12,450 million, while costs were 3% lower.")
    assert [(c.text, c.direction) for c in claims] == [("7.0%", "up"), ("Rs. 12,450 million", None), ("3%", "down")]
