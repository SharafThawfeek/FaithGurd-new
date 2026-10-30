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
    # and the words it keys on inside them: the line form of "The question asks about", a fix moved to another line, the
    # withheld "grew X% to Y" (written with both years' figures, it can be sent)
    for prefix in [*prefixes, "Wording:", "direction word", "is printed in brackets", "but the answer gives the figure for",
                   "the line the question asks", "both years"]:
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
// as the DOM's replaceChildren, which (unlike h()) writes a null as the text "null"
const shown = (x) => x !== null && typeof x === "object" ? text(x) : String(x);
const document = { getElementById: (id) => (els[id] = els[id] || { replaceChildren(...k) { this.text = k.map(shown).join(" "); }, scrollIntoView() {} }),
                   querySelectorAll: () => [] };
const out = new Function("h", "text", "document", "cases", "els", src + `
  const cases_ = cases.map((d) => {
    state.data = state.original = d; state.tricks = d.tricks || { edits: [] }; state.sourceNote = d.sourceNote || null;
    renderResult();
    return { verdict: text(verdict(d)), marked: text(marked(d)), step1: text(checkList(d)),
             step2: d.output.action === "abstain" ? whyHeld(d) : decision(d), notes: notes(d), page: els.result.text,
             tricks: (els.trickcard || {}).text || "", link: els.full.href };
  });
  // the AI's text when its answer was cut off before a sentence ended, then a refusal with no text
  askError("The AI's answer ran past 120 tokens and was cut off before a sentence clearly ended, so it is not checked.", "The Group's revenue grew by 21.8% and the gross");
  const cut = { text: els.askcut.text, hidden: els.askcut.hidden, error: els.askerr.textContent };
  askError("The template writes lookups, growth rates and changes only. Type an answer.");
  return { cases: cases_, cut, after: { hidden: els.askcut.hidden, error: els.askerr.textContent } };`)(h, text, document, JSON.parse(fs.readFileSync(casesFile, "utf8")), els);
