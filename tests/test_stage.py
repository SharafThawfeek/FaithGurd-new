"""The new demo (stage/) keeps the tested page's rules and stays offline."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "stage" / "static"
SIMPLE = (ROOT / "demo" / "static" / "simple.js").read_text(encoding="utf-8")
LOGIC = (STATIC / "logic.js").read_text(encoding="utf-8")


def block(start: str, end: str) -> str:
    a = SIMPLE.index(start)
    return SIMPLE[a:SIMPLE.index(end, a)].rstrip()


def test_every_rule_is_the_tested_pages_word_for_word():
    for start, end in [("const NOTE = {", "// ---------------------------------------------------------------- helpers"),
                       ("function h(tag, attrs", "async function api("),
                       ("// ---------------------------------------------------------------- table cells", "// ---------------------------------------------------------------- status"),
                       ("function marked(d) {", "function renderResult() {"),
                       ("function trickName(label) {", "function renderTricks() {")]:
        assert block(start, end) in LOGIC, f"stage/static/logic.js drifted from demo/static/simple.js at {start!r}"


def test_the_mark_rule_copies_the_marked_function():
    rule = re.search(r"const cls = (flagged \|\| unread \|\| other.*?: \"bad\");", SIMPLE, re.S).group(1)
    assert " ".join(rule.split()) in " ".join(LOGIC.split())


def test_nothing_loads_from_the_network():
    for path in STATIC.glob("*.*"):
        text = path.read_text(encoding="utf-8")
        hits = [u for u in re.findall(r"https?://[^\s\"'`)]+", text) if not u.startswith("http://www.w3.org/")]
        assert not hits, f"{path.name} names {hits}"
    assert (STATIC / "vendor" / "three.module.min.js").is_file() and (STATIC / "vendor" / "three.core.min.js").is_file()


def test_the_server_serves_these_pages_on_the_demos_api():
    source = (ROOT / "stage" / "serve.py").read_text(encoding="utf-8")
    assert 'app.STATIC = HERE / "static"' in source
    index = (STATIC / "index.html").read_text(encoding="utf-8")
    for name in re.findall(r'(?:href|src)="([^"#:]+)"', index):
        assert (STATIC / name).is_file(), name


def test_the_page_never_promises_more_than_the_results():
    pages = "".join((STATIC / n).read_text(encoding="utf-8") for n in ("main.js", "scene.js", "index.html"))
    for claim in ("Every number checks out", "guaranteed", "production-ready", "All clear"):
        assert claim not in pages
    assert "Thresholds certified on practice data only" in pages and "Studied. Not in the decision" in pages
    assert "Fix by the rule repairer" in pages
