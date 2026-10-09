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


# Phrasings from the first natural (generated) pilot answers, which the checker used to flag although they were right.
LK_GRID = [
    ["Statement extract", "Group", "Group", "Bank", "Bank"],
    ["Rs. '000", "2025", "2024", "2025", "2024"],
    ["Total operating expenses", "50,402,848", "42,802,391", "46,768,432", "39,332,563"],
    ["Loans & advances", "1,195,918,062", "901,950,481", "1,127,776,792", "860,151,610"],
    ["Financial assets at amortised cost- Net investment in leases and hire purchase", "83,377,069", "56,556,667", "80,000,000", "50,000,000"],
    ["Total assets", "2,064,207,240", "1,836,995,366", "1,978,252,563", "1,777,941,123"],
]


def lk_item(answer: str, question: str = "What were the Group's total operating expenses in 2025?"):
    from faithguard.records import Answer, Evidence, Item, Question
    from faithguard.tables import table_from_grid

    return Item(
        id="lk", evidence=Evidence(tables=[table_from_grid("t1", LK_GRID, currency="LKR")]),
        question=Question(id="q-lk", issuer="lk", country="LK", text=question, question_type="lookup", period="2025"),
        answer=Answer(id="lk", question_id="q-lk", generator="hand", text=answer),
    )


@pytest.mark.parametrize(
    "answer",
    [
        # a difference between two entities in one year, with the subject before or after the figure
        "In 2025, the Group's total operating expenses were Rs. 50,402,848 thousand, while the Bank's were "
        "Rs. 46,768,432 thousand. This makes the Group's expenses Rs. 3,634,416 thousand higher than the Bank's.",
        "The Group's total operating expenses in 2025 were Rs. 50,402,848 thousand, which were Rs. 3,634,416 thousand "
        "higher than the Bank's total operating expenses of Rs. 46,768,432 thousand.",
        # "&" and "and" name the same line; a long row is named by its distinctive ending
        "The Group's loans and advances were Rs. 1,195,918,062 thousand in 2025.",
        "The Group's net investment in leases and hire purchase was Rs. 83,377,069 thousand in 2025. "
        "This represents approximately 4.0% of the Group's total assets.",
        # the period after an aside, "reported in", "in the previous year"
        "The Group's total operating expenses grew by 17.8% to Rs. 50,402,848 thousand (Rs 50,402.8 million) in 2025 "
        "from Rs. 42,802,391 thousand (Rs 42,802.4 million) in 2024.",
        "The Group's total operating expenses were Rs. 50,402,848 thousand. This represents an increase of "
        "Rs. 7,600,457 thousand compared to the Rs. 42,802,391 thousand reported in 2024.",
        "The Group's total operating expenses were Rs. 50,402,848 thousand, up from Rs. 42,802,391 thousand in the previous year.",
    ],
)
def test_natural_phrasings_of_correct_answers_are_supported(answer):
    _, got = checks(lk_item(answer))
    assert all(v == "supported" for v, _ in got), got


def test_holders_of_the_bank_do_not_make_a_claim_about_the_bank():
    _, got = checks(bank_item("Group profit after tax attributable to equity holders of the Bank was Rs. 14,213 million in FY2025."))
    assert got == [("supported", [])]


@pytest.mark.parametrize(
    "answer",
    [
        "The Group's loans and advances were 4.0% of the Group's total assets in 2025.",  # 4.0% is the leases share
        "Goodwill was 4.0% of the Group's total assets in 2025.",  # the share's numerator is never named
    ],
)
def test_a_share_with_the_wrong_numerator_is_still_flagged(answer):
    _, got = checks(lk_item(answer))
    assert got[-1][0] != "supported"
