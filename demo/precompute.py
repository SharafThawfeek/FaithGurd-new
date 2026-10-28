"""Pre-check every demo example and store the trained models' outputs for it (data/demo/, gitignored).

    .venv\\Scripts\\python demo\\precompute.py                 # Channel A and the trained repairer, where they load
    .venv\\Scripts\\python demo\\precompute.py --check-only    # the pre-check alone (CPU, seconds)

For each example it runs the live pipeline and checks the action is the one the example is meant to
show, and that a sent or repaired answer is right by the development gold (pilot gold store, or the
fictional items' own gold). Gold is read here, offline, never by the demo app itself; only each pilot
answer's reference text is stored for the Output step. Channel A's token probabilities and the trained
repairer's output on the fictional items go to data/demo/cache.json, so the demo can show them even
when the models are not loaded. The report goes to data/demo/precheck.md.
"""

from __future__ import annotations

import argparse
import gc
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path[:0] = [str(HERE), str(ROOT / "src")]

from cases import DEMO_DATA, Demo  # noqa: E402

from faithguard.detect import detect  # noqa: E402
from faithguard.evaluate.score import score_text  # noqa: E402
from faithguard.gold import GoldQuestion, GoldStore  # noqa: E402


def golds(demo: Demo) -> dict[str, GoldQuestion]:
    from faithguard.demo import bank_items

    out = {item.id: g for item, g, _ in bank_items()}
    spec = json.loads((DEMO_DATA / "examples.json").read_text(encoding="utf-8")) if (DEMO_DATA / "examples.json").exists() else {}
    if spec.get("gold") and (ROOT / spec["gold"]).exists():
        store = GoldStore.load(ROOT / spec["gold"])
        for e in demo.examples.values():
            if e.group == "pilot" and e.item.question.id in store.questions:
                out[e.item.id] = store.questions[e.item.question.id]
    return out


def precheck(demo: Demo, gold: dict[str, GoldQuestion]) -> tuple[list[str], int]:
    lines = ["# Demo pre-check", "", f"Policy: {demo.policy.name if demo.policy else 'threshold v0 (no policy.pkl)'}.", "",
             "| Example | Expected | Action | Output by the gold | Rule repairer | Trained repairer | Channel A | OK |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    problems = 0
    for e in demo.examples.values():
        case = demo.case(e.item.id)
        action = case["output"]["action"]
        g = gold.get(e.item.id)
        text = case["output"]["text"]
        state = score_text(text, g) if (g is not None and text) else "abstained" if action == "abstain" else "no gold"
        if g is not None and e.group == "fictional" and e.expect == "abstain":
            state = "abstained" if action == "abstain" else state
        ok = action == e.expect and state in ("supported_useful", "abstained")
        if e.group == "pilot" and action == "send":
            ok = action == e.expect  # a sent original is judged by its label, which the pilot chose it for
        rule = case["correct"]["rule"]
        trained = case["correct"]["trained"]
        a = case["catch"]["channel_a"]
        if a.get("source") not in ("live", "laptop") or trained is None:
            ok = False  # each member's trained model must have an output to show for every example
        problems += not ok
        flagged = ", ".join(f"{s['text'].strip()} {s['score']:.2f}" for s in a.get("spans", [])) or "-"
        trained_state = trained["status"] if trained else "-"
        if trained and trained["status"] == "repaired":
            trained_state += f", gate {'passed' if trained.get('check', {}).get('passed') else 'FAILED here'}"
            trained_state += f", {score_text(trained['text'], g)}" if g is not None else ""
        lines.append(f"| {e.item.id} | {e.expect} | {action} | {state} | {rule['status'] if rule else '-'} | {trained_state} | "
                     f"{(a.get('source') or 'none')}: {flagged} | {'yes' if ok else 'NO'} |")
    lines += ["", "## One-click edits in the try-it box", "", "| Example | Edit | Expected | Action | Output by the gold | OK |", "| --- | --- | --- | --- | --- | --- |"]
    for e in demo.examples.values():
        g = gold.get(e.item.id)
        for label, answer, expect in e.edits:
            case = demo.case(e.item.id, answer)
            action, text = case["output"]["action"], case["output"]["text"]
            state = score_text(text, g) if (g is not None and text) else "abstained" if action == "abstain" else "no gold"
            ok = action == expect and state in ("supported_useful", "abstained")
            problems += not ok
            lines.append(f"| {e.item.id} | {label} | {expect} | {action} | {state} | {'yes' if ok else 'NO'} |")
    return lines, problems


def run_channel_a(demo: Demo, cache: dict, device: str | None) -> None:
    import torch

    from faithguard.detect.channel_a import ChannelA

    folder = ROOT / "data" / "demo-models" / "channel-a" / "model"
    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    model = ChannelA(folder, device=device)
    for e in demo.examples.values():
        det = detect(e.item)
        started = time.perf_counter()
        tokens = model.token_probs(e.item, det)
        cache.setdefault(e.item.id, {})["channel_a"] = {
            "tokens": [list(t) for t in tokens], "device": "GPU" if device == "cuda" else "CPU", "seconds": time.perf_counter() - started}
        print(f"Channel A  {e.item.id:28} {time.perf_counter() - started:5.2f} s")
    del model
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def run_repairer(demo: Demo, cache: dict, groups: set[str]) -> None:
    import torch

    from faithguard.repair.model import ModelRepairer
    from faithguard.train.generation import Generator
    from models import BASE_MODEL

    adapter = ROOT / "data" / "demo-models" / "repair-v1" / "adapter"
    repairer = ModelRepairer(Generator(BASE_MODEL, "fp16", adapter=str(adapter)), name=f"{BASE_MODEL} + repair-v1 adapter (this laptop)")
    for e in demo.examples.values():
        if e.group not in groups:
            continue
        det = detect(e.item)
        started = time.perf_counter()
        out = repairer(e.item, det)
        seconds = time.perf_counter() - started
        cache.setdefault(e.item.id, {})["trained_repair"] = {"output": out.model_dump(mode="json"), "seconds": seconds}
        print(f"repairer   {e.item.id:28} {seconds:5.1f} s  {out.status}  {out.program.model_dump_json() if out.program else ''}")
    del repairer
    gc.collect()
    torch.cuda.empty_cache()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--no-repairer", action="store_true")
    parser.add_argument("--repair-groups", default="fictional", help="which examples the trained repairer runs on here (pilot ones have Kaggle outputs)")
    parser.add_argument("--channel-a-device", choices=["cuda", "cpu"])
    args = parser.parse_args(argv)

    DEMO_DATA.mkdir(parents=True, exist_ok=True)
    cache_path = DEMO_DATA / "cache.json"
    demo = Demo()
    cache = demo.cache
    gold = golds(demo)
    for e in demo.examples.values():
        if e.group == "pilot" and e.item.id in gold:
            cache.setdefault(e.item.id, {})["reference"] = gold[e.item.id].answer_text
    if not args.check_only:
        run_channel_a(demo, cache, args.channel_a_device)
        if not args.no_repairer:
            run_repairer(demo, cache, set(args.repair_groups.split(",")))
    cache_path.write_text(json.dumps(cache), encoding="utf-8")
    demo.cache = cache
    lines, problems = precheck(demo, gold)
    lines += ["", f"{len(demo.examples)} examples; {problems} not as expected."]
    (DEMO_DATA / "precheck.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\n-> {DEMO_DATA / 'precheck.md'}, {cache_path}")


if __name__ == "__main__":
    main()