console.log(JSON.stringify(out));
"""


def claim(text, start, verdict="supported", slots=(), relation="cell", entity="group", period="2026", **extra):
    return {"id": f"c{start}", "start": start, "end": start + len(text), "text": text, "kind": "amount", "direction": None,
            "direction_span": extra.get("direction_span"), "verdict": verdict, "slots": list(slots), "relation": relation,
            "intended": {"metric": "profit for the year", "entity": entity, "period": period}, "expected": extra.get("expected"),
            "cells": ["t1r1c1"], "asked": ["t1r1c1"], "came_from": [] if verdict == "supported" else ["t1r1c2"], "same_cell": False,
            "loose_match": extra.get("loose_match", False), "missing": False,
            "cell_labels": {"t1r1c1": "Profit for the year, GROUP 2026 Rs.: 2,579,997,694", "t1r1c2": "Profit for the year, GROUP 2025 Rs.: 3,459,202,495"}}


def case(answer, claims, action, caveats=(), rule=None, **extra):
    return {"id": "ask-test-1", "group": "ask", "answer": answer, "generator": "typed in the demo", "caption": "",
            "report": {"id": "LK:TKYO"}, "catch": {"claims": claims}, "caveats": list(caveats),
            "output": {"action": action, "text": answer}, "correct": {"rule": rule}, **extra}


@pytest.fixture(scope="module")
def page(tmp_path_factory):
    if NODE is None:
        pytest.skip("node is not installed")
    tmp = tmp_path_factory.mktemp("simple")
    figure = "Rs. 3,459,202,495"
    answer = f"The Group's profit for the year was {figure}."
    at = answer.index(figure)
    asked = "FaithGuard checks each number against what the answer says it is, not whether it answers the question asked."
    entity = f"The question asks about the Group, but the answer gives the Bank's figure. {asked}"
    period = f"The question asks about 2026, but the answer gives the 2025 figure. {asked}"
    line = f"The question asks about “Revenue”, but the answer gives the figure for “Gross profit”. {asked}"
    grew = "The Group's profit for the year grew by 2.5% in 2026."  # a fall of 2.5%: only the up/down word is wrong
    rate = "Group profit before tax changed by (22.5%) in 2026."  # a fall in accounting brackets, read as a rise
    level = f"The Group's profit for the year increased by {figure} in 2026."  # the 2025 figure, given as the change
    roe = "The Group's return on equity was 12.8% in 2026."
    bare = "The Group's profit for the year was 3,459,202,495 in 2025."  # the digits with no unit
    rose = "The Group's profit for the year rose 25.4% to Rs. 2,579,997,694 in 2026."  # a rate with only the new year's figure
    year = "Wrong year: the 2025 figure"  # a planted mistake, as /api/plant labels it
    fell = "The Group's profit for the year fell by 13% in 2025."  # a rise of 13% read from the report's printed change column
    direction = ("Direction not checked: “13%” is read from the report's printed change column, so FaithGuard did not check the word "
                 "“fell” beside it: the report prints 13 there, a rise (a known limitation).")
    decr = "The Group's profit for the year decreased by Rs. 879.2 million, or 25.4%, to Rs. 2.58 billion in 2026."
    nav = "Net asset value per share was Rs. 375.23 in 2026 (page 186)."
    split = "The Group's revenue for FY25/26 was Rs. 65,925,260 thousand."
    vs = "Profit before tax: Rs 14.21bn (FY2026) vs Rs 13.87bn (FY2025)."
    cases = {
        "plain": case(answer, [claim(figure, at)], "send",
                      tricks={"edits": [{"label": year, "answer": answer.replace("3,459", "2,579"), "expect": "repair"}], "dropped": 0}),
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
        # a return on equity matched by nothing in the report: it cannot be checked, which is not the same as wrong
        "untraced": case(roe, [claim("12.8%", roe.index("12.8%"), "unsupported", ["metric"], "ratio", loose_match=True)], "abstain"),
        "wordfix": case(grew, [claim("2.5%", grew.index("2.5%"), "unsupported", ["sign"], "growth", expected="a fall of 2.5%",
                                     direction_span=[grew.index("grew"), grew.index("grew") + 4])], "repair",
                        rule={"check": {"text": grew.replace("grew", "declined"), "changes": [
                            {"start": grew.index("grew"), "end": grew.index("grew") + 4, "old": "grew", "new": "declined", "cells": [],
                             "cell_labels": {}, "direction_word": True}]}}),
        "brackets": case(rate, [claim("22.5%", rate.index("22.5%"), "unsupported", ["sign"], "growth", expected="-22.5%")], "repair",
                         rule={"check": {"text": rate.replace("22.5%", "-22.5%"), "changes": []}}),
        "brackets-held": case(rate, [claim("22.5%", rate.index("22.5%"), "unsupported", ["sign"], "growth", expected="-22.5%")], "abstain"),
        "level": case(level, [claim(figure, level.index(figure), period="2025")], "abstain",
                      [f"A total given as a change: “{figure}” follows “increased by”, but it is the report's 2025 figure for profit for the year, "
                       "not the change from 2024. The frozen checker accepts it because it matches a cell (a known limitation)."]),
        "level-sent": case(level, [claim(figure, level.index(figure), period="2025")], "send",
                           [f"A total given as a change: “{figure}” follows “increased by”, but it is the report's 2025 figure for profit for "
                            "the year, not the change from 2024. The frozen checker accepts it because it matches a cell (a known limitation)."]),
        "nounit": case(bare, [claim("3,459,202,495", bare.index("3,459,202,495"), period="2025")], "send",
                       ["No unit: “3,459,202,495” has no unit, but the table is in thousands, so as written it is 1,000 times too small; "
                        "FaithGuard matches its digits to the cell (a known limitation)."]),
        "line": case(answer, [claim(figure, at)], "send", [line]),
        "moved": case(answer, [claim(figure, at, "unsupported", ["metric"], expected="Rs. 2,579,997,694")], "repair",
                      [f"Careful, this fix is not trustworthy: “{figure}” is the report's figure for “Revenue”, the line the question asks about, "
                       "but FaithGuard read “Profit for the year” in the answer's words and changed it to Rs. 2,579,997,694 (a known limitation)."],
                      rule={"check": {"text": answer.replace(figure, "Rs. 2,579,997,694"), "changes": []}}),
        "grewto": case(rose, [claim("25.4%", rose.index("25.4%"), relation="growth"), claim("Rs. 2,579,997,694", rose.index("Rs. 2,579"))], "abstain",
                       ["Every number is supported, yet the policy withholds the answer: a growth rate given with only the new year's figure "
                        "(‘grew X% to Y’) scores just over the policy's 0.5 cut on these reports. Written with both years' figures, it can be sent."]),
        "held": case(answer, [claim(figure, at)], "abstain",
                     ["Every number is supported, yet the policy withholds the answer: it was certified on the controlled track's answers."]),
        # integration of round 3: the notes ask.py writes that the page must not contradict
        "direction": case(fell, [claim("13%", fell.index("13%"), direction_span=[fell.index("fell"), fell.index("fell") + 4])], "abstain", [direction]),
        "direction-sent": case(fell, [claim("13%", fell.index("13%"), direction_span=[fell.index("fell"), fell.index("fell") + 4])], "send",
                               [direction]),
        "ratesign": case(decr, [claim("Rs. 879.2 million", decr.index("Rs. 879"), relation="diff"),
                                claim("25.4%", decr.index("25.4%"), "unsupported", ["sign"], "growth"),
                                claim("Rs. 2.58 billion", decr.index("Rs. 2.58"))], "abstain",
                         ["Rate read as a rise: “25.4%” has no up/down word of its own (the sentence's “decreased” is on Rs. 879.2 million), and the "
                          "frozen checker reads such a rate as a rise (a known limitation); read as a fall, as the sentence says, it matches the report."]),
        "page": case(nav, [claim("Rs. 375.23", nav.index("Rs. 375.23")), claim("186", nav.index("186"), "unsupported", ["value"], expected="340")],
                     "abstain", ["“186” looks like a page or note number, not a report figure, but FaithGuard reads every number as a figure of the "
                                 "line asked about (a known limitation): ignore what it says about it."]),
        "split": case(split, [claim("Rs. 65,925,260 thousand", split.index("Rs. 65"), "unsupported", ["period"], expected="Rs. 59,282,247 thousand")],
                      "repair", ["Careful, this fix is not trustworthy: “Rs. 65,925,260 thousand” is given for “FY25/26”, which the frozen checker "
                                 "reads as 2025, so it changed it to Rs. 59,282,247 thousand, the 2025 figure; the report's FY2025/26 is its 2026 "
                                 "column (a known limitation)."]),
        "bracketyear": case(vs, [claim("Rs 14.21bn", vs.index("Rs 14.21bn")),
                                 claim("Rs 13.87bn", vs.index("Rs 13.87bn"), "unsupported", ["period"], expected="Rs 14.21bn")], "abstain",
                            ["One year per clause: “Rs 13.87bn” has its year in brackets after it (“(FY2025)”), which FaithGuard skips, so it read "
                             "it as 2026, the clause's year (a known limitation); it may be right."]),
        "onwrong": case(answer, [claim(figure, at)], "send",
                        tricks={"edits": [{"label": year, "answer": answer.replace("3,459", "2,579"), "expect": "repair"}], "dropped": 2,
                                "on_wrong": True}),
    }
    (tmp / "harness.js").write_text(HARNESS, encoding="utf-8")
    (tmp / "cases.json").write_text(json.dumps(list(cases.values())), encoding="utf-8")
    run = subprocess.run([NODE, str(tmp / "harness.js"), str(DEMO / "static" / "simple.js"), str(tmp / "cases.json")],
                         capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert run.returncode == 0, run.stderr
    out = json.loads(run.stdout)
    return dict(zip(cases, out["cases"])), out


@pytest.fixture(scope="module")
def shown(page):
    return page[0]


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


# ---------------------------------------------------------------- round-3 mock panel (D-114 follow-up)

def _direct_args(js: str, at: int) -> list[str]:
    """The top-level arguments of the call whose "(" is at js[at], skipping strings and nested brackets."""
    args, depth, start, i = [], 0, at + 1, at
    while i < len(js):
        ch = js[i]
        if ch in "\"'`":
            i = js.index(ch, i + 1) if ch != "`" else js.index("`", i + 1)
            while js[i - 1] == "\\":
                i = js.index(ch, i + 1)
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
            if depth == 0:
                args.append(js[start:i].strip())
                return args
        elif ch == "," and depth == 1:
            args.append(js[start:i].strip())
            start = i + 1
        i += 1
    raise AssertionError("unbalanced call")


def test_no_replace_children_call_can_write_null_on_screen():
    # the DOM's replaceChildren, unlike the page's h(), writes a null argument as the text "null" (round 3, P3-PROJ-01)
    js = (DEMO / "static" / "simple.js").read_text(encoding="utf-8")
    calls = [m.end() - 1 for m in re.finditer(r"\.replaceChildren\(", js)]
    assert len(calls) >= 8
    for at in calls:
        for arg in _direct_args(js, at):
            assert not re.search(r":\s*null$", arg) and arg != "null", js[at - 40:at + 80]


def test_the_trick_card_never_prints_null(shown):
    tricks = shown["plain"]["tricks"]
    assert "Use another year's figure" in tricks and "null" not in tricks and "undefined" not in tricks


def test_a_figure_it_cannot_trace_is_not_called_wrong(shown):
    s = shown["untraced"]
    assert "?" in s["marked"] and "✗" not in s["marked"] and s["step1"].strip().startswith("?")
    assert "could not find where this figure comes from" in s["step2"] and "A number is wrong" not in s["step2"]


def test_a_fix_of_the_up_down_word_says_so(shown):
    s = shown["wordfix"]
    assert "“grew”" in s["step1"] and "the report shows a fall of 2.5%" in s["step1"] and "2.5% is wrong" not in s["step1"]
    assert "Changed the up/down word" in s["page"] and "Changed the numbers" not in s["page"]
    assert "worked out the up/down word" in s["page"] and "It does not check the words around them" not in s["page"]


def test_the_two_repairers_correction_rates_are_given_by_the_same_scorer_too(shown):
    page = shown["repair"]["page"]
    assert "49.4% scored by code" in page and "both corrected 50.6%" not in page


def test_a_fall_in_accounting_brackets_is_a_known_limitation_not_a_fix(shown):
    s = shown["brackets"]
    assert "because of a known limitation" in s["verdict"] and "direction was wrong" not in s["verdict"]
    assert "✗" not in s["marked"] and "accounting brackets" in s["step1"]
    assert "A number is wrong" not in shown["brackets-held"]["step2"] and "may be right" in shown["brackets-held"]["step2"]


def test_a_years_total_given_as_a_change_is_amber_and_explained(shown):
    held, sent = shown["level"], shown["level-sent"]
    assert "?" in held["marked"] and "✓" not in held["marked"] and held["step1"].strip().startswith("?")
    assert "year's total given as a change" in held["step2"] and "Every number matches" not in held["step2"]
    assert "follows “increased by”" in held["step1"] and not any(n.startswith("A total given as a change:") for n in held["notes"])
    assert "Every number checks out" not in sent["verdict"] and "year's total as a change" in sent["verdict"]
    assert "Every number matches" not in sent["step2"]


def test_a_figure_with_no_unit_is_amber(shown):
    s = shown["nounit"]
    assert "Every number checks out" not in s["verdict"] and "no unit" in s["verdict"]
    assert "?" in s["marked"] and "✓" not in s["marked"] and "1,000 times too small" in s["step1"]


def test_another_line_than_the_question_asks_about_is_amber(shown):
    s = shown["line"]
    assert "Every number checks out" not in s["verdict"] and "the figure for “Gross profit”" in s["verdict"] and "“Revenue”" in s["verdict"]
    assert "?" in s["marked"] and "✓" not in s["marked"] and "line the answer names" in s["step2"]


def test_a_fix_that_moves_a_right_figure_to_another_line_is_not_trustworthy(shown):
    s = shown["moved"]
    assert "not trustworthy" in s["verdict"] and "✗" not in s["marked"] and "may be right" in s["step1"]
    assert "Before sending, FaithGuard re-checked" not in s["page"]


def test_a_withheld_answer_gives_the_reason_the_server_gives(shown):
    assert "both years' figures" in shown["grewto"]["step2"] and "only the new year's figure" in shown["grewto"]["step2"]
    for which in ("grewto", "held"):  # not the table size: the same figures in another wording are sent
        assert "smaller tables" not in shown[which]["step2"] and "big real reports" not in shown[which]["step2"], which


def test_a_cut_off_answer_is_shown_greyed_and_not_checked(page):
    cut, after = page[1]["cut"], page[1]["after"]
    assert cut["hidden"] is False and "not checked" in cut["text"] and "The Group's revenue grew by 21.8%" in cut["text"]
    assert after["hidden"] is True and after["error"].startswith("The template answer only covers")


def test_enter_in_the_question_asks_the_ai_as_the_button_does():
    js = (DEMO / "static" / "simple.js").read_text(encoding="utf-8")
    assert 'ask(aiReady() ? "ai" : "table")' not in js and re.search(r'ev\.key === "Enter".*ask\("ai"\)', js)
    assert "scripted" not in js  # the suggested questions, as on the full page


def test_a_wrong_up_down_word_beside_a_printed_change_is_never_called_right(shown):
    held, sent = shown["direction"], shown["direction-sent"]
    assert "?" in held["marked"] and "✓" not in held["marked"] and "did not check the word “fell”" in held["step1"]
    assert "up/down word is wrong" in held["step2"] and "Every number matches" not in held["step2"]
    assert "Every number checks out" not in sent["verdict"] and "up/down word in it is wrong" in sent["verdict"]
    assert not any(n.startswith("Direction not checked") for n in held["notes"])  # said in step 1


def test_a_rate_read_as_a_rise_and_a_page_number_are_not_called_wrong(shown):
    for which, says in (("ratesign", "reads a rate with no up/down word of its own as a rise"), ("page", "page or note number")):
        s = shown[which]
        assert "✗" not in s["marked"] and says in s["step1"] and "A number is wrong" not in s["step2"], which
    assert "25.4%  is right" in shown["ratesign"]["step1"] or "25.4% is right" in shown["ratesign"]["step1"]
    assert "page or note number" in shown["page"]["step2"] and "186 is right" not in shown["page"]["step1"]


def test_a_year_note_says_where_the_year_came_from(shown):
    split, vs = shown["split"], shown["bracketyear"]
    assert "the answer gives it for “FY25/26”, which FaithGuard reads as 2025" in split["step1"] and "no year of its own" not in split["step1"]
    assert "its year is in brackets after it" in vs["step1"] and "no year of its own" not in vs["step1"]
    assert "skips a year written in brackets" in vs["step2"]


def test_tricks_are_refused_on_an_untrusted_fix_and_drops_on_a_misread_answer_say_why(shown):
    assert "fix of this answer is not trustworthy" in shown["moved"]["tricks"]
    assert "FaithGuard reads a number in this answer as wrong" in shown["onwrong"]["tricks"]
    assert "already has a wrong number" not in shown["onwrong"]["tricks"]
