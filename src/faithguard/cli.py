"""The faithguard command line.

    faithguard data download all                     fetch FinQA, TAT-QA, RAGTruth; record checksums
    faithguard controlled --source tatqa --split dev build the controlled track and replay it
    faithguard slice                                 the thin end-to-end slice: 20-40 items, rules only
    faithguard trace --items F --id ID               one item, step by step (for demonstrations)
    faithguard splits build                          rebuild the split manifest
    faithguard labelling tasks|triage|audit|import   Label Studio tasks in, gold labels out; code labels with an audit
    faithguard pilot                                 the pilot answers at a glance (counts only)
    faithguard hashes FILES --out F                  pin files by SHA-256 (answers, evidence, the locked test set)
    faithguard extraction compare                    three PDF table tools against the hand-corrected tables (20 tables)
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
    from faithguard.controlled import track_split
    from faithguard.replay import replay, summary

    items, gold = _controlled(args.source, args.split)
    out = Path(args.out or f"runs/controlled/{args.source}-{args.split}")
    gold.root = out / "gold"
    gold.save()
    write_jsonl(out / "items.jsonl", items)
    records = list(replay(items, gold))
    for r in records:  # the policy study reads these files too, and needs each record's split (D-023)
        r.split = track_split(r.issuer)
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
    result = study.run(records, alpha=args.alpha, delta=args.delta, kinds=tuple(args.models.split(",")), seed=args.seed,
                       predictions={"neural": args.neural_predictions})
    out = study.save(result, args.out)
    for f in result["families"]:
        t = f.get("test")
        shown = f"sent {t['emission_coverage']:.1%}, wrong {t['residual_risk']:.1%}, useful {t['useful_coverage']:.1%}" if t else "not certified"
        print(f"{f['family']:28s} {shown}")
    print(f"Report: {out / 'report.md'}")


def cmd_transfer(args) -> None:
    """The transfer study on the controlled track: v0 = the cached rule-repairer replays of the items v1 replayed."""
    from faithguard.controlled import load_or_build
    from faithguard.policy import transfer
    from faithguard.replay import ReplayRecord

    v1 = list(read_jsonl(args.v1, ReplayRecord))
    order = {r.item_id: i for i, r in enumerate(v1)}
    v0 = []
    for source in args.sources.split(","):
        for split in ("train", "dev", "test"):
            v0 += [r for r in load_or_build(source, split)[2] if r.item_id in order]
    v0.sort(key=lambda r: order[r.item_id])
    if len(v0) != len(v1):
        raise SystemExit(f"{len(v1) - len(v0)} of v1's items have no rule-repairer replay: check --sources")
    result = transfer.run(v0, v1, alpha=args.alpha, delta=args.delta, seed=args.seed)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
    (out / "report.md").write_text(transfer.report(result), encoding="utf-8")
    print(transfer.report(result))


def cmd_sft(args) -> None:
    from faithguard.controlled import load_or_build, repair_only, track_split
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
                if args.arithmetic:
                    extra, extra_gold = repair_only(source, split)
                    chosen = [i for i in extra if track_split(i.question.issuer) == track]
                    rows += list(sft.examples(chosen, extra_gold, mode=args.mode, false_flag_rate=args.false_flags))
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


def cmd_outcome_data(args) -> None:
    """Inputs for the neural outcome model (D-096), from the cached controlled track the policy study reads."""
    from faithguard.controlled import load_or_build
    from faithguard.data import outcome_examples

    def rows():
        for source in args.sources.split(","):
            for split in ("train", "dev", "test"):
                items, _, records = load_or_build(source, split)
                yield from outcome_examples.rows(items, records)

    counts = outcome_examples.write(args.out, rows())
    print(f"{sum(counts.values())} rows {counts} -> {args.out}")


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
    from faithguard.gold import GoldStore

    splits = set(args.splits.split(",")) if args.splits else None
    if splits and manifest is None:
        raise SystemExit("--splits needs the split manifest (--manifest)")
    questions, built = benchmark.build(paths, manifest, pilot_only=args.pilot_only, splits=splits)
    out = Path(args.out)
    write_jsonl(out / "questions.jsonl", questions)
    gold = GoldStore.load(out / "gold")  # only the gold answers are rebuilt: labels and injections already there stay
    gold.questions = built.questions
    gold.save()
    kept = sum(len(v) for v in gold.labels.values())
    print(f"{len(questions)} questions -> {out / 'questions.jsonl'}; gold -> {gold.root} ({kept} labels kept)")


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


def cmd_extraction(args) -> None:
    from faithguard.data import extraction
    from faithguard.splits import split_of

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    reports = sorted(Path(args.root).glob("*/*.yaml"))

    def split(path: Path) -> str:
        return split_of(manifest, path.parent.parent.name, path.parent.name)

    if args.action == "evidence":  # the real-world condition: the main questions with their Sri Lankan tables as the tool reads them
        from faithguard.benchmark import BenchmarkQuestion

        auto, notes = {}, []
        for path in reports:
            if split(path) in ("test", "calibration"):
                tables, n = extraction.automatic_tables(path, Path(args.raw), args.tool, args.strategy)
                auto[f"{path.parent.parent.name}:{path.parent.name}"] = tables
                notes += n
        questions = []
        for q in read_jsonl(args.questions, BenchmarkQuestion):
            if q.question.issuer in auto:
                q = q.model_copy(update={"evidence": q.evidence.model_copy(update={"tables": auto[q.question.issuer]})})
            questions.append(q)
        write_jsonl(Path(args.evidence_out) / "questions.jsonl", questions)
        record = {"tool": args.tool, "strategy": args.strategy, "questions": len(questions),
                  "questions_with_automatic_tables": sum(q.question.issuer in auto for q in questions),
                  "tables": len(notes), "scale_right": sum(n["scale_right"] for n in notes),
                  "scale_from": dict(collections.Counter(n["scale_from"] for n in notes)), "per_table": notes}
        Path(args.out).mkdir(parents=True, exist_ok=True)
        (Path(args.out) / "evidence.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        print(f"{record['questions_with_automatic_tables']} of {len(questions)} questions get automatic tables; "
              f"scale right on {record['scale_right']} of {len(notes)} tables -> {Path(args.evidence_out) / 'questions.jsonl'}")
        return
    if args.action == "compare":
        chosen = extraction.choose_reports(reports, split, args.per_split, args.seed)
        title = f"Automatic-extraction run: three tools on {2 * len(chosen)} tables"
    else:  # every test and calibration report, to see how the chosen tool does beyond the tables it was chosen on
        chosen = [p for p in reports if split(p) in ("test", "calibration")]
        title = f"Automatic extraction on all {2 * len(chosen)} test and calibration tables"
    tools = extraction.TOOLS if not args.tool else {args.tool: (args.strategy,)}
    rows = extraction.run(chosen, Path(args.raw), tools)
    summary = extraction.summarise(rows)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    record = {"reports": [p.parent.name for p in chosen], "seed": args.seed, **summary, "tables": rows}
    (out / "summary.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    (out / "report.md").write_text(extraction.report(summary, rows, title), encoding="utf-8")
    print(f"best: {summary['best']} -> {out / 'report.md'}")


def cmd_systems(args) -> None:
    from faithguard.evaluate import systems
    from faithguard.evaluate.pilot import label_of
    from faithguard.gold import GoldStore

    items = list(read_jsonl(args.items, Item))
    gold = GoldStore.load(args.gold)
    folder = Path(args.outputs)

    def rows(name: str) -> dict[str, dict]:
        path = folder / f"{name}.jsonl"
        if not path.exists():
            return {}
        return {r["item_id"]: r for r in (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())}

    states = {}
    for item in items:
        label = label_of(gold, item.id)
        if label and label.status in systems.LABEL_STATE:
            states[item.id] = systems.LABEL_STATE[label.status]
    # on the benchmark every original is judged by its label (D-100); only the pilot may fall back to the gold scorer
    locked = [i.id for i in items if i.question.split in ("test", "calibration") and i.question.question_type != "narrative"]
    if unlabelled := [i for i in locked if i not in states]:
        sys.exit(f"{len(unlabelled)} test or calibration answers have no label yet, e.g. {', '.join(unlabelled[:3])}")
    summary = systems.score(items, gold, rows("detector"), {"rule_spans": rows("repair-rule-spans"),
                                                            "channel_a_spans": rows("repair-channel-a-spans")}, states)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (out / "report.md").write_text(systems.report(summary, args.title), encoding="utf-8")
    print(systems.report(summary, args.title))


def cmd_hashes(args) -> None:
    """SHA-256, size and line count of each file, so a run's inputs and outputs can be pinned (phase 5)."""
    import datetime
    import hashlib

    files = []
    for name in args.files:
        data = Path(name).read_bytes()
        files.append({"path": Path(name).as_posix(), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data),
                      "lines": data.count(b"\n")})
    record = {"created": datetime.date.today().isoformat(), "note": args.note, "files": files}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"{len(files)} files -> {out}")


