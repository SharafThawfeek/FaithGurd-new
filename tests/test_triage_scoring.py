"""Natural-answer scoring and the labelling triage (D-100): code labels clear answers, a person the rest."""

import json
from decimal import Decimal

import pytest

from faithguard.evaluate.pilot import AI_ANNOTATORS, label_of
from faithguard.evaluate.score import score_text, wrong_numbers
from faithguard.evaluate.systems import LABEL_STATE
from faithguard.evaluate.triage import AUDIT_MAX_WRONG, AUTO_ANNOTATOR, audit, code_label, draw_audit, reasons, triage
from faithguard.gold import GoldLabel, GoldQuestion, GoldSpan, GoldStore, GoldValue
from faithguard.labelling import build_tasks
from faithguard.records import Answer, Evidence, Item, Question, write_jsonl
from faithguard.tables import table_from_grid
from fixtures import BANK_PAT_2025, GROUP_PAT_2025, bank_item, us_item

LOSS_GRID = [
    ["(in thousands)", "FY2025", "FY2024"],
    ["Operating loss", "(70,541)", "(165,490)"],
    ["Net loss", "(64,907)", "(12,000)"],
    ["Diluted loss per share", "(1.98)", "(0.40)"],
]


def gold(answer, kind="amount", operands=(), program=None, qid="q-us") -> GoldQuestion:
    values = [GoldValue(value=Decimal(answer), kind=kind, role="answer")]
    values += [GoldValue(value=Decimal(v), kind="amount", role="operand", cell=c) for c, v in operands]
    return GoldQuestion(question_id=qid, answer_text="", values=values, cells=[c for c, _ in operands], program=program, source="team")


def loss_item(answer: str, grid=LOSS_GRID, question="What was the net loss in FY2025?", qtype="lookup", currency="USD") -> Item:
    evidence = Evidence(tables=[table_from_grid("t1", grid, currency=currency)])
    return Item(id="i", question=Question(id="q-us", issuer="x", country="US", text=question, question_type=qtype),
                evidence=evidence, answer=Answer(id="i", question_id="q-us", generator="hand", text=answer))


def state(item: Item, g: GoldQuestion) -> str:
    return score_text(item.answer.text, g, item.evidence)


# Net income fell from 655.1 to 612.4 million; the gold answer is the size of the fall.
FALL = gold("42700000", operands=[("t1r3c2", "655100000"), ("t1r3c1", "612400000")], program="t1r3c2 - t1r3c1")
NET_LOSS = gold("-64907000", operands=[("t1r2c1", "-64907000")], program="t1r2c1")
NARROWED = gold("94949000", operands=[("t1r1c1", "-70541000"), ("t1r1c2", "-165490000")], program="t1r1c1 - t1r1c2")
REVENUE = gold("8432500000", operands=[("t1r1c1", "8432500000")], program="t1r1c1")
GROWTH = gold("6.535780574", kind="percent", operands=[("t1r1c1", "8432500000"), ("t1r1c2", "7915200000")],
              program="growth(t1r1c1, t1r1c2)")


def test_a_fall_is_read_by_its_size_and_direction_word():
    right = us_item("Net income fell by $42.7 million in FY2025.")
    assert score_text(right.answer.text, FALL) == "unsupported"  # template reading, unchanged
    assert state(right, FALL) == "supported_useful"
    assert state(us_item("Net income rose by $42.7 million in FY2025."), FALL) == "unsupported"


def test_a_loss_written_as_a_positive_figure_right_after_loss():
    assert state(loss_item("The company reported a net loss of $64,907 thousand."), NET_LOSS) == "supported_useful"
    assert score_text("The company reported a net loss of $64,907 thousand.", NET_LOSS) == "unsupported"
    eps = gold("-1.98", operands=[("t1r3c1", "-1.98")], program="t1r3c1")
    assert state(loss_item("Diluted loss per share was $(1.98)."), eps) == "supported_useful"
    lk = loss_item("The Group reported a net loss of Rs. 64,907 thousand.", currency="LKR")
    assert state(lk, NET_LOSS) == "supported_useful"  # "Rs." does not end the clause


@pytest.mark.parametrize("text", [
    "The company reported net income of $64,907 thousand.",
    "The company turned last year's loss into a profit of $64,907 thousand.",
    "The company recovered from last year's loss with net income of $64,907 thousand.",
    "The company avoided a loss and reported net income of $64,907 thousand.",
    "The company swung from a loss to a net profit of $64,907 thousand in FY2025.",
    "The profit & loss statement shows a net profit of $64,907 thousand.",
    "No longer loss-making, the company earned $64,907 thousand.",
])
def test_a_profit_stated_for_a_loss_is_still_a_sign_error(text):
    assert state(loss_item(text), NET_LOSS) == "unsupported"


