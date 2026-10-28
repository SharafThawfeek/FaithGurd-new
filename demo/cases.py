"""The demo's examples and how one is run: the live pipeline plus the trained models' outputs.

Two groups of examples:
    fictional  the six hand-written items on a fictional bank (faithguard.demo), in the repository
    pilot      a few real AI answers from the pilot (development issuers), read at run time from the local,
               gitignored data/ folder; which ones is listed in data/demo/examples.json (not in git)

Every case runs the live pipeline (Channel B, the policy, the rule repairer, executor and gate). Channel A
and the trained repairer run live when loaded (demo.models), else their stored outputs are shown:
data/demo/cache.json (computed on this laptop by demo/precompute.py) or the Kaggle pilot run.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from faithguard.detect import detect
from faithguard.pipeline import run
from faithguard.policy import ThresholdPolicy
from faithguard.records import Item, RepairOutput, read_jsonl

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
    "missing_operand": ("Missing operand", "Return on equity is not in the evidence, so nothing can confirm or fix it."),
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
    group: str  # fictional | pilot
    title: str
    caption: str
    expect: str | None = None  # the action the example is meant to show
    kaggle: dict = field(default_factory=dict)  # pilot only: the Kaggle run's detector record and trained repair
    edits: list = field(default_factory=list)  # (label, answer, expected action) for the try-it box


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
    for item_id, e in wanted.items():
        if item_id in items and items[item_id].question.split in (None, "dev"):
            kaggle = {"detector": detector.get(item_id), "repair": repairs.get(item_id), "run": spec.get("kaggle_label", "")}
            edits = [tuple(x) for x in e.get("edits", [])]
            out.append(Example(items[item_id], "pilot", e["title"], e.get("caption", ""), e.get("expect"), kaggle, edits))
    return out


def load_policy():
    """The certified outcome-aware policy (LightGBM), or None; and its certificate for display."""
    certificate: dict = {}
    if POLICY_RESULTS.exists():
        results = json.loads(POLICY_RESULTS.read_text(encoding="utf-8"))
        family = next((f for f in results["families"] if f["family"].startswith("outcome_aware")), {})
        mix = results.get("chosen_detail", {}).get("action_mix_test", {})
        certificate = {
            "alpha": results["alpha"], "delta": results["delta"], "setting": family.get("chosen"),
            "certified": f"{family.get('certified')} of {family.get('settings')}", "p_value": family.get("p_chosen"),
            "p_issuer": family.get("cluster_p_calibration"), "fit_items": results["counts"]["fit"]["items"],
            "calibration_items": results["counts"]["calibration"]["items"], "budget_curve": results["budget_curve"],
            "test": family.get("test", {}), "test_mix": {k: v / max(1, sum(mix.values())) for k, v in mix.items()},
        }
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
                "stored": stored, "examples": len(self.examples)}

    def item_for(self, example_id: str, answer: str | None) -> tuple[Example, Item, bool]:
        if example_id not in self.examples:
            raise UnknownExample(example_id)
        e = self.examples[example_id]
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
            trained = repair_view(item, det, rep, "laptop", f"trained repairer v1 candidate, computed earlier on this laptop's GPU in {c['seconds']:.1f} s")

        rule = repair_view(item, det, final.repair, "live", "rule repairer v0, live") if final.repair else None
        if rule is None and final.action != "send":
            # the policy abstained, so the pipeline did not repair; show what the rules would write, for comparison
            from faithguard.repair import repair

            rule = repair_view(item, det, repair(item, det), "live", "rule repairer v0, live (for comparison: the policy withheld the answer)")
            rule["not_released"] = True

        return jsonable({
            "id": e.item.id, "group": e.group, "title": e.title, "caption": e.caption, "expect": e.expect, "edited": edited,
            "question": e.item.question.model_dump(mode="json"), "answer": item.answer.text, "original_answer": e.item.answer.text,
            "generator": e.item.answer.generator, "evidence": evidence_view(item, det),
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
        return jsonable(repair_view(item, det, rep, "live", f"trained repairer v1 candidate, live on this laptop's GPU in {seconds:.1f} s"))