def cmd_analyse(args) -> None:
    """Phase 7: the pre-registered analyses (evaluate.analysis). --rehearse runs them on the pilot, its development
    issuers split into calibration and test by a hash, to exercise the code before the main labels exist."""
    from faithguard.controlled import load_or_build
    from faithguard.evaluate import analysis
    from faithguard.gold import GoldStore
    from faithguard.policy import outcome
    from faithguard.replay import ReplayRecord

    items = list(read_jsonl(args.items, Item))
    if args.rehearse:
        for item in items:
            item.question.split = ("calibration", "test")[analysis.hash_half(item.question.issuer)]
    elif any(item.question.split not in ("calibration", "test") for item in items):
        sys.exit("the analyses run on test and calibration items only (or pass --rehearse for the pilot)")
    gold = GoldStore.load(args.gold)
    outputs = analysis.load_outputs(args.systems)
    gold_spans = None
    if args.gold_spans and Path(args.gold_spans).exists():
        rows = [json.loads(x) for x in Path(args.gold_spans).read_text(encoding="utf-8").splitlines() if x.strip()]
        gold_spans = {r["item_id"]: [tuple(s) for s in r["spans"]] for r in rows}
    controlled = []
    for source in ("tatqa", "finqa"):
        for split in ("train", "dev", "test"):
            controlled += load_or_build(source, split)[2]
    controlled_v1 = list(read_jsonl(args.controlled_v1, ReplayRecord)) if args.controlled_v1 and Path(args.controlled_v1).exists() else None
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    neural = analysis.neural_predictions(outputs, outcome.PRECOMPUTED["neural"], out / "neural-predictions.jsonl")
    result = {"detection": analysis.detection(items, gold, outputs, args.seed),
              "repair": analysis.repair(items, gold, outputs, gold_spans, args.seed),
              "policy": analysis.policy(items, gold, outputs, controlled, controlled_v1, args.seed, neural_file=neural)}
    for key, name in (("repair_check", "repair-check-result.json"), ("information_preserved", "repair-info-result.json")):
        if (gold.root / name).exists():  # the repair check and the information-preserved pass (D-106, D-109)
            result["repair"][key] = json.loads((gold.root / name).read_text(encoding="utf-8"))
    (out / "results.json").write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
    (out / "report.md").write_text(analysis.report(result), encoding="utf-8")
    print(analysis.report(result))


