"""The faithguard command line.

    faithguard data download all                     fetch FinQA, TAT-QA, RAGTruth; record checksums
    faithguard controlled --source tatqa --split dev build the controlled track and replay it
    faithguard slice                                 the thin end-to-end slice: 20-40 items, rules only
    faithguard trace --items F --id ID               one item, step by step (for demonstrations)
    faithguard splits build                          rebuild the split manifest
    faithguard labelling tasks|import ...            Label Studio tasks in, gold labels out
"""

from __future__ import annotations

import argparse
import collections
import json
import random
import sys
from pathlib import Path

from faithguard.records import Item, read_jsonl, write_jsonl

RAW = Path("data/raw")
SOURCES = {
    ("tatqa", "train"): RAW / "tatqa/tatqa_dataset_train.json",
    ("tatqa", "dev"): RAW / "tatqa/tatqa_dataset_dev.json",
    ("tatqa", "test"): RAW / "tatqa/tatqa_dataset_test_gold.json",
    ("finqa", "train"): RAW / "finqa/train.json",
    ("finqa", "dev"): RAW / "finqa/dev.json",
    ("finqa", "test"): RAW / "finqa/test.json",
}


def _controlled(source: str, split: str):
    """(items, gold store) for the controlled track: injected errors on grounded gold examples."""
    from faithguard.data import finqa, tatqa
    from faithguard.gold import GoldStore
    from faithguard.inject import inject

    loader = tatqa if source == "tatqa" else finqa
    gold = GoldStore("unused")
    items = []
    for ex in loader.load(SOURCES[(source, split)]):
        pairs = inject(ex)
        if pairs:
            gold.add_question(ex.gold)
        for item, injection in pairs:
            items.append(item)
            gold.add_injection(injection)
    return items, gold


def cmd_data(args) -> None:
    from faithguard.data.download import SOURCES as DATASETS, download

    for name in (DATASETS if args.name == "all" else [args.name]):
        entry = download(name)
        print(name, {f: v["bytes"] for f, v in entry["files"].items()})


def cmd_controlled(args) -> None:
    from faithguard.replay import replay, summary

    items, gold = _controlled(args.source, args.split)
    out = Path(args.out or f"runs/controlled/{args.source}-{args.split}")
    gold.root = out / "gold"
    gold.save()
    write_jsonl(out / "items.jsonl", items)
    records = list(replay(items, gold))
    write_jsonl(out / "replay.jsonl", records)
    s = summary(records)
    by_error = collections.defaultdict(collections.Counter)
    for r in records:
        by_error[r.error][f"{r.decision} -> {r.final_state}"] += 1
    s["by_error"] = {e: dict(c.most_common()) for e, c in sorted(by_error.items())}
    s["items"] = len(items)
    (out / "summary.json").write_text(json.dumps(s, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: s[k] for k in ("items", "policy", "always_send", "action_accuracy")}, indent=2))


def cmd_slice(args) -> None:
    from faithguard.demo import bank_items
    from faithguard.evaluate import policy_metrics, score_text
    from faithguard.pipeline import run

    rng = random.Random(args.seed)
    chosen: list[tuple[Item, object, object]] = [(i, g, inj) for i, g, inj in bank_items()]
    for source in ("tatqa", "finqa"):
        items, gold = _controlled(source, "dev")
        by_error = collections.defaultdict(list)
        for item in items:
            by_error[gold.injections[item.id].error].append(item)
        for error in sorted(by_error):
            for item in rng.sample(by_error[error], min(args.per_error, len(by_error[error]))):
                chosen.append((item, gold.questions[item.question.id], gold.injections[item.id]))
    out = Path(args.out)
    rows, states = [], []
    for item, gold_q, injection in chosen:
        final = run(item)
        state = score_text(final.text, gold_q) if final.action != "abstain" else "abstained"
        states.append(state)
        rows.append((item, injection, final, state))
    write_jsonl(out / "items.jsonl", [r[0] for r in rows])
    write_jsonl(out / "outputs.jsonl", [r[2] for r in rows])
    metrics = policy_metrics(states)
    correct_action = sum(r[2].action == r[1].expected_action for r in rows)
    lines = [
        "# Thin end-to-end slice (rules only)",
        "",
        f"{len(rows)} items: {len(bank_items())} hand-written on a fictional Sri Lankan bank, the rest injected into FinQA and TAT-QA development examples.",
        "Every item runs the full pipeline: Channel B rule checker, threshold policy v0, rule-only repairer v0 with the hard gate.",
        "These items were made by the project's own templates, so the numbers show the pipeline works end to end; they are not results.",
        "",
        f"- Expected action taken: {correct_action} of {len(rows)}",
        f"- Answers sent (original or fixed): {metrics['emitted']} of {len(rows)}; unsupported among them: {metrics['unsafe_emitted']}",
        f"- Useful answers sent: {round(metrics['useful_coverage'] * len(rows))} of {len(rows)}",
        "",
        "| # | Source | Planted error | Expected | Action | Outcome | Answer | Output or reason |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for n, (item, injection, final, state) in enumerate(rows, start=1):
        shown = final.text if final.action != "abstain" else f"ABSTAIN: {final.reason}"
        cell = lambda s: s.replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {n} | {item.question.source} | {injection.error} | {injection.expected_action} | {final.action} | {state} | {cell(item.answer.text)} | {cell(shown)} |"
        )
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:9]))
    print(f"\nWrote {out / 'report.md'}")


