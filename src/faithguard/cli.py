"""The faithguard command line.

    faithguard data download all                     fetch FinQA, TAT-QA, RAGTruth; record checksums
    faithguard controlled --source tatqa --split dev build the controlled track and replay it
    faithguard slice                                 the thin end-to-end slice: 20-40 items, rules only
    faithguard trace --items F --id ID               one item, step by step (for demonstrations)
    faithguard splits build                          rebuild the split manifest
    faithguard labelling tasks|import ...            Label Studio tasks in, gold labels out
    faithguard pilot                                 the pilot answers at a glance (counts only)
"""

from __future__ import annotations

import argparse
import collections
import gzip
import json
import random
import shutil
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
    from faithguard.controlled import build

    return build(source, split)


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


def cmd_policy(args) -> None:
    from faithguard.controlled import load_or_build
    from faithguard.policy import study

    records = []
    for source in args.sources.split(","):
        for split in ("train", "dev", "test"):
            records += load_or_build(source, split, rebuild=args.rebuild)[2]
    result = study.run(records, alpha=args.alpha, delta=args.delta, kinds=tuple(args.models.split(",")), seed=args.seed)
    out = study.save(result, args.out)
    for f in result["families"]:
        t = f.get("test")
        shown = f"sent {t['emission_coverage']:.1%}, wrong {t['residual_risk']:.1%}, useful {t['useful_coverage']:.1%}" if t else "not certified"
        print(f"{f['family']:28s} {shown}")
    print(f"Report: {out / 'report.md'}")


def cmd_sft(args) -> None:
    from faithguard.controlled import load_or_build
    from faithguard.data import repair_examples as sft

    hold_out = tuple(x for x in args.hold_out.split(",") if x)
    out = Path(args.out)
    for track, name in (("fit", "train"), ("tune", "dev")):
        rows = []
        for source in args.sources.split(","):
            for split in ("train", "dev", "test"):
                items, gold, records = load_or_build(source, split)
                by_track = {r.item_id: r.split for r in records}
                chosen = [i for i in items if by_track.get(i.id) == track]
                # held-out error types stay out of training but remain in the dev file for evaluation
                rows += list(sft.examples(chosen, gold, mode=args.mode, hold_out=hold_out if name == "train" else (), false_flag_rate=args.false_flags))
        counts = sft.write(out / f"repair-{args.mode}-{name}.jsonl", rows)
        print(f"{name}: {sum(counts.values())} examples {dict(sorted(counts.items()))}")


def cmd_detector_data(args) -> None:
    from faithguard.controlled import load_or_build
    from faithguard.data import channel_a_examples as train_data

    out = Path(args.out)
    for track, name, rag_split in (("fit", "train", "train"), ("tune", "dev", "test")):
        rows = []
        for source in args.sources.split(","):
            for split in ("train", "dev", "test"):
                items, gold, records = load_or_build(source, split)
                by_track = {r.item_id: r.split for r in records}
                rows += list(train_data.controlled_examples([i for i in items if by_track.get(i.id) == track], gold))
        if args.ragtruth:
            rows += list(train_data.ragtruth_examples(RAW / "ragtruth", split=rag_split, limit=args.ragtruth_limit if name == "train" else 1000))
        xbrl = Path(args.xbrl)
        if not xbrl.exists() and Path(args.xbrl + ".gz").exists():
            xbrl = Path(args.xbrl + ".gz")  # the committed copy
        if xbrl.exists():
            # XBRL examples are split by company: a stable hash sends one company in ten to dev
            from faithguard.controlled import track_split

            opener = gzip.open if xbrl.suffix == ".gz" else open
            mined = [json.loads(line) for line in opener(xbrl, "rt", encoding="utf-8") if line.strip()]
            company = lambda r: r["id"].split(":")[1]
            rows += [r for r in mined if (track_split(company(r)) == "tune") == (name == "dev")]
        counts = train_data.write(out / f"{name}.jsonl", rows)
        print(f"{name}: {sum(counts.values())} examples {dict(sorted(counts.items()))}")


