"""The automatic-extraction run's cleaning and scoring (the PDF tools themselves are not run here)."""

from faithguard.data import extraction as ex

GOLD = [
    ["", "Group", "Group", "Bank", "Bank"],
    ["For the year ended 31 December", "2025", "2024", "2025", "2024"],
    ["", "Rs. '000", "Rs. '000", "Rs. '000", "Rs. '000"],
    ["Gross income", "300,747,904", "228,476,799", "243,601,451", "190,538,072"],
    ["Impairment charges for loans and other losses", "(12,345,678)", "(9,876,543)", "-", "-"],
    ["Profit for the year", "48,215,330", "44,102,870", "45,870,120", "42,015,440"],
]


def test_figures_are_read_in_one_form():
    assert ex.figure("(12,345,678)") == "-12345678" and ex.figure("1,234*") == "1234"
    assert ex.figure("-") == ex.figure("–") == "-"
    assert ex.figure("Rs.") is None and ex.figure("000") is None and ex.figure("2025/26") is None


def test_a_table_scored_against_itself_is_complete():
    s = ex.score(GOLD, GOLD)
    assert s["figures"] == 10 and s["found"] == 10 and s["table_complete"] and s["wrong"] == 0


def test_note_columns_wrapped_labels_and_split_cells_are_handled_alike():
    # what tools return: a note column, a label split over two lines, a label split mid-word, blank rows
    tool = [
        ["", "", "Group", "", "Bank", ""],
        ["For the year end", "ed 31 December", "2025", "2024", "2025", "2024"],
        ["", "Note", "Rs 000", "Rs 000", "Rs 000", "Rs 000"],
        ["Gross inc", "ome 7", "300,747,904", "228,476,799", "243,601,451", "190,538,072"],
        ["Impairment charges for loans and", "", "", "", "", ""],
        ["other losses", "8", "(12,345,678)", "(9,876,543)", "-", "-"],
        ["", "", "", "", "", ""],
        ["Profit for the year", "", "48,215,330", "44,102,870", "45,870,120", "42,015,440"],
    ]
    s = ex.score(GOLD, ex.clean(tool))
    assert s["found"] == 10 and s["table_complete"]


def test_misplaced_and_cut_figures_do_not_count():
    tool = [row[:] for row in GOLD]
    tool[3][1] = "300,747"  # a figure cut at a column boundary: wrong, not just missing
    tool[5][3], tool[5][4] = tool[5][4], tool[5][3]  # two figures swapped
    s = ex.score(GOLD, tool)
    assert s["found"] == 7 and s["wrong"] == 3 and s["rows_complete"] == 1 and not s["table_complete"]


def test_a_row_without_its_label_cannot_be_matched():
    tool = [row[:] for row in GOLD]
    tool[3][0] = ""  # the label lost, as pdfplumber's line strategy does
    assert ex.score(GOLD, tool)["found"] == 6


def test_pages_come_from_the_report_file(tmp_path):
    report = tmp_path / "2025.yaml"
    report.write_text("# PDF pages (as a viewer numbers them): t1 pages 334, 335; t2 pages 336.\nissuer: X\n", encoding="utf-8")
    assert ex.statement_pages(report) == {"t1": [334, 335], "t2": [336]}


def test_choice_is_seeded_and_covers_both_splits(tmp_path):
    reports = [tmp_path / f"R{i}" / "2025.yaml" for i in range(12)]
    split = {r: ("test" if i % 2 else "calibration") for i, r in enumerate(reports)}
    first = ex.choose_reports(reports, split.get, per_split=3, seed=2026)
    assert first == ex.choose_reports(reports, split.get, per_split=3, seed=2026)
    assert sorted(split[r] for r in first) == ["calibration"] * 3 + ["test"] * 3


def test_the_best_tool_is_never_the_reference():
    rows = [
        {"issuer": "A", "table": "t1", "pages": [1], "tool": tool, "strategy": st, "seconds": 1.0, "error": "",
         "figures": 10, "found": found, "wrong": 0, "rows": 2, "rows_complete": 1, "table_complete": found == 10}
        for tool, st, found in [("pymupdf", "text", 8), ("camelot", "stream", 9), ("pdf_tables", "project", 10)]
    ]
    assert ex.summarise(rows)["best"] == {"tool": "camelot", "strategy": "stream"}
