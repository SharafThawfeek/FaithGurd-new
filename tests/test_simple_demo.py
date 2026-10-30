"""The simple demo page (demo/static/simple.*) only uses what the demo server serves."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

DEMO = Path(__file__).resolve().parent.parent / "demo"
NODE = shutil.which("node")


def test_the_simple_page_calls_only_routes_the_server_has():
    js = (DEMO / "static" / "simple.js").read_text(encoding="utf-8")
    server = (DEMO / "app.py").read_text(encoding="utf-8")
    routes = set(re.findall(r'"(/api/[a-z/-]+)"', js))
    assert routes >= {"/api/status", "/api/reports", "/api/ask/ai", "/api/ask/draft", "/api/ask", "/api/plant", "/api/run"}
    for route in routes:
        assert f'"{route}"' in server, route


def test_the_simple_page_loads_its_own_files():
    html = (DEMO / "static" / "simple.html").read_text(encoding="utf-8")
    assert 'src="simple.js"' in html and 'href="simple.css"' in html
    assert 'id="full"' in html and 'id="restart"' in html  # the deep link to the full demo, the restart banner
    assert (DEMO / "static" / "simple.js").exists() and (DEMO / "static" / "simple.css").exists()


def test_the_notes_the_simple_page_keys_on_are_ones_the_server_writes():
    js = (DEMO / "static" / "simple.js").read_text(encoding="utf-8")
    block = re.search(r"const NOTE = \{(.*?)\n\};", js, re.S).group(1)
    prefixes = re.findall(r':\s*"([^"]+)"', block)
    assert len(prefixes) >= 8
    server = (DEMO / "ask.py").read_text(encoding="utf-8") + (DEMO / "cases.py").read_text(encoding="utf-8")
    for prefix in [*prefixes, "Wording:", "direction word", "is printed in brackets"]:
        assert prefix in server, prefix


# ---------------------------------------------------------------- what the page says, run with node on made-up responses

HARNESS = r"""
const fs = require("fs");
const [jsFile, casesFile] = process.argv.slice(2);
let src = fs.readFileSync(jsFile, "utf8");
src = src.slice(0, src.indexOf("(async function start()")).replace(/^function h\(tag[\s\S]*?\n}\n/m, "");
const text = (n) => n == null || n === false ? "" : typeof n === "string" ? n : Array.isArray(n) ? n.map(text).join("") : n.t || "";
const h = (tag, attrs, ...kids) => ({ t: kids.flat(Infinity).map(text).join(" ") });
const els = {};
const document = { getElementById: (id) => (els[id] = els[id] || { replaceChildren(...k) { this.text = k.map(text).join(" "); }, scrollIntoView() {} }),
                   querySelectorAll: () => [] };
const out = new Function("h", "text", "document", "cases", "els", src + `
  return cases.map((d) => {
    state.data = state.original = d; state.tricks = d.tricks || { edits: [] }; state.sourceNote = d.sourceNote || null;
    renderResult();
    return { verdict: text(verdict(d)), marked: text(marked(d)), step1: text(checkList(d)),
             step2: d.output.action === "abstain" ? whyHeld(d) : decision(d), notes: notes(d), page: els.result.text,
             tricks: (els.trickcard || {}).text || "", link: els.full.href };
  });`)(h, text, document, JSON.parse(fs.readFileSync(casesFile, "utf8")), els);