def cmd_xbrl_mine(args) -> None:
    """Mine wrong-context negatives from recent 10-K filings of training-only US companies."""
    from faithguard.data import edgar, xbrl_mining
    from faithguard.data import channel_a_examples as train_data

    cache = Path(args.cache)
    tickers = [t.upper() for t in args.tickers.split(",")] if args.tickers else sorted({
        ex["filename"].split("/")[0] for split in ("train", "dev", "test")
        for ex in json.loads(SOURCES[("finqa", split)].read_text(encoding="utf-8"))
    })
    manifest = json.loads(Path("manifests/splits.json").read_text(encoding="utf-8"))
    benchmark = {k[3:] for k, v in manifest["splits"].items() if k.startswith("US:") and v != "train"}
    tickers = [t for t in tickers if t not in benchmark][: args.limit]
    directory = json.loads(edgar.fetch(f"{edgar.SEC_WWW}/files/company_tickers.json", cache / "company_tickers.json"))
    by_ticker = {row["ticker"].upper(): row for row in directory.values()}
    rows, done = [], 0
    for ticker in tickers:
        entry = by_ticker.get(ticker.replace(".", "-")) or by_ticker.get(ticker)
        if entry is None:
            print(f"{ticker}: not in the SEC directory (renamed or delisted)")
            continue
        try:
            filings = [f for f in edgar.annual_filings(entry["cik_str"], cache) if f["inline_xbrl"]]
            if not filings:
                print(f"{ticker}: no inline-XBRL 10-K")
                continue
            url = edgar.instance_url(entry["cik_str"], filings[0]["accession"], cache)
            if url is None:
                print(f"{ticker}: no XBRL instance in {filings[0]['accession']}")
                continue
            xml = edgar.fetch(url, cache / f"{filings[0]['accession']}.xml")
            facts = edgar.parse_instance(xml, entity=edgar.cik10(entry["cik_str"]))
            mined = list(xbrl_mining.mine(facts, entry["title"], max_cited=args.facts_per_filing))
            rows += mined
            done += 1
            print(f"{ticker}: {len(facts)} facts, {len(mined)} examples")
        except edgar.SecAccessError as err:
            raise SystemExit(str(err))
    counts = train_data.write(Path(args.out), rows)
    # a byte-stable compressed copy is committed, so notebooks that clone the repository have the examples
    with open(args.out, "rb") as f, open(args.out + ".gz", "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz:
        shutil.copyfileobj(f, gz)
    print(f"{done} filings, {sum(counts.values())} examples {dict(sorted(counts.items()))} -> {args.out} (and .gz)")


def cmd_benchmark(args) -> None:
    from faithguard import benchmark
    from faithguard.records import write_jsonl

    use_manifest = args.manifest not in ("", "none") and Path(args.manifest).is_file()
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8")) if use_manifest else None
    if args.action == "cells":
        _, evidence = benchmark.load_report(args.report)
        print(benchmark.cell_listing(evidence))
        return
    paths = benchmark.report_paths(args.root)
    if args.action == "check":
        findings, counts = benchmark.check(paths, manifest)
        for f in findings:
            print(f"{f.level.upper():8} {f.question:16} {f.message}  [{f.file}]")
        total = sum(counts.values())
        print(f"\n{len(paths)} reports, {total} questions checked; {sum(f.level == 'error' for f in findings)} errors, {sum(f.level == 'warning' for f in findings)} warnings")
        for (country, split, qtype), n in sorted(counts.items()):
            print(f"  {country} {split:12} {qtype:12} {n}")
        if any(f.level == "error" for f in findings):
            raise SystemExit(1)
        return
    questions, gold = benchmark.build(paths, manifest, pilot_only=args.pilot_only)
    out = Path(args.out)
    write_jsonl(out / "questions.jsonl", questions)
    gold.root = out / "gold"
    gold.save()
    print(f"{len(questions)} questions -> {out / 'questions.jsonl'}; gold -> {gold.root}")


def cmd_generate(args) -> None:
    from faithguard.benchmark import BenchmarkQuestion
    from faithguard.generation.answers import generate_answers
    from faithguard.generation.models import MODELS

    questions = list(read_jsonl(args.questions, BenchmarkQuestion))
    n = generate_answers(questions, args.server, args.generator, MODELS[args.generator]["sampling"], Path(args.out), seed=args.seed, max_tokens=args.max_tokens)
    print(f"{n} new answers -> {args.out}")


def cmd_items(args) -> None:
    from faithguard.benchmark import BenchmarkQuestion
    from faithguard.records import Answer, Item

    questions = {q.question.id: q for q in read_jsonl(args.questions, BenchmarkQuestion)}
    items = []
    for path in args.answers:
        for answer in read_jsonl(path, Answer):
            q = questions[answer.question_id]
            items.append(Item(id=answer.id, question=q.question, evidence=q.evidence, answer=answer))
    write_jsonl(args.out, items)
    print(f"{len(items)} items -> {args.out}")


def cmd_pilot(args) -> None:
    from faithguard.evaluate import pilot
    from faithguard.gold import GoldStore

    summary = pilot.summarise(list(read_jsonl(args.items, Item)), GoldStore.load(args.gold))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (out / "report.md").write_text(pilot.report(summary), encoding="utf-8")
    print(f"pilot summary (counts only) -> {out / 'report.md'}")


def cmd_reports(args) -> None:
    from faithguard import splits
    from faithguard.data import reports

    manifest_path = args.manifest or f"manifests/{args.country.lower()}-reports.csv"
    if args.action == "locate":
        if args.country != "US":
            raise SystemExit("locate finds 10-Ks on SEC EDGAR, so it is for --country US only")
        split_of = json.loads(Path("manifests/splits.json").read_text(encoding="utf-8"))["splits"]
        found, problems = reports.locate_us(splits.read_issuers(args.issuers), split_of, Path(args.cache))
        reports.write_manifest(manifest_path, found)
        for problem in problems:
            print(problem)
        print(f"{len(found)} reports -> {manifest_path}")
        return
    rows = reports.read_manifest(manifest_path)
    chosen = [r for r in rows if r["split"] in set(args.splits.split(","))]
    total = sum(int(r["bytes"]) for r in chosen) / 2**20
    if args.action == "list":
        for r in chosen:
            print(f"{r['issuer']:6} {r['split']:12} {r['period_end']}  {int(r['bytes']) / 2**20:5.1f} MB  {r['report']}  {r['url']}")
        print(f"{len(chosen)} reports, {total:.0f} MB")
        return
    for issuer, outcome in reports.download(manifest_path, set(args.splits.split(",")), args.root, args.country):
        print(f"{issuer:6} {outcome}")


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

    p = sub.add_parser("policy", help="the policy study on the controlled track")
    p.add_argument("--sources", default="tatqa,finqa")
    p.add_argument("--models", default="lightgbm", help="comma-separated: lightgbm, tabicl")
    p.add_argument("--alpha", type=float, default=0.10)
    p.add_argument("--delta", type=float, default=0.05)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--rebuild", action="store_true", help="rebuild the replay records instead of using the cache")
    p.add_argument("--out", default="runs/policy/controlled")
    p.set_defaults(fn=cmd_policy)

    p = sub.add_parser("sft", help="repairer training data from the controlled track")
    p.add_argument("--mode", choices=["program", "rewrite"], default="program")
    p.add_argument("--sources", default="tatqa,finqa")
    p.add_argument("--hold-out", default="basis", help="error types kept out of training (RQ2); empty for none")
    p.add_argument("--false-flags", type=float, default=0.3, help="share of items with one correct claim flagged by mistake")
    p.add_argument("--out", default="runs/sft")
    p.set_defaults(fn=cmd_sft)

    p = sub.add_parser("detector-data", help="Channel A training data (controlled track + RAGTruth)")
    p.add_argument("--sources", default="tatqa,finqa")
    p.add_argument("--ragtruth", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--ragtruth-limit", type=int, default=8000)
    p.add_argument("--xbrl", default="runs/detector/xbrl.jsonl", help="XBRL-mined examples (or the committed .gz copy), included if present")
    p.add_argument("--out", default="runs/detector")
    p.set_defaults(fn=cmd_detector_data)

    p = sub.add_parser("xbrl-mine", help="XBRL-mined negatives from training-only US companies (needs FG_SEC_USER_AGENT)")
    p.add_argument("--tickers", help="comma-separated; default: FinQA's companies minus benchmark issuers")
    p.add_argument("--limit", type=int, default=150)
    p.add_argument("--facts-per-filing", type=int, default=25, help="cited facts sampled per filing, each with its negatives")
    p.add_argument("--cache", default="data/raw/edgar")
    p.add_argument("--out", default="runs/detector/xbrl.jsonl")
    p.set_defaults(fn=cmd_xbrl_mine)

    p = sub.add_parser("benchmark", help="team benchmark: list cells, check gold answers, build records")
    p.add_argument("action", choices=["cells", "check", "build"])
    p.add_argument("report", nargs="?", help="a report YAML (for 'cells')")
    p.add_argument("--root", default="data/benchmark")
    p.add_argument("--manifest", default="manifests/splits.json")
    p.add_argument("--pilot-only", action="store_true")
    p.add_argument("--out", default="data/benchmark-build")
    p.set_defaults(fn=cmd_benchmark)

    p = sub.add_parser("generate", help="answers from one generator served by llama.cpp (resumable)")
    p.add_argument("--questions", required=True)
    p.add_argument("--server", default="http://127.0.0.1:8080")
    p.add_argument("--generator", choices=["qwen", "gemma"], required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--seed", type=int, default=2026)
    p.add_argument("--max-tokens", type=int, default=300)
    p.set_defaults(fn=cmd_generate)

    p = sub.add_parser("items", help="join benchmark questions with generated answers into items")
    p.add_argument("--questions", required=True)
    p.add_argument("--answers", nargs="+", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_items)

    p = sub.add_parser("pilot", help="automatic first look at the pilot answers: gold scorer and rule checker (counts only)")
    p.add_argument("--items", default="data/benchmark-build/items.jsonl")
    p.add_argument("--gold", default="data/benchmark-build/gold")
    p.add_argument("--out", default="runs/pilot")
    p.set_defaults(fn=cmd_pilot)

    p = sub.add_parser("reports", help="annual reports listed in manifests/lk-reports.csv and manifests/us-reports.csv")
    p.add_argument("action", choices=["list", "download", "locate"], help="locate: find each US issuer's latest 10-K on EDGAR")
    p.add_argument("--country", choices=["LK", "US"], default="LK")
    p.add_argument("--splits", default="dev", help="comma-separated: dev (the pilot), calibration, test, train")
    p.add_argument("--manifest", default=None, help="default: manifests/<country>-reports.csv")
    p.add_argument("--root", default="data/raw/reports")
    p.add_argument("--issuers", default="manifests/issuers.csv")
    p.add_argument("--cache", default="data/raw/edgar")
    p.set_defaults(fn=cmd_reports)

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
