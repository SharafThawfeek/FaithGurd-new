"""The demo's examples and how one is run: the live pipeline plus the trained models' outputs.

Two groups of examples:
    fictional  the six hand-written items on a fictional bank (faithguard.demo), in the repository
    pilot      a few real AI answers from the pilot (development issuers), read at run time from the local,
               gitignored data/ folder; which ones is listed in data/demo/examples.json (not in git)

Every case runs the live pipeline (Channel B, the policy, the rule repairer, executor and gate). Channel A
and the trained repairer run live when loaded (demo.models), else their stored outputs are shown:
data/demo/cache.json (computed on this laptop by demo/precompute.py) or the Kaggle pilot run.

A third group, "ask", holds the presenter's own questions on these reports (demo/ask.py), kept in memory
for the session only.
"""

from __future__ import annotations

import json
import re
import secrets
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

from faithguard.detect import detect
from faithguard.pipeline import run
from faithguard.policy import ThresholdPolicy
from faithguard.records import Item, RepairOutput, read_jsonl

from ask import (Unanswerable, candidate_questions, caveats, contradictions, draft, figures_match, make_item, missing_year,
                 other_company, plant, read_question, released_problems, reports_of)
from models import ANSWER_TOKENS
from views import catch_view, channel_a_view, control_view, evidence_view, jsonable, output_view, repair_view

ROOT = Path(__file__).resolve().parent.parent
DEMO_DATA = ROOT / "data" / "demo"
POLICY = ROOT / "runs" / "policy" / "controlled" / "policy.pkl"
POLICY_RESULTS = ROOT / "runs" / "policy" / "controlled" / "results.json"

FICTIONAL_TITLES = {
    "none": ("Correct answer", "Every number traces to the Group figures (2025, and 2024 for the growth), so it is sent unchanged."),
    "entity": ("Entity error", "The answer quotes the Bank's figures for a question about the Group."),
    "scale": ("Scale error", "Rs. '000 read as millions: the amount is a thousand times too large."),
    "period": ("Period error", "The 2024 figure is given for FY2025."),
    "sign": ("Sign error", "Profit rose, but the answer says it fell."),
    "missing_operand": ("Missing operand", "Return on equity is not in the evidence. 15.2% matches no ratio of two cells, so the "
                        "answer is withheld. A figure that does match one is traced to those cells and sent: 3.8% (net interest "
                        "income ÷ total assets, what the trained repairer writes here) or 29.5% (profit after tax ÷ net interest "
                        "income). With no such line in the evidence, the checker cannot tell what a ratio is about (a known limitation)."),
}

