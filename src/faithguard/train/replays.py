"""Replay controlled-track items with a trained repairer (GPU), for the transfer study (policy RQ3, D-082).

    python -m faithguard.train.replays --adapter REPAIR_ADAPTER --per-split 1000 --out OUT

The detector, features and threshold decision are those of the rule-repairer replays (faithguard.replay);
only the repairer differs. Items are a fixed sample, the same number from each track split, so a laptop
can pair them with the rule repairer's replays of the same items (`faithguard transfer`). Writes
replay.jsonl, one record per item, and resumes: items already written are skipped.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Iterable, Iterator, Sequence

from faithguard.records import Item

SPLITS = ("fit", "tune", "calibration", "test")


def pick(by_split: dict[str, Sequence[Item]], per_split: int, seed: int = 7) -> list[Item]:
    """The same number of items from each track split, drawn with a fixed seed (order-independent)."""
    chosen: list[Item] = []
    for split in SPLITS:
        pool = sorted(by_split.get(split, ()), key=lambda it: it.id)
        random.Random(f"{seed}:{split}").shuffle(pool)
        chosen += pool[:per_split]
    return chosen


def sample(per_split: int, seed: int = 7, sources: Iterable[str] = ("tatqa", "finqa")):
    """(items, gold): pick() over the cached controlled track."""
    from faithguard.controlled import load_or_build
    from faithguard.gold import GoldStore

    by_split: dict[str, list[Item]] = {}
    gold = GoldStore("unused")
    stores = {}
    for source in sources:
        for split in ("train", "dev", "test"):
            items, g, records = load_or_build(source, split)
            track = {r.item_id: r.split for r in records}
            for it in items:
                by_split.setdefault(track[it.id], []).append(it)
                stores[it.id] = g
    chosen = pick(by_split, per_split, seed)
    for it in chosen:
        gold.add_question(stores[it.id].questions[it.question.id])
        gold.add_injection(stores[it.id].injections[it.id])
    return chosen, gold


def replay_items(items: Iterable[Item], gold, repairer) -> Iterator:
    """Replay records (faithguard.replay) with each record's track split filled in, as the controlled cache has it."""
    from faithguard.controlled import track_split
    from faithguard.replay import replay

    for record in replay(items, gold, repairer=repairer):
        record.split = track_split(record.issuer)
        yield record


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--adapter", required=True, help="the trained repairer's LoRA adapter")
    parser.add_argument("--model", default="Qwen/Qwen3.5-2B")
    parser.add_argument("--load", choices=["fp16", "qlora"], default="fp16")
    parser.add_argument("--per-split", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--sources", default="tatqa,finqa")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    from faithguard.train.common import one_gpu

    one_gpu()
    from faithguard.repair.model import ModelRepairer
    from faithguard.train.generation import Generator

    items, gold = sample(args.per_split, args.seed, args.sources.split(","))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "replay.jsonl"
    done = set()
    if path.exists():
        done = {json.loads(line)["item_id"] for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}
    todo = [it for it in items if it.id not in done]
    print(f"{len(items)} items ({args.per_split} per split), {len(done)} already replayed", flush=True)
    repairer = ModelRepairer(Generator(args.model, args.load, adapter=args.adapter), name=f"{args.model} + {args.adapter}")
    with open(path, "a", encoding="utf-8") as f:
        for n, record in enumerate(replay_items(todo, gold, repairer), start=1):
            f.write(record.model_dump_json() + "\n")
            f.flush()
            if n % 100 == 0:
                print(f"{n} of {len(todo)} items", flush=True)
    print(f"{len(items)} items -> {path}", flush=True)


if __name__ == "__main__":
    main()
