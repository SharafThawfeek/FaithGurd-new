"""The one-click check: every suggestion's and line-item button's template answer, and every planted error on it,
run in-process with the models off. It lists each warning that fires on a right answer (a template answer, or a
planted error repaired back to the template's figures): none may, except a true "Rounded:". From the repository
root, about 10 minutes:

    python demo/stress/one_click.py [--plants planted.json]
"""
import re
import sys
import time
from collections import Counter

PLANTS = sys.argv[sys.argv.index('--plants') + 1] if '--plants' in sys.argv else None  # where to list the planted errors
sys.path[:0] = ['demo', 'src']
from cases import Demo  # noqa: E402
from ask import figures_match  # noqa: E402

d = Demo()
# a template answer is right by construction: none of these may fire on it
ALTER = re.compile(r"^(The sentence contradicts|Careful, this fix|Unknown line item|“Attributable to”|One year per clause|Not checkable|Wording|"
                   r"The question asks about|The question names no part|Every number is supported|Rounded:|The report covers|"
                   r"FaithGuard checks the numbers, not the words|“000”|The answer says “|"
                   r"A total given as a change|No unit|Accounting brackets|Direction not checked)|is a count, not a report figure|"
                   r"is printed in brackets|looks like a page or note number|because the words .* name that line")
# a planted error repaired back to the template's figures: none of these may fire on it
RIGHT = re.compile(r"^(The sentence contradicts|Careful, this fix|Rounded:|One year per clause|Not checkable|Wording|The question asks about|"
                   r"Unknown line item|The report covers|The question names no part|"
                   r"A total given as a change|No unit|Accounting brackets|Direction not checked)|is a count, not a report figure|"
                   r"looks like a page or note number|because the words .* name that line")
BAD_TEXT = re.compile(r"\ban? (?:grow|rose|fell|grew)\b|\ban (?:rise|fall|decline|drop|growth|decrease)\b|\ba (?:increase|decrease|upturn|uptick)\b",
                      re.I)
plants_out = []
t0 = time.perf_counter(); n = 0; fp = []; notes = Counter(); planted_notes = Counter(); actions = Counter(); dropped = 0; refused = 0
for rid in d.reports:
    c = d.chips(rid)
    for q in c["suggestions"] + [x["question"] for x in c["line_items"]]:
        draft = d.ask_draft(rid, q)
        if "error" in draft:
            refused += 1; fp.append(("draft refused", rid, q, draft["error"])); continue
        case = d.ask(rid, q, draft["answer"]); n += 1; actions[("template", case["output"]["action"])] += 1
        if case["output"]["action"] != "send":
            fp.append(("template not sent", rid, q, case["output"]["action"]))
        for x in case["caveats"]:
            notes[x[:50]] += 1
            if ALTER.search(x): fp.append(("template", rid, q, x))
        planted = d.plant_errors(case["id"])
        plants_out.append({'report': rid, 'question': q, 'template': draft['answer'], 'edits': planted['edits']})
        dropped += planted["dropped"]
        for e in planted["edits"]:
            if BAD_TEXT.search(e["answer"]): fp.append(("planted text", rid, e["label"], e["answer"]))
            r = d.case(case["id"], e["answer"]); n += 1; actions[("planted", r["output"]["action"])] += 1
            ok = r["output"]["action"] == "repair" and figures_match(r["output"]["text"], draft["answer"])
            if r["output"]["action"] == "repair" and not ok:
                fp.append(("planted repair not back to the template", rid, e["label"], r["output"]["text"]))
            for x in r["caveats"]:
                planted_notes[x[:50]] += 1
                if ok and RIGHT.search(x): fp.append(("planted repair right but flagged", rid, e["label"], x))
if PLANTS:
    import json
    json.dump(plants_out, open(PLANTS, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(n, "cases;", len(fp), "flags;", f"{time.perf_counter()-t0:.0f}s;", dropped, "planted dropped;", refused, "templates refused")
print(dict(actions))
for f in fp:
    print("  ", f)
print("notes seen on templates:", notes.most_common(20))
print("notes seen on planted:", planted_notes.most_common(30))