# One-click edits for the try-it box, each checked by demo/precompute.py to give this action. Free typing
# works too, but the rule checker reads one period per clause: "from Rs. 13,004 million to ..." with no
# year is checked as FY2025 (a known limitation), so presenters start from these.
FICTIONAL_EDITS = {
    "none": [("Swap in the Bank's figure", "Group profit after tax rose 9.3% to Rs. 12,450 million in FY2025.", "repair"),
             ("Flip the direction", "Group profit after tax fell 9.3% to Rs. 14,213 million in FY2025.", "repair"),
             ("Read Rs. '000 as millions", "Group profit after tax rose 9.3% to Rs. 14,212,560 million in FY2025.", "repair"),
             ("Write it in billions", "Group profit after tax rose 9.3% to Rs. 14.2 billion in FY2025.", "send")],
    "entity": [("Fix both numbers by hand", "Group profit after tax rose 9.3% to Rs. 14,213 million.", "send"),
               ("Fix only the amount", "Group profit after tax rose 7.0% to Rs. 14,213 million.", "repair")],
    "scale": [("Say thousand instead", "Group profit after tax was Rs. 14,212,560 thousand in FY2025.", "send"),
              ("Write it in billions", "Group profit after tax was Rs. 14.2 billion in FY2025.", "send")],
    "period": [("Use the 2025 figure", "Group profit after tax was Rs. 14,213 million in FY2025.", "send")],
    "sign": [("Say it rose", "Group profit after tax rose 9.3% in FY2025.", "send"),
             ("Wrong size as well", "Group profit after tax fell 7.0% in FY2025.", "repair")],
    "missing_operand": [("Another made-up ratio", "The Group return on equity was 29.6% in FY2025.", "abstain")],
}
BLINDED = ("data/benchmark-build/main", "data/benchmark-build/main-auto", "labelling")
MAX_ASKED = 200  # own questions kept in memory; the oldest go first
ANSWER_SOURCES = {
    "ai": "Qwen3.5-2B, live on this laptop (the base model: no FaithGuard training)",
    "template": "a template, written from the cells the question names",
    "typed": "typed in the demo",
    "recorded": "Qwen3.5-2B, its answer to this question recorded at rehearsal (the live AI is not loaded)",
    "recorded-failed": "Qwen3.5-2B, its answer to this question recorded at rehearsal (the live AI did not answer)",
}
REHEARSAL = Path(__file__).resolve().parent / "rehearsal.json"  # the live AI's answers to the script's questions
MAX_SUGGESTIONS = 4
# The stored Kaggle repair outputs, by the run folder data/demo/examples.json points at. Its own label was written while
# v1 was a candidate; the run used the adapter later frozen as v1, and the live adapter reproduces its programs.
KAGGLE_LABELS = {
    "data/benchmark-build/systems-pilot-v1run/systems-pilot-repair-v1":
        "trained repairer v1 (frozen, D-101), run on Kaggle in the systems-pilot rerun (runs/pilot/v1run-repair-v1)",
}
# Pilot captions from data/demo/examples.json (not in git) corrected here, by example id
PILOT_CAPTIONS = {
    "SAMP-2025-06:gemma": "Rs. 1,627,060,300 thousand is about Rs. 1,627 billion, not Rs. 1.63 billion. The checker traces Rs. 1.63 "
                          "billion to the right cell read at the wrong scale, but it did not read “owe its depositors” as the line "
                          "“due to depositors”, so it has no fix to copy, and the answer is withheld with the cell.",
}
# A cut-off AI answer is checked only up to its last complete sentence: an end mark the next sentence follows
# ("Rs. 3,692" does not end one), so a trailing partial number never reaches the checker.
_SENTENCE_END = re.compile(r"[.!?](?=\s+[A-Z(“\"])")


class UnknownExample(LookupError):
    pass


def safe_path(relative: str) -> Path:
    """A configured data path, refused if it points into the blinded main benchmark or the labelling tasks."""
    path = (ROOT / relative).resolve()
    for blinded in BLINDED:
        if path == (ROOT / blinded).resolve() or (ROOT / blinded).resolve() in path.parents:
            raise ValueError(f"{relative} is blinded: the demo uses development (pilot) data only")
    return path


@dataclass
class Example:
    item: Item
    group: str  # fictional | pilot | ask
    title: str
    caption: str
    expect: str | None = None  # the action the example is meant to show
    kaggle: dict = field(default_factory=dict)  # pilot only: the Kaggle run's detector record and trained repair
    edits: list = field(default_factory=list)  # (label, answer, expected action) for the try-it box
    report: str | None = None  # ask only: the report's id
    planted: bool = False  # ask only: edits hold the planted errors, each with the action the pipeline took
    planted_on: str = "original"  # or "repaired": the answer had no supported figure, so they went into its repair
    planted_dropped: int = 0  # planted errors left out because their repair did not give the figures back