def test_loss_before_a_positive_gold_figure_needs_a_loss_line():
    profit_grid = [["(in thousands)", "FY2025", "FY2024"], ["Net income", "64,907", "12,000"]]
    loss_line_grid = [["(in thousands)", "FY2025", "FY2024"], ["Net loss", "64,907", "12,000"]]
    g = gold("64907000", operands=[("t1r1c1", "64907000")], program="t1r1c1")
    text = "The company reported a net loss of $64,907 thousand."
    assert state(loss_item(text, grid=profit_grid), g) == "unsupported"
    assert state(loss_item(text, grid=loss_line_grid), g) == "supported_useful"
    assert state(loss_item("Net income was $(64,907) thousand.", grid=profit_grid), g) == "unsupported"  # brackets read negative


def test_profit_or_loss_names_a_statement_not_a_loss():
    item = us_item("The statement of profit or loss shows revenue of $8,432.5 million in FY2025.")
    assert state(item, REVENUE) == "supported_useful"


def test_a_change_between_losses_moves_by_size_and_judging_words_are_not_read():
    question = "Did the operating loss narrow or widen in FY2025, and by how much?"
    for text, expected in [
        ("The operating loss narrowed, a decrease of $94,949 thousand.", "supported_useful"),
        ("The operating loss widened, an increase of $94,949 thousand.", "unsupported"),
        ("The operating loss improved by $94,949 thousand in FY2025.", "unsupported"),
        ("The operating loss deteriorated by $94,949 thousand in FY2025.", "unsupported"),
        ("The operating loss decreased from $165,490 thousand to $70,541 thousand.", "supported_unhelpful"),
    ]:
        assert state(loss_item(text, question=question, qtype="difference"), NARROWED) == expected, text


def test_a_bare_number_change_is_read_in_the_tables_unit():
    assert state(us_item("Net income fell by 42.7 in FY2025."), FALL) == "supported_useful"


def test_ratio_as_percentage_only_for_a_level_and_calculation_constants():
    ratio = gold("2.084105649", kind="ratio")
    assert state(us_item("Liabilities were about 2.08:1 of equity (208%)."), ratio) == "supported_useful"
    assert state(us_item("Liabilities rose 208% against equity."), ratio) == "unsupported"
    item = us_item("Revenue grew 6.5% in FY2025 (the change over FY2024 × 100).")
    assert [w.strip() for w in wrong_numbers(item.answer.text, GROWTH)] == ["100"]
    assert state(item, GROWTH) == "supported_useful"


def test_triage_routes_only_clear_answers_to_code():
    assert reasons(us_item("Example Industries' revenue was $8,432.5 million in FY2025."), REVENUE) == []
    assert reasons(us_item("Revenue grew 6.5% in FY2025, from $7,915.2 million in FY2024 to $8,432.5 million."), GROWTH) == []
    routed = {
        "Revenue is not available separately, but total revenue was $8,432.5 million.": "a negation, hedge or guess",
        "Revenue was $8,432.5 million; the extract lacks a segment breakdown.": "a negation, hedge or guess",
        "Revenue was Rs. 8,432.5 million in FY2025.": "a currency the report does not use",
        "Revenue was $8,000 million.": "a number the gold values do not cover",
        "Revenue rose to $8,432.5 million in FY2025.": "a direction word the scorer cannot check",
        "Revenue was $8,432.5 million in FY2024.": "a year that is not its figure's",
        "Revenue was $8,432.5 million in FY2025, up about seven percent.": "a figure in words or a fraction",
    }
    for text, reason in routed.items():
        assert reason in reasons(us_item(text), REVENUE), text
    comparison = us_item("Revenue was larger in FY2025, by $517.3 million.")
    comparison.question.question_type = "comparison"
    assert reasons(comparison, REVENUE) == ["comparison question"]