def cmd_trace(args) -> None:
    from faithguard.pipeline import run

    item = next(i for i in read_jsonl(args.items, Item) if i.id == args.id)
    final = run(item)
    print(f"QUESTION  {item.question.text}\nANSWER    {item.answer.text}\n")
    print("1. DETECTION (Channel B rules)")
    for claim, check in zip(final.detector.claims, final.detector.checks):
        ctx = check.intended
        print(f"   {claim.text!r:28} {check.verdict:12} slots={check.slots or '-'}  about {ctx.entity or ''} {ctx.metric} {ctx.period}  ({check.note})")
    print(f"   risk = {final.detector.risk}\n")
    print(f"2. POLICY: {final.decision.action} ({final.decision.reason})\n")
    if final.repair:
        print("3. REPAIR PROGRAM")
        for edit in (final.repair.program.edits if final.repair.program else []):
            print(f"   {edit.model_dump_json()}")
        print(f"   gate: {final.repair.gate.model_dump() if final.repair.gate else final.repair.status} {final.repair.reason}\n")
    print(f"RESULT    {final.action.upper()}: {final.text if final.text else final.reason}")


def cmd_splits(args) -> None:
    import json as _json

    from faithguard import splits

    tickers = set()
    for split in ("train", "dev", "test"):
        for ex in _json.loads(SOURCES[("finqa", split)].read_text(encoding="utf-8")):
            tickers.add(ex["filename"].split("/")[0])
    manifest = splits.build(args.issuers, tickers, seed=args.seed)
    Path(args.out).write_text(_json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.out} (sha256 {manifest['sha256'][:16]})")


def cmd_labelling(args) -> None:
    from faithguard import labelling
    from faithguard.gold import GoldStore

    if args.action == "tasks":
        items = list(read_jsonl(args.items, Item))
        n = labelling.write_tasks(items, args.out, args.mapping, salt=args.salt)
        print(f"wrote {n} blinded tasks to {args.out}; keep {args.mapping} with the gold store")
    else:
        export = json.loads(Path(args.export).read_text(encoding="utf-8"))
        mapping = json.loads(Path(args.mapping).read_text(encoding="utf-8"))
        store = GoldStore.load(args.gold)
        labels = labelling.labels_from_export(export, mapping, target=args.target)
        for label in labels:
            store.add_label(label)
        store.save()
        print(f"added {len(labels)} labels to {args.gold}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="faithguard", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("data")
    p.add_argument("action", choices=["download"])
    p.add_argument("name", choices=["finqa", "tatqa", "ragtruth", "all"])
    p.set_defaults(fn=cmd_data)

    p = sub.add_parser("controlled")
    p.add_argument("--source", choices=["tatqa", "finqa"], default="tatqa")
    p.add_argument("--split", choices=["train", "dev", "test"], default="dev")
    p.add_argument("--out")
    p.set_defaults(fn=cmd_controlled)

    p = sub.add_parser("slice")
    p.add_argument("--per-error", type=int, default=2, help="items per error type per dataset")
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--out", default="runs/slice")
    p.set_defaults(fn=cmd_slice)

    p = sub.add_parser("trace")
    p.add_argument("--items", required=True)
    p.add_argument("--id", required=True)
    p.set_defaults(fn=cmd_trace)

    p = sub.add_parser("splits")
    p.add_argument("action", choices=["build"])
    p.add_argument("--issuers", default="manifests/issuers.csv")
    p.add_argument("--out", default="manifests/splits.json")
    p.add_argument("--seed", type=int, default=2026)
    p.set_defaults(fn=cmd_splits)

    p = sub.add_parser("labelling")
    p.add_argument("action", choices=["tasks", "import"])
    p.add_argument("--items")
    p.add_argument("--out", default="labelling/tasks.json")
    p.add_argument("--mapping", default="data/gold/task-mapping.json")
    p.add_argument("--salt", default="faithguard")
    p.add_argument("--export")
    p.add_argument("--gold", default="data/gold")
    p.add_argument("--target", choices=["original", "repair"], default="original")
    p.set_defaults(fn=cmd_labelling)

    args = parser.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