def _rows(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    return {r["item_id"]: r for r in (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())}


def load_examples(config: Path = DEMO_DATA / "examples.json") -> list[Example]:
    from faithguard.demo import bank_items

    out = []
    for item, _, injection in bank_items():
        title, caption = FICTIONAL_TITLES[injection.error]
        out.append(Example(item, "fictional", title, caption, injection.expected_action, edits=FICTIONAL_EDITS[injection.error]))
    if not config.exists():
        return out
    spec = json.loads(config.read_text(encoding="utf-8"))
    items_path = safe_path(spec["items"])
    if not items_path.exists():
        return out
    wanted = {e["id"]: e for e in spec["pilot"]}
    items = {i.id: i for i in read_jsonl(items_path, Item) if i.id in wanted}
    runs = safe_path(spec["kaggle_outputs"])
    detector, repairs = _rows(runs / "detector.jsonl"), _rows(runs / "repair-rule-spans.jsonl")
    run_label = KAGGLE_LABELS.get(spec["kaggle_outputs"].replace("\\", "/").strip("/"), spec.get("kaggle_label", ""))
    for item_id, e in wanted.items():
        if item_id in items and items[item_id].question.split in (None, "dev"):
            kaggle = {"detector": detector.get(item_id), "repair": repairs.get(item_id), "run": run_label}
            edits = [tuple(x) for x in e.get("edits", [])]
            caption = PILOT_CAPTIONS.get(item_id, e.get("caption", ""))
            out.append(Example(items[item_id], "pilot", e["title"], caption, e.get("expect"), kaggle, edits))
    return out


def load_policy():
    """The certified outcome-aware policy (LightGBM), or None; and its certificate for display."""
    certificate: dict = {}
    if POLICY_RESULTS.exists():
        results = json.loads(POLICY_RESULTS.read_text(encoding="utf-8"))
        family = next((f for f in results["families"] if f["family"].startswith("outcome_aware")), {})
        mix = results.get("chosen_detail", {}).get("action_mix_test", {})
        curve = results.get("budget_curve") or []  # one list of points, or (since D-099) one list per outcome model
        certificate = {
            "alpha": results["alpha"], "delta": results["delta"], "setting": family.get("chosen"),
            "certified": f"{family.get('certified')} of {family.get('settings')}", "p_value": family.get("p_chosen"),
            "p_issuer": family.get("cluster_p_calibration"), "fit_items": results["counts"]["fit"]["items"],
            "calibration_items": results["counts"]["calibration"]["items"],
            "budget_curve": curve.get("lightgbm", []) if isinstance(curve, dict) else curve,  # the deployed policy's model
            "test": family.get("test", {}), "test_mix": {k: v / max(1, sum(mix.values())) for k, v in mix.items()},
        }
        if isinstance(curve, dict) and curve.get("neural"):
            certificate["budget_curve_neural"] = curve["neural"]
    if not POLICY.exists():
        return None, certificate
    from faithguard.policy.deployed import OutcomeAwarePolicy

    return OutcomeAwarePolicy.load(POLICY), certificate


class Demo:
    def __init__(self, models=None, cache_path: Path = DEMO_DATA / "cache.json", config: Path = DEMO_DATA / "examples.json"):
        self.examples = {e.item.id: e for e in load_examples(config)}
        self.policy, self.certificate = load_policy()
        self.cache_path, self.cache_mtime, self._cache = cache_path, None, {}
        self.models = models
        self.reports = reports_of(self.examples.values())
        self.asked: OrderedDict[str, Example] = OrderedDict()
        self.generated: dict[tuple[str, str, str], str] = {}  # (report, question, answer) -> source, for answers the demo wrote
        self.ask_lock = threading.Lock()
        self.ask_count = 0
        self.run_id = secrets.token_hex(2)  # own questions' ids differ between server starts
        self.recorded = json.loads(REHEARSAL.read_text(encoding="utf-8")) if REHEARSAL.exists() else {}
        self._chips: dict[str, dict] = {}
        self._chips_lock = threading.Lock()

    @property
    def cache(self) -> dict:
        """data/demo/cache.json, read again whenever precompute rewrites it (no restart needed)."""
        mtime = self.cache_path.stat().st_mtime if self.cache_path.exists() else None
        if mtime != self.cache_mtime:
            self._cache = json.loads(self.cache_path.read_text(encoding="utf-8")) if mtime else {}
            self.cache_mtime = mtime
        return self._cache

    @cache.setter
    def cache(self, value: dict) -> None:
        self._cache = value

    def listing(self) -> list[dict]:
        return [{"id": e.item.id, "group": e.group, "title": e.title, "caption": e.caption, "expect": e.expect,
                 "issuer": e.item.question.issuer, "country": e.item.question.country} for e in self.examples.values()]

    def status(self) -> dict:
        models = self.models.status() if self.models else {"channel_a": {"state": "off", "detail": "started with --no-models"},
                                                            "repairer": {"state": "off", "detail": "started with --no-models"}}
        cache = self.cache
        stored = {
            "channel_a": sum(1 for i in self.examples if cache.get(i, {}).get("channel_a") or self.examples[i].kaggle.get("detector")),
            "repairer": sum(1 for i in self.examples if cache.get(i, {}).get("trained_repair") or self.examples[i].kaggle.get("repair")),
        }
        return {**models, "policy": {"state": "ready" if self.policy else "failed",
                                     "detail": "LightGBM outcome models, live on CPU" if self.policy else
                                     f"no {POLICY.relative_to(ROOT)}: run `faithguard policy`; threshold v0 decides meanwhile"},
                "stored": stored, "examples": len(self.examples), "run_id": self.run_id}

    def example(self, example_id: str) -> Example:
        e = self.examples.get(example_id) or self.asked.get(example_id)
        if e is None:
            raise UnknownExample(example_id)
        return e

    def item_for(self, example_id: str, answer: str | None) -> tuple[Example, Item, bool]:
        e = self.example(example_id)
        if answer is None or answer == e.item.answer.text:
            return e, e.item, False
        edited = e.item.model_copy(update={"answer": e.item.answer.model_copy(update={"text": answer, "generator": "edited in the demo"})})
        return e, edited, True

    def case(self, example_id: str, answer: str | None = None, channel_a: bool = True) -> dict:
        e, item, edited = self.item_for(example_id, answer)
        policy = self.policy or ThresholdPolicy()
        final = run(item, policy=policy)
        det = final.detector
        cached = {} if edited else self.cache.get(item.id, {})

        # Channel A: live, else computed earlier on this laptop, else the Kaggle run's spans
        live_a = self.models is not None and self.models.channel_a.state == "ready"
        a_view, failed = None, ""
        if live_a and not channel_a:
            a_view = {"source": "pending", "note": "computing…"}  # the browser asks /api/channel-a next
        elif live_a:
            try:
                a_view = self.channel_a_live(item, det)
            except Exception as err:  # fall back to stored output rather than lose the case
                failed = f"live Channel A failed ({type(err).__name__}); "
        if a_view is None and cached.get("channel_a"):
            c = cached["channel_a"]
            a_view = channel_a_view(item, c["tokens"], "laptop", note=f"{failed}computed earlier on this laptop ({c.get('device', '')})", det=det)
        elif a_view is None and not edited and e.kaggle.get("detector"):
            spans = e.kaggle["detector"]["spans"]
            a_view = channel_a_view(item, [[s["start"], s["end"], s["score"], s["slot"]] for s in spans], "kaggle-spans",
                                    note=f"{failed}flagged spans from the Kaggle pilot run (token probabilities were not stored)", det=det)
        elif a_view is None:
            a_view = {"source": None, "note": failed + ("Channel A is not loaded here; stored outputs cover only the original answers."
                                                        if edited else "Channel A is not loaded and has no stored output for this answer.")}

        # the trained repairer: stored output for this exact answer (Kaggle pilot run, or this laptop)
        trained = None
        if not edited and e.kaggle.get("repair"):
            rep = RepairOutput.model_validate(e.kaggle["repair"])
            trained = repair_view(item, det, rep, "kaggle", e.kaggle.get("run") or "Kaggle pilot run")
        elif cached.get("trained_repair"):
            c = cached["trained_repair"]
            rep = RepairOutput.model_validate(c["output"])
            trained = repair_view(item, det, rep, "laptop", f"trained repairer v1 (frozen, D-101), computed earlier on this laptop's GPU in {c['seconds']:.1f} s")

        rule = repair_view(item, det, final.repair, "live", "rule repairer v0, live") if final.repair else None
        if rule is None and final.action != "send":
            # the policy abstained, so the pipeline did not repair; show what the rules would write, for comparison
            from faithguard.repair import repair

            rule = repair_view(item, det, repair(item, det), "live", "rule repairer v0, live (for comparison: the policy withheld the answer)")
            rule["not_released"] = True

        report = self.reports.get(e.report or e.item.question.issuer)  # its name on screen, for the sidebar examples too
        return jsonable({
            "id": e.item.id, "group": e.group, "title": e.title, "caption": e.caption, "expect": e.expect, "edited": edited,
            "question": e.item.question.model_dump(mode="json"), "answer": item.answer.text, "original_answer": e.item.answer.text,
            "generator": e.item.answer.generator, "evidence": evidence_view(item, det),
            "report": {"id": report.id, "name": report.name, "real": report.real} if report else None, "planted": e.planted,
            "planted_on": e.planted_on, "planted_dropped": e.planted_dropped,
            # the known limitations this answer runs into, for the sidebar examples and their edits as for own questions
            "caveats": caveats(item, det, final.action) + self.released_contradictions(item, final) + released_problems(item, final),
            "edits": [{"label": label, "answer": answer, "expect": expect} for label, answer, expect in e.edits],
            "catch": catch_view(item, det, a_view),
            "control": control_view(item, det, final, self.policy, self.certificate),
            "correct": {"action": final.action, "rule": rule, "trained": trained,
                        "live_repairer": bool(self.models and self.models.repairer.state == "ready")},
            "output": output_view(item, final),
            "reference": cached.get("reference") if not edited else None,
        })

    def channel_a_live(self, item: Item, det) -> dict:
        tokens, seconds = self.models.channel_a_tokens(item, det)
        if tokens is None:
            raise RuntimeError("Channel A is not ready")
        return channel_a_view(item, tokens, "live", note=f"{self.models.channel_a.detail}; this answer took {seconds * 1000:.0f} ms", det=det)

    def channel_a_only(self, example_id: str, answer: str | None) -> dict:
        _, item, _ = self.item_for(example_id, answer)
        if self.models is None or self.models.channel_a.state != "ready":
            return {"source": None, "note": "Channel A is not loaded here; stored outputs cover only the original answers."}
        try:
            return self.channel_a_live(item, detect(item))
        except Exception as err:
            return {"source": None, "note": f"Live Channel A failed on this text ({type(err).__name__}); the rest of the pipeline is unaffected."}

    def trained_live(self, example_id: str, answer: str | None) -> dict:
        _, item, _ = self.item_for(example_id, answer)
        det = detect(item)
        if self.models is None or self.models.repairer.state != "ready":
            return {"error": "The trained repairer is not loaded on this laptop; its stored outputs are shown instead."}
        try:
            rep, seconds = self.models.repair(item, det)
        except Exception as err:
            return {"error": f"The trained repairer failed on this text ({type(err).__name__}); the rule repairer's result stands."}
        return jsonable(repair_view(item, det, rep, "live", f"trained repairer v1 (frozen, D-101), live on this laptop's GPU in {seconds:.1f} s"))

    def released_contradictions(self, item: Item, final) -> list[str]:
        """A sentence of the released text (sent or repaired) that contradicts itself, said on screen (ask.contradictions)."""
        if final.action not in ("send", "repair") or not final.text:
            return []
        if final.text == item.answer.text:
            return contradictions(final.text, final.detector)
        released = item.model_copy(update={"answer": item.answer.model_copy(update={"text": final.text})})
        return contradictions(final.text, detect(released))

    # -- ask your own question ----------------------------------------------

    def report(self, report_id: str):
        if report_id not in self.reports:
            raise UnknownExample(f"report {report_id}")
        return self.reports[report_id]

    def chips(self, report_id: str) -> dict:
        """The report's one-click questions, kept only when the template answers them and the live pipeline sends that
        answer: what is clicked on stage has been checked. Computed once per report (a few seconds on a real report)."""
        with self._chips_lock:
            if report_id in self._chips:
                return self._chips[report_id]
        r = self.report(report_id)
        policy = self.policy or ThresholdPolicy()

        def sent(question: str) -> bool:
            """The template answers it, the pipeline sends that, and the checker read the line item it is about."""
            try:
                item = make_item(r, "chip", question, draft(r, question), "template")
                final = run(item, policy=policy)
            except Exception:
                return False
            return final.action == "send" and all(c.intended.metric is not None for c in final.detector.checks)

        suggested, items = candidate_questions(r)
        out = {"suggestions": [q for q in suggested if sent(q)][:MAX_SUGGESTIONS],
               "line_items": [{"label": label, "question": q} for label, q in items if sent(q)]}
        with self._chips_lock:
            self._chips[report_id] = out
        return out

    def prepare(self) -> threading.Thread:
        """Check every report's one-click questions in the background, so the Ask screen opens at once."""
        thread = threading.Thread(target=lambda: [self.chips(r) for r in self.reports], daemon=True)
        thread.start()
        return thread

    def report_listing(self) -> list[dict]:
        out = []
        for r in self.reports.values():
            preview = make_item(r, "preview", "", "", "")
            out.append({"id": r.id, "name": r.name, "country": r.country, "real": r.real, **self.chips(r.id),
                        "evidence": jsonable(evidence_view(preview, detect(preview)))})
        return out

    def ai_ready(self) -> bool:
        return self.models is not None and self.models.repairer.state == "ready"

    def _recorded(self, r, question: str, recorded: dict, source: str) -> dict:
        self.generated[(r.id, question.strip(), recorded["answer"])] = source
        return {"answer": recorded["answer"], "source": "recorded", "by": f"{ANSWER_SOURCES[source]} on {recorded['recorded']}"}

    def ask_ai(self, report_id: str, question: str) -> dict:
        r = self.report(report_id)
        if (problem := other_company(r, question) or missing_year(r, question)):
            return {"error": problem}  # the same refusal as the table answer's, before the AI is asked
        recorded = self.recorded.get(r.id, {}).get(" ".join(question.split()))
        stopped = bool(getattr(self.models, "ai_stopped", False))
        if not self.ai_ready():
            if recorded:  # the AI is off (no GPU, --no-models, or it stopped answering): its answer to this question at rehearsal
                return self._recorded(r, question, recorded, "recorded-failed" if stopped else "recorded")
            if stopped:
                return {"error": "The AI is off: the model on the GPU failed several times in a row. "
                                 "Write a template answer from the table, or type one."}
            return {"error": "The AI is not loaded on this laptop (it needs the GPU and the model files): "
                             "write a template answer from the table, or type one."}
        try:
            text, seconds, cut = self.models.answer(question, r.evidence)
        except Exception as err:
            if recorded:
                return self._recorded(r, question, recorded, "recorded-failed")
            return {"error": f"The AI could not answer ({type(err).__name__}). Write a template answer from the table, or type one."}
        if not text:
            return {"error": "The AI gave an empty answer. Ask again in other words, or type an answer."}
        out = {}
        if cut:  # it ran out of tokens mid-sentence, maybe mid-number: check only the sentences it finished
            ends = list(_SENTENCE_END.finditer(text))
            if not ends:
                return {"error": f"The AI's answer ran past {ANSWER_TOKENS} tokens and was cut off before a sentence clearly "
                                 "ended, so it is not checked. Ask a shorter question, write a template answer from the table, or type one."}
            text = text[:ends[-1].end()]
            out["note"] = f"The AI's answer ran past {ANSWER_TOKENS} tokens and was cut off; only its complete sentences are checked."
        self.generated[(r.id, question.strip(), text)] = "ai"
        return {"answer": text, "seconds": round(seconds, 1), "source": "ai", "by": ANSWER_SOURCES["ai"], **out}

    def ask_draft(self, report_id: str, question: str) -> dict:
        r = self.report(report_id)
        if (problem := other_company(r, question)):
            return {"error": problem}
        try:
            text = draft(r, question)
        except Unanswerable as err:
            return {"error": str(err)}
        self.generated[(r.id, question.strip(), text)] = "template"
        return {"answer": text, "source": "template", "by": ANSWER_SOURCES["template"]}

    def ask(self, report_id: str, question: str, answer: str) -> dict:
        """Register the question and its answer as an example of its own, and run it."""
        r = self.report(report_id)
        if (problem := other_company(r, question)):
            return {"error": problem}
        source = self.generated.get((r.id, question.strip(), answer), "typed")
        with self.ask_lock:
            self.ask_count += 1
            item_id = f"ask-{self.run_id}-{self.ask_count}"
            item = make_item(r, item_id, question, answer, ANSWER_SOURCES[source])
            note = read_question(r, question)[2]
            self.asked[item_id] = Example(item, "ask", "Your question", note, report=r.id)
            while len(self.asked) > MAX_ASKED:
                self.asked.popitem(last=False)
        return self.case(item_id)

    def plant_errors(self, example_id: str) -> dict:
        """Errors planted in the question's original answer, each with the action the live pipeline takes on it."""
        e = self.example(example_id)
        if e.group != "ask":
            return {"edits": []}
        if not e.planted:
            policy = self.policy or ThresholdPolicy()

            def with_text(text: str) -> Item:
                return e.item.model_copy(update={"answer": e.item.answer.model_copy(update={"text": text})})

            det = detect(e.item)
            base, variants = e.item, plant(e.item, det)
            if not any(c.verdict == "supported" for c in det.checks):
                # a wrong answer has no supported figure to spoil: plant into its repair, if it got one that changed a figure
                final = run(e.item, policy=policy)
                if final.action == "repair" and final.text and final.text != e.item.answer.text:
                    base = with_text(final.text)
                    variants = plant(base, detect(base))
                    e.planted_on = "repaired"
            edits, e.planted_dropped = [], 0
            for label, text in variants:
                try:
                    final = run(with_text(text), policy=policy)
                except Exception:  # a variant the pipeline cannot read is not offered
                    continue
                if final.action == "repair" and not figures_match(final.text, base.answer.text):
                    e.planted_dropped += 1  # its repair does not give the figures back (a frozen-checker limitation)
                    continue
                edits.append((label, text, final.action))
            e.edits, e.planted = edits, True
        return {"edits": [{"label": label, "answer": answer, "expect": expect} for label, answer, expect in e.edits],
                "on": e.planted_on, "dropped": e.planted_dropped}