def test_triage_checks_years_and_entities_against_the_cells_figures_matched():
    swapped = us_item("Revenue was $7,915.2 million in FY2025, up 6.5% from FY2024.")
    assert "a year that is not its figure's" in reasons(swapped, GROWTH)
    group = gold("14212560000", operands=[(GROUP_PAT_2025, "14212560000")], program=GROUP_PAT_2025, qid="q-bank")
    assert reasons(bank_item("The Group's profit after tax was Rs. 14,212,560 thousand in FY2025."), group) == []
    assert "an entity that is not its figure's" in reasons(
        bank_item("The Bank's profit after tax was Rs. 14,212,560 thousand in FY2025."), group)
    named = bank_item("Example Bank Group's profit after tax was Rs. 14,212,560 thousand in FY2025.",
                      question="What was Example Bank Group's profit after tax in FY2025?")
    assert reasons(named, group) == []
    assert "an entity that is not its figure's" in reasons(
        bank_item("For FY2025, Example's Bank profit after tax was Rs. 14,212,560 thousand."), group)
    between = gold("1762230000", operands=[(GROUP_PAT_2025, "14212560000"), (BANK_PAT_2025, "12450330000")],
                   program=f"{GROUP_PAT_2025} - {BANK_PAT_2025}", qid="q-bank")
    assert "a difference between two entities" in reasons(
        bank_item("The Group earned Rs. 1,762,230 thousand more than the Bank in FY2025."), between)


def test_audit_sample_is_stratified_drawn_from_code_labels_and_decides(tmp_path):
    items = []
    for n in range(8):
        text = "Revenue was $8,432.5 million in FY2025." if n % 2 else "Revenue was $8,000 million."
        item = us_item(text).model_copy(update={"id": f"i{n}"}, deep=True)
        item.answer.generator = "qwen" if n < 4 else "gemma"
        items.append(item)
    store = GoldStore(tmp_path)
    store.add_question(REVENUE)
    result = triage(items, store, audit_size=2, seed=1)
    assert result["code"] == ["i1", "i3", "i5", "i7"] and result["person"] == ["i0", "i2", "i4", "i6"]
    assert set(result["audit"]) <= set(result["code"]) and len(result["audit"]) == 2
    assert sorted(result["strata"]) == ["US gemma one figure", "US qwen one figure"]  # one from each generator
    assert result == triage(items, store, audit_size=2, seed=1)
    assert draw_audit(items, 0) == []

    def person(i, status="correct", spans=()):
        return GoldLabel(item_id=i, status=status, useful=True, annotator="a@x", spans=list(spans))

    for i in result["audit"]:
        store.add_label(person(i))
    verdict = audit(result, store, items)
    assert verdict["code_labels_stand"] and verdict["to_person"] == [] and len(verdict["code_labels_kept"]) == 2
    first, second = result["audit"]
    store.labels[first] = [person(first, spans=[GoldSpan(start=0, end=3, slot="value")])]
    store.labels[second] = [person(second, status="incorrect")]
    assert AUDIT_MAX_WRONG == 1
    fallen = audit(result, store, items)
    assert not fallen["code_labels_stand"] and fallen["code_labels_kept"] == []
    assert set(fallen["to_person"]) == set(result["code"]) - set(result["audit"])
    store.labels[second] = [code_label(items[int(second[1:])])]  # a code or Claude label never counts as the person's
    assert not audit(result, store, items)["code_labels_stand"]


def test_an_overruled_question_sends_its_other_code_labels_to_a_person(tmp_path):
    items = [us_item("Revenue was $8,432.5 million in FY2025.").model_copy(update={"id": f"i{n}"}) for n in range(3)]
    store = GoldStore(tmp_path)
    store.add_question(REVENUE)
    result = {"code": ["i0", "i1", "i2"], "person": [], "audit": ["i0"], "audit_size": 1}
    store.add_label(GoldLabel(item_id="i0", status="incorrect", useful=False, annotator="a@x"))
    verdict = audit(result, store, items)
    assert verdict["code_labels_stand"] and verdict["to_person"] == ["i1", "i2"]  # the gold may be wrong


def test_a_persons_label_wins_over_a_code_label(tmp_path):
    assert AUTO_ANNOTATOR in AI_ANNOTATORS
    item = us_item("Revenue was $8,432.5 million in FY2025.")
    store = GoldStore(tmp_path)
    store.add_label(code_label(item))
    person = GoldLabel(item_id=item.id, status="incorrect", useful=False, annotator="a@x")
    store.add_label(person)
    assert label_of(store, item.id) == person


def test_tasks_get_a_random_salt_unless_one_is_given():
    items = [us_item("Revenue was $8,432.5 million in FY2025.")]
    (_, a), (_, b) = build_tasks(items), build_tasks(items)
    assert set(a) != set(b)
    assert build_tasks(items, salt="s", seed=7)[1] == build_tasks(items, salt="s", seed=7)[1]


def test_ambiguous_labels_count_as_unsafe():
    assert LABEL_STATE["ambiguous"] == "unsupported"