console.log(JSON.stringify(out));
"""


def claim(text, start, verdict="supported", slots=(), relation="cell", entity="group", period="2026", **extra):
    return {"id": f"c{start}", "start": start, "end": start + len(text), "text": text, "kind": "amount", "direction": None,
            "direction_span": None, "verdict": verdict, "slots": list(slots), "relation": relation,
            "intended": {"metric": "profit for the year", "entity": entity, "period": period}, "expected": extra.get("expected"),
            "cells": ["t1r1c1"], "asked": ["t1r1c1"], "came_from": [] if verdict == "supported" else ["t1r1c2"], "same_cell": False,
            "loose_match": False, "missing": False, "cell_labels": {"t1r1c1": "Profit for the year, GROUP 2026 Rs.: 2,579,997,694",
                                                                    "t1r1c2": "Profit for the year, GROUP 2025 Rs.: 3,459,202,495"}}


def case(answer, claims, action, caveats=(), rule=None, **extra):
    return {"id": "ask-test-1", "group": "ask", "answer": answer, "generator": "typed in the demo", "caption": "",
            "report": {"id": "LK:TKYO"}, "catch": {"claims": claims}, "caveats": list(caveats),
            "output": {"action": action, "text": answer}, "correct": {"rule": rule}, **extra}


@pytest.fixture(scope="module")
def shown(tmp_path_factory):
    if NODE is None:
        pytest.skip("node is not installed")
    tmp = tmp_path_factory.mktemp("simple")
    figure = "Rs. 3,459,202,495"
    answer = f"The Group's profit for the year was {figure}."
    at = answer.index(figure)
    entity = "The question asks about the Group, but the answer gives the Bank's figure. FaithGuard checks each number against what the answer says it is, not whether it answers the question asked."
    period = "The question asks about 2026, but the answer gives the 2025 figure. FaithGuard checks each number against what the answer says it is, not whether it answers the question asked."
    cases = {
        "plain": case(answer, [claim(figure, at)], "send"),
        "entity": case(answer, [claim(figure, at, entity="bank")], "send", [entity]),
        "period": case(answer, [claim(figure, at, period="2025")], "send", [period]),
        "sum": case(answer, [claim(figure, at, "unsupported", ["value"], expected="Rs. 498,489 thousand")], "abstain",
                    [f"Not checkable: “{figure}” adds up (or averages) several lines, and FaithGuard compares a figure with one line only (a known limitation)."]),
        "oneyear": case(answer, [claim(figure, at, "unsupported", ["period"], expected="Rs. 2,579,997,694")], "repair",
                        [f"Careful, this fix is not trustworthy: FaithGuard reads one year per clause, so it read “{figure}” as 2026, the clause's year, and changed it, "
                         "but the answer gives it for 2025 (a known limitation)."]),
        "upfrom": case(answer, [claim(figure, at)], "abstain",
                       ["Every number is supported, yet the policy withholds the answer: a direction word (“up”, “down”) beside a looked-up figure ..."]),
        "repair": case(answer, [claim(figure, at, "unsupported", ["period"], expected="Rs. 2,579,997,694")], "repair",
                       rule={"check": {"text": "The Group's profit for the year was Rs. 2,579,997,694.", "changes": []}},
                       sourceNote="The AI's answer ran past 120 tokens and was cut off; only its complete sentences are checked.",
                       tricks={"edits": [], "dropped": 2}),
        "recorded": case(answer, [claim(figure, at)], "send",
                         generator="Qwen3.5-2B, its answer to this question recorded at rehearsal (the live AI did not answer)"),
    }
    (tmp / "harness.js").write_text(HARNESS, encoding="utf-8")
    (tmp / "cases.json").write_text(json.dumps(list(cases.values())), encoding="utf-8")
    run = subprocess.run([NODE, str(tmp / "harness.js"), str(DEMO / "static" / "simple.js"), str(tmp / "cases.json")],
                         capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert run.returncode == 0, run.stderr
    return dict(zip(cases, json.loads(run.stdout)))


def test_a_sent_answer_that_checks_out_says_so_but_never_safe(shown):
    assert "Every number checks out" in shown["plain"]["verdict"] and "✓" in shown["plain"]["marked"]
    assert all("safe to send" not in s["step2"] for s in shown.values())


@pytest.mark.parametrize("which, given", [("entity", "Bank's"), ("period", "2025")])
def test_another_part_or_year_than_the_question_asks_about_is_amber(shown, which, given):
    s = shown[which]
    assert "Every number checks out" not in s["verdict"] and f"the {given} figure" in s["verdict"]
    assert "?" in s["marked"] and "✓" not in s["marked"] and s["step1"].strip().startswith("?")
    assert "not the one the question asks about" in s["step2"]


def test_a_sum_and_a_year_read_from_the_clause_are_not_called_wrong(shown):
    for which in ("sum", "oneyear"):
        s = shown[which]
        assert "?" in s["marked"] and "✗" not in s["marked"], which
        assert "The report says" not in s["step1"] and "The answer used" not in s["step1"], which
    assert "adds up" in shown["sum"]["step2"] and "A number is wrong" not in shown["sum"]["step2"]
    assert "may be right" in shown["oneyear"]["step1"] and "cannot be trusted" in shown["oneyear"]["step2"]
    assert "the 2026 figure, the clause's year" in shown["oneyear"]["step1"]  # where the year came from, as the note says


def test_a_direction_word_withholding_is_explained_as_such(shown):
    assert "“up” or “down”" in shown["upfrom"]["step2"] and "big real reports" not in shown["upfrom"]["step2"]


def test_a_repair_names_the_rule_repairer_and_the_page_carries_the_ai_note_and_the_deep_link(shown):
    page = shown["repair"]["page"]
    assert "rule repairer (v0)" in page and "trained repairer v1" in page and "6.2%" in page and "0.4%" in page
    assert "cut off" in page and "2 planted mistakes left out" in shown["repair"]["tricks"]
    assert shown["repair"]["link"] == "/?case=ask-test-1"


def test_a_recorded_answer_says_why_the_recording_was_used(shown):
    # the server's own reason: the AI is not loaded, or it stopped answering
    assert "recorded at rehearsal (the live AI did not answer):" in shown["recorded"]["page"]
    assert "the live AI is not loaded" not in shown["recorded"]["page"]