def cmd_repair_check(args) -> None:
    """The repair check (pre-registration §6, D-106): draw a blind sample of changed repairs, then compare code with the labels."""
    from faithguard import labelling
    from faithguard.evaluate import analysis, repair_check
    from faithguard.gold import GoldStore

    items = list(read_jsonl(args.items, Item))
    store = GoldStore.load(args.gold)
    changes = repair_check.changed(items, analysis.load_outputs(args.systems))
    plan = store.root / "repair-check.json"
    if args.action == "draw":
        if plan.exists():
            sys.exit(f"{plan} exists: the sample is drawn once")
        if not any(arm in changes for arm in repair_check.R_H1_ARMS):
            sys.exit(f"no changed repairs on the labelled spans in {args.systems}: fetch systems_main with --gold-spans first")
        sample = repair_check.draw(changes)
        ids = sorted({rid for group in sample.values() for rid in group})
        n = labelling.write_tasks(repair_check.repair_items(items, changes, ids), Path(args.out or "labelling/repair-tasks.json"),
                                  store.root / "repair-task-mapping.json")
        info, info_map = repair_check.info_tasks(items, changes, ids)  # D-109: its own keys, so the two passes stay apart
        Path("labelling/repair-info-tasks.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
        (store.root / "repair-info-mapping.json").write_text(json.dumps(info_map, indent=1, sort_keys=True), encoding="utf-8")
        plan.write_text(json.dumps({"seed": repair_check.SEED, "per_group": repair_check.SAMPLE, "sample": sample,
                                    "changed": {arm: len(v) for arm, v in changes.items()}}, indent=1) + "\n", encoding="utf-8")
        print(f"wrote {n} blinded repair tasks ({', '.join(f'{g}: {len(v)}' for g, v in sample.items())}); "
              f"import their labels with --target repair --mapping {store.root / 'repair-task-mapping.json'}; "
              f"the information-preserved tasks are in labelling/repair-info-tasks.json")
        return
    sample = json.loads(plan.read_text(encoding="utf-8"))["sample"]
    if args.action == "info":
        if not args.results:
            sys.exit("repair-check info needs --results: the information-preserved pass, [{task_key, preserved, note}]")
        mapping = json.loads((store.root / "repair-info-mapping.json").read_text(encoding="utf-8"))
        result = repair_check.info_summary(items, json.loads(Path(args.results).read_text(encoding="utf-8")), mapping, sample)
        (store.root / "repair-info-result.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
        for group, r in result.items():
            p = r["preserved"]
            print(f"{group}: {r['checked']} of {r['planned']} judged; information preserved {p['estimate']:.1%} [{p['ci95'][0]:.1%}, {p['ci95'][1]:.1%}]")
        return
    result = repair_check.compare(items, store, changes, sample)
    (store.root / "repair-check-result.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    for group, r in result.items():
        rate = "n/a" if r["rate"] is None else f"{r['rate']:.1%}"
        print(f"{group}: {r['labelled']} of {r['planned']} checked repairs labelled, code and labels disagree on {r['disagree']} ({rate})"
              + ("; every changed repair of this group is labelled" if r["label_every_changed_repair"] else ""))
    todo = [f"{i}@{arm}" for arm, v in sorted(changes.items()) for i in sorted(v)
            if result.get(repair_check.group_of(arm), {}).get("label_every_changed_repair")
            and repair_check.repair_label(store, f"{i}@{arm}") is None]
    if todo:
        mapping = store.root / "repair-task-mapping-all.json"
        if mapping.exists():
            sys.exit(f"{mapping} exists: import those labels, then run compare again")
        n = labelling.write_tasks(repair_check.repair_items(items, changes, todo), Path(args.out or "labelling/repair-tasks-all.json"), mapping)
        print(f"wrote {n} blinded tasks for the rest; import their labels with --target repair --mapping {mapping}")


def cmd_labelling(args) -> None:
    from faithguard import labelling
    from faithguard.gold import GoldStore

    needed = {"tasks": ("items", "mapping"), "triage": ("items", "gold"), "audit": ("items", "gold"),
              "import": ("export", "mapping", "gold"), "spans": ("items", "gold")}[args.action]
    if missing := [f"--{name}" for name in needed if getattr(args, name) is None]:
        sys.exit(f"labelling {args.action} needs {', '.join(missing)}")

    def write_tasks(items: list, out: Path, mapping: Path) -> int:
        # random keys each time, so a second set of tasks would orphan any export made from the first
        if taken := [str(p) for p in (out, mapping) if p.exists()]:
            sys.exit(f"{' and '.join(taken)} already exist; move them away first")
        return labelling.write_tasks(items, out, mapping, salt=args.salt)

    if args.action == "tasks":
        items = list(read_jsonl(args.items, Item))
        n = write_tasks(items, Path(args.out or "labelling/tasks.json"), Path(args.mapping))
        print(f"wrote {n} blinded tasks; keep {args.mapping} with the gold store")
    elif args.action == "triage":
        from faithguard.evaluate import triage

        items = list(read_jsonl(args.items, Item))
        store = GoldStore.load(args.gold)
        locked = {item.question.id for item in items if item.question.split in triage.LOCKED_SPLITS}
        if locked and (args.audit not in (None, triage.AUDIT_SIZE) or args.seed not in (None, triage.AUDIT_SEED)):
            sys.exit(f"on test or calibration questions the audit is pre-registered: {triage.AUDIT_SIZE} answers, seed {triage.AUDIT_SEED}")
        if locked and not args.filed:
            sys.exit("triage scores answers: on test or calibration questions it runs only after the pre-registration "
                     "is filed; pass --filed with the filing (OSF link or tagged commit)")
        if locked and (unchecked := triage.unchecked_questions(locked, args.benchmark)):
            sys.exit(f"code labels take the gold as true; {len(unchecked)} questions have no second reader (R-23), "
                     f"e.g. {', '.join(unchecked[:5])}")
        if (store.root / "triage.json").exists():
            sys.exit(f"{store.root} is already triaged; move triage.json, triage-task-mapping.json and code-labels.jsonl away first")
        result = triage.triage(items, store, audit_size=triage.AUDIT_SIZE if args.audit is None else args.audit,
                               seed=triage.AUDIT_SEED if args.seed is None else args.seed)
        result["filed"] = args.filed
        by_id = {item.id: item for item in items}
        for_person = [by_id[i] for i in sorted(set(result["person"]) | set(result["audit"]))]
        n = write_tasks(for_person, Path(args.out or "labelling/triage-tasks.json"), store.root / "triage-task-mapping.json")
        (store.root / "triage.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
        write_jsonl(store.root / "code-labels.jsonl", [triage.code_label(by_id[i]) for i in result["code"]])
        if args.report:
            out = Path(args.report)
            out.mkdir(parents=True, exist_ok=True)
            (out / "report.md").write_text(triage.report(result, items, store), encoding="utf-8")
        print(f"wrote {n} blinded tasks for a person, the audit sample hidden among them; the routing, the key mapping "
              f"and the code labels are kept in {store.root} until `labelling audit` decides on the code labels")
    elif args.action == "audit":
        from faithguard.evaluate import triage

        items = list(read_jsonl(args.items, Item))
        store = GoldStore.load(args.gold)
        if not (store.root / "triage.json").exists():
            sys.exit(f"{store.root} has no triage.json: run `labelling triage` first")
        result = json.loads((store.root / "triage.json").read_text(encoding="utf-8"))
        by_id = {item.id: item for item in items}
        if missing := sorted((set(result["code"]) | set(result["person"])) - set(by_id)):
            sys.exit(f"--items lacks {len(missing)} of the triaged answers, e.g. {', '.join(missing[:3])}; pass the items triaged")
        verdict = triage.audit(result, store, items)
        (store.root / "audit.json").write_text(json.dumps(verdict, indent=1) + "\n", encoding="utf-8")
        upper = f"{verdict['upper_95']:.1%}" if verdict["upper_95"] is not None else "n/a"
        if verdict["status"] == "incomplete":
            sys.exit(f"audit incomplete: {verdict['labelled']} of {verdict['planned']} audited answers have a person's label; "
                     f"import the rest, then run it again")
        print(f"audit: {verdict['planned']} audited answers labelled by a person, {len(verdict['overruled'])} overruled "
              f"(95% upper bound {upper}); the code labels {'stand' if verdict['code_labels_stand'] else 'fall'}; "
              f"{len(verdict['to_person'])} answers still need a person")
        tasked = set()
        for mapping in sorted(store.root.glob("audit-task-mapping*.json")):
            tasked |= set(json.loads(mapping.read_text(encoding="utf-8")).values())
        if new := [i for i in verdict["to_person"] if i not in tasked]:
            n = 1 + len(list(store.root.glob("audit-task-mapping*.json")))
            mapping = store.root / f"audit-task-mapping-{n}.json"
            count = write_tasks([by_id[i] for i in new], Path(args.out or f"labelling/audit-tasks-{n}.json"), mapping)
            print(f"wrote {count} blinded tasks for them; import their labels with --mapping {mapping}")
        if args.apply:
            people = {i for i in by_id if triage.person_labels(store, i)}
            if waiting := sorted((set(result["person"]) | set(verdict["to_person"])) - people):
                sys.exit(f"{len(waiting)} answers routed to a person have no person's label yet, e.g. {', '.join(waiting[:3])}; "
                         f"the code labels are added only once every one has")
            for i in verdict["code_labels_kept"]:
                if not any(label.annotator == triage.AUTO_ANNOTATOR for label in store.labels.get(i, [])):
                    store.add_label(triage.code_label(by_id[i]))
            store.save()
            print(f"added {len(verdict['code_labels_kept'])} code labels to {store.root}")
    elif args.action == "spans":
        from faithguard.evaluate.pilot import label_of

        # R-H1's gold-span setting: the deciding label's span offsets for every labelled test answer
        store = GoldStore.load(args.gold)
        rows = [{"item_id": item.id, "spans": [[s.start, s.end] for s in label.spans]}
                for item in read_jsonl(args.items, Item) if item.question.split == "test" and (label := label_of(store, item.id))]
        out = Path(args.out or "data/benchmark-build/main/gold-spans.jsonl")
        out.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8", newline="\n")
        print(f"wrote span offsets for {len(rows)} labelled test answers ({sum(bool(r['spans']) for r in rows)} with spans)")
    else:
        export = json.loads(Path(args.export).read_text(encoding="utf-8"))
        mapping = json.loads(Path(args.mapping).read_text(encoding="utf-8"))
        store = GoldStore.load(args.gold)
        labels = labelling.labels_from_export(export, mapping, target=args.target)
        seen = {(x.item_id, x.target, x.annotator) for xs in store.labels.values() for x in xs}
        fresh = [x for x in labels if (x.item_id, x.target, x.annotator) not in seen]
        for label in fresh:
            store.add_label(label)
        store.save()
        print(f"added {len(fresh)} labels to {args.gold}" + (f" ({len(labels) - len(fresh)} already there)" if len(fresh) < len(labels) else ""))


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
    p.add_argument("--models", default="lightgbm", help="comma-separated: lightgbm, neural (D-096)")
    p.add_argument("--neural-predictions", help="the neural outcome model's probabilities, written on a GPU by "
                   "faithguard.train.outcome_model (default: runs/policy/neural/outcome-model/predictions.jsonl, as fetched)")
    p.add_argument("--alpha", type=float, default=0.10)
    p.add_argument("--delta", type=float, default=0.05)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--rebuild", action="store_true", help="rebuild the replay records instead of using the cache")
    p.add_argument("--out", default="runs/policy/controlled")
    p.set_defaults(fn=cmd_policy)

    p = sub.add_parser("transfer", help="the transfer study: the rule-repairer (v0) policy on a trained repairer's (v1) replays")
    p.add_argument("--v1", required=True, help="replay.jsonl written by faithguard.train.replays")
    p.add_argument("--sources", default="tatqa,finqa")
    p.add_argument("--alpha", type=float, default=0.10)
    p.add_argument("--delta", type=float, default=0.05)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--out", default="runs/policy/transfer")
    p.set_defaults(fn=cmd_transfer)

    p = sub.add_parser("sft", help="repairer training data from the controlled track")
    p.add_argument("--mode", choices=["program", "rewrite"], default="program")
    p.add_argument("--sources", default="tatqa,finqa")
    p.add_argument("--hold-out", default="basis", help="error types kept out of training (RQ2); empty for none")
    p.add_argument("--false-flags", type=float, default=0.3, help="share of items with one correct claim flagged by mistake")
    p.add_argument("--arithmetic", action="store_true",
                   help="add the repair-only arithmetic slips (a growth rate or share misstated from the right figures, D-088)")
    p.add_argument("--out", default="runs/sft")
    p.set_defaults(fn=cmd_sft)

    p = sub.add_parser("detector-data", help="Channel A training data (controlled track + RAGTruth)")
    p.add_argument("--sources", default="tatqa,finqa")
    p.add_argument("--ragtruth", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--ragtruth-limit", type=int, default=8000)
    p.add_argument("--xbrl", default="runs/detector/xbrl.jsonl", help="XBRL-mined examples (or the committed .gz copy), included if present")
    p.add_argument("--out", default="runs/detector")
    p.set_defaults(fn=cmd_detector_data)

    p = sub.add_parser("outcome-data", help="inputs for the neural outcome model, the policy's challenger (D-096)")
    p.add_argument("--sources", default="tatqa,finqa")
    p.add_argument("--out", default="runs/policy/neural/outcome-data.jsonl")
    p.set_defaults(fn=cmd_outcome_data)

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
    p.add_argument("--splits", default="", help="build: only issuers in these splits, e.g. test,calibration for the main run")
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

    p = sub.add_parser("pilot", help="the pilot answers at a glance: gold scorer, rule checker and labels (counts only)")
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

    p = sub.add_parser("extraction", help="the automatic-extraction run: PDF table tools against the hand-corrected tables")
    p.add_argument("action", choices=["compare", "all", "evidence"])
    p.add_argument("--questions", default="data/benchmark-build/main/questions.jsonl", help="evidence: the main questions")
    p.add_argument("--evidence-out", default="data/benchmark-build/main-auto", help="evidence: where the real-world questions go")
    p.add_argument("--root", default="data/benchmark/LK")
    p.add_argument("--raw", default="data/raw/reports")
    p.add_argument("--manifest", default="manifests/splits.json")
    p.add_argument("--per-split", type=int, default=5, help="compare: reports drawn from each of test and calibration")
    p.add_argument("--seed", type=int, default=2026)
    p.add_argument("--tool", default="", help="all: the chosen tool (default: every tool)")
    p.add_argument("--strategy", default="")
    p.add_argument("--out", default="runs/extraction")
    p.set_defaults(fn=cmd_extraction)

    p = sub.add_parser("systems", help="score the stored outputs of the GPU systems against the gold store (counts only)")
    p.add_argument("--items", default="data/benchmark-build/items.jsonl")
    p.add_argument("--gold", default="data/benchmark-build/gold")
    p.add_argument("--outputs", default="data/benchmark-build/systems-pilot", help="folder with detector.jsonl and the repair files")
    p.add_argument("--title", default="Repair on the pilot's natural answers")
    p.add_argument("--out", default="runs/pilot/systems")
    p.set_defaults(fn=cmd_systems)

    p = sub.add_parser("hashes", help="SHA-256 of files, to pin a run's inputs and outputs")
    p.add_argument("files", nargs="+")
    p.add_argument("--note", default="", help="what the files are, e.g. the run and its settings")
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_hashes)

    p = sub.add_parser("analyse", help="phase 7: the pre-registered analyses on the labelled main benchmark (D-102)")
    p.add_argument("--items", default="data/benchmark-build/main/items-locked.jsonl", help="the locked test set (D-104)")
    p.add_argument("--gold", default="data/benchmark-build/main/gold")
    p.add_argument("--systems", default="data/benchmark-build/main/systems", help="folder of the fetched GPU outputs")
    p.add_argument("--gold-spans", default="data/benchmark-build/main/gold-spans.jsonl", help="span offsets cut from the labels (R-H1)")
    p.add_argument("--controlled-v1", default="runs/policy/transfer-replays/replay.jsonl", help="repairer v1's controlled replays (P-H3)")
    p.add_argument("--rehearse", action="store_true", help="run on the pilot, its issuers split into calibration and test by a hash")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--out", default="runs/main")
    p.set_defaults(fn=cmd_analyse)

    p = sub.add_parser("repair-check", help="the repair check: a blind labelled sample of changed repairs against code (D-106), "
                                            "and the information-preserved pass on the same sample (D-109)")
    p.add_argument("action", choices=["draw", "compare", "info"])
    p.add_argument("--results", help="info: the information-preserved pass's results, [{task_key, preserved, note}]")
    p.add_argument("--items", default="data/benchmark-build/main/items-locked.jsonl")
    p.add_argument("--gold", default="data/benchmark-build/main/gold")
    p.add_argument("--systems", default="data/benchmark-build/main/systems", help="folder of the fetched GPU outputs")
    p.add_argument("--out", help="the blinded tasks (never overwritten)")
    p.set_defaults(fn=cmd_repair_check)

    p = sub.add_parser("labelling", help="blinded Label Studio tasks, code labels with a person's audit (D-100), label import")
    p.add_argument("action", choices=["tasks", "triage", "audit", "import", "spans"])
    p.add_argument("--items")
    p.add_argument("--out", help="the blinded tasks for a person (never overwritten); spans: the span-offset file")
    p.add_argument("--mapping", help="the task key -> item file, kept with the gold store (tasks, import)")
    p.add_argument("--salt", help="task-key salt; random when left out, so nobody can recompute the keys")
    p.add_argument("--export")
    p.add_argument("--gold", help="the gold store folder (triage, audit, import)")
    p.add_argument("--target", choices=["original", "repair"], default="original")
    p.add_argument("--audit", type=int, help="code labels a person also labels, hidden among the tasks (default 150)")
    p.add_argument("--seed", type=int, help="seed for drawing the audit sample (default 2026, pre-registered)")
    p.add_argument("--report", help="folder for the counts-only triage report")
    p.add_argument("--filed", help="the pre-registration's filing (OSF link or tagged commit): needed to triage test or calibration answers")
    p.add_argument("--benchmark", default="data/benchmark", help="report YAMLs, for the second-reader check")
    p.add_argument("--apply", action="store_true", help="audit: add the code labels that stand to the gold store's labels")
    p.set_defaults(fn=cmd_labelling)

    args = parser.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