def test_cli_guards_on_labelling(tmp_path):
    from faithguard import cli

    with pytest.raises(SystemExit):  # import needs an explicit gold store
        cli.main(["labelling", "import", "--export", "x.json", "--mapping", "m.json"])
    item = us_item("Revenue was $8,432.5 million in FY2025.")
    item.question.split = "test"
    items = tmp_path / "items.jsonl"
    write_jsonl(items, [item])
    store = GoldStore(tmp_path / "gold")
    store.add_question(REVENUE)
    store.save()
    args = ["labelling", "triage", "--items", str(items), "--gold", str(store.root), "--out", str(tmp_path / "t.json")]
    with pytest.raises(SystemExit, match="filed"):  # never before the pre-registration
        cli.main(args)
    with pytest.raises(SystemExit, match="second reader"):  # never on gold nobody has cross-checked
        cli.main(args + ["--filed", "osf.io/x", "--benchmark", str(tmp_path / "reports")])
    taken = tmp_path / "tasks.json"
    taken.write_text(json.dumps([]), encoding="utf-8")
    with pytest.raises(SystemExit, match="already exist"):  # random keys: never overwrite tasks or a mapping
        cli.main(["labelling", "tasks", "--items", str(items), "--out", str(taken), "--mapping", str(tmp_path / "m.json")])


def test_from_to_phrasing_line_items_and_counts_are_not_routed_but_swaps_are():
    item = lambda text: us_item(text)
    clear = "Revenue increased from $7,915.2 million in FY2024 to $8,432.5 million in FY2025, a growth of 6.5%."
    assert reasons(item(clear), GROWTH) == []
    swapped = "Revenue rose from $8,432.5 million to $7,915.2 million, a growth of 6.5%."
    assert "a 'from' or 'to' figure from the wrong year" in reasons(item(swapped), GROWTH)
    assert reasons(item("Revenue fell by 6.5% in FY2025."), GROWTH) == ["a number the gold values do not cover"]
    assert "a direction word the scorer cannot check" in reasons(item("Revenue grew 6.5% in FY2025 as costs fell."), GROWTH)
    assert reasons(item("Revenue was $8,432.5 million in FY2025, comparing the two periods."), REVENUE) == []
    group = gold("14212560000", operands=[(GROUP_PAT_2025, "14212560000")], program=GROUP_PAT_2025, qid="q-bank")
    owners = "The Group's profit after tax attributable to owners of the company was Rs. 14,212,560 thousand in FY2025."
    assert reasons(bank_item(owners), group) == []


GROWTH_ITEM = "Revenue grew 6.5% in FY2025."


@pytest.mark.parametrize("text,reason", [
    ("Revenue grew 6.5% in FY2024.", "a year that is not its figure's"),
    ("Revenue grew 6.5% compared with FY2025.", "a year that is not its figure's"),
    ("Revenue was $7,915.2 million this year, a growth of 6.5%.", "a year that is not its figure's"),
    ("Revenue grew 6.5% to $7,915.2 million.", "a 'from' or 'to' figure from the wrong year"),
    ("Revenue grew 6.5%, from a total of $8,432.5 million.", "a 'from' or 'to' figure from the wrong year"),
    ("Revenue grew by 6.5% in FY2025; only the consolidated figure is shown.", "a negation, hedge or guess"),
    ("Revenue grew 6.5% in FY2025. It is unclear whether the figures were restated.", "a negation, hedge or guess"),
    ("Revenue grew 6.5% in FY2025, although this may include acquisitions.", "a negation, hedge or guess"),
    ("Revenue grew 6.5% in FY2025, driven by stronger demand.", "an explanation or judgement"),
    ("Revenue grew 6.5% in FY2025, a record for the company.", "an explanation or judgement"),
    ("Revenue grew 6.5% in FY2025, roughly a fifth of its five-year growth.", "a figure in words or a fraction"),
    ("Revenue grew 6.5% in the fourth quarter of FY2025.", "a quarter or part of a year"),
    ("Revenue grew 6.5 percentage points in FY2025.", "percentage points"),
    ("Revenue dipped 6.5% in FY2025.", "a direction word the scorer cannot check"),
])
def test_wording_the_numbers_cannot_check_goes_to_a_person(text, reason):
    assert reason in reasons(us_item(text), GROWTH), text


def test_signs_currencies_units_metrics_and_losses_the_numbers_cannot_check():
    assert reasons(us_item("Revenue grew by -6.5% in FY2025."), GROWTH)  # a minus beside a direction word is a sign error
    assert state(us_item("Revenue grew by -6.5% in FY2025."), GROWTH) == "unsupported"
    assert "a currency after a bare figure" in reasons(us_item("Revenue was 8,432.5 US$ in FY2025."), REVENUE)
    assert "a unit the tables do not use" in reasons(
        us_item("Revenue was $8,432.5 million in FY2025. The amounts are presented in thousands."), REVENUE)
    assert "'loss' beside a figure that is not one" in reasons(
        us_item("The company recorded a loss for FY2025, with revenue of $8,432.5 million."), REVENUE)
    eps_grid = [["(in millions, except per share)", "FY2025", "FY2024"], ["Revenue", "8,432.5", "7,915.2"],
                ["Basic earnings per share", "15.64", "14.10"], ["Diluted earnings per share", "15.28", "13.90"]]
    diluted = gold("15.28", operands=[("t1r3c1", "15.28")], program="t1r3c1")
    item = loss_item("Diluted earnings per share were $15.28 in FY2025.", grid=eps_grid, question="Diluted EPS in FY2025?")
    assert reasons(item, diluted) == []
    item = loss_item("Basic earnings per share were $15.28 in FY2025.", grid=eps_grid, question="Diluted EPS in FY2025?")
    assert "a metric name that is not its figure's" in reasons(item, diluted)


def test_audit_counts_any_persons_overrule_and_waits_until_complete(tmp_path):
    items = [us_item("Revenue was $8,432.5 million in FY2025.").model_copy(update={"id": f"i{n}"}, deep=True) for n in range(4)]
    store = GoldStore(tmp_path)
    store.add_question(REVENUE)
    result = {"code": ["i0", "i1", "i2", "i3"], "person": [], "audit": ["i0", "i1"], "audit_size": 2}
    store.add_label(GoldLabel(item_id="i0", status="correct", useful=True, annotator="alice"))
    assert audit(result, store, items)["status"] == "incomplete"  # i1 not labelled yet: nothing decided, nothing sent
    store.add_label(GoldLabel(item_id="i1", status="correct", useful=True, annotator="alice"))
    store.add_label(GoldLabel(item_id="i1", status="incorrect", useful=False, annotator="bob"))  # a second reader overrules
    store.add_label(GoldLabel(item_id="i0", status="incorrect", useful=False, annotator="bob"))
    verdict = audit(result, store, items)
    assert verdict["overruled"] == ["i0", "i1"] and verdict["code_labels_stand"] is False
    store.add_label(GoldLabel(item_id="i0", status="correct", useful=True, annotator="adj", adjudicated=True))
    store.add_label(GoldLabel(item_id="i1", status="correct", useful=True, annotator="adj", adjudicated=True))
    verdict = audit(result, store, items)  # the adjudicator reverses both overrules
    assert verdict["overruled"] == [] and verdict["code_labels_stand"] and verdict["code_labels_kept"] == ["i2", "i3"]
    assert audit(result | {"audit_size": 3}, store, items)["code_labels_stand"] is False  # an audit smaller than planned


def test_cli_audit_and_import_guards(tmp_path):
    from faithguard import cli

    items = [us_item("Revenue was $8,432.5 million in FY2025.").model_copy(update={"id": f"i{n}"}, deep=True) for n in range(3)]
    for item in items:
        item.question.split = "test"
    path = tmp_path / "items.jsonl"
    write_jsonl(path, items)
    store = GoldStore(tmp_path / "gold")
    store.add_question(REVENUE)
    store.save()
    with pytest.raises(SystemExit, match="pre-registered"):  # the audit's size and seed are fixed on locked splits
        cli.main(["labelling", "triage", "--items", str(path), "--gold", str(store.root), "--filed", "x", "--audit", "0"])
    with pytest.raises(SystemExit, match="triage"):  # no audit before triage
        cli.main(["labelling", "audit", "--items", str(path), "--gold", str(store.root)])
    export = tmp_path / "export.json"
    export.write_text(json.dumps([{"data": {"task_key": "k"}, "annotations": [{"completed_by": {"email": "a@x"}, "result": [
        {"type": "choices", "from_name": "status", "value": {"choices": ["correct"]}}]}]}]), encoding="utf-8")
    mapping = tmp_path / "m.json"
    mapping.write_text(json.dumps({"k": "i0"}), encoding="utf-8")
    for _ in range(2):  # importing the same export twice adds its labels once
        cli.main(["labelling", "import", "--export", str(export), "--mapping", str(mapping), "--gold", str(store.root)])
    assert len(GoldStore.load(store.root).labels["i0"]) == 1
