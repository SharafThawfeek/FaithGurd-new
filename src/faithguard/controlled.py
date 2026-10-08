"""The controlled track: injected errors on FinQA and TAT-QA, replayed at scale.

Every item gets a track split by its issuer, so a company never appears in two
splits: fit (train the outcome models), tune (order the policy settings),
calibration (certify) and test (report). Replays run in parallel and are cached
under runs/controlled/<source>-<split>/replay.jsonl.
"""

from __future__ import annotations

import hashlib
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from faithguard.gold import GoldStore
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
# Shares of issuers per track split (by a stable hash of the issuer id).
TRACK_SPLITS = (("fit", 0.5), ("tune", 0.1), ("calibration", 0.2), ("test", 0.2))


def track_split(issuer: str) -> str:
    """fit / tune / calibration / test, decided by a stable hash of the issuer, never by the item."""
    x = int(hashlib.sha256(issuer.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    edge = 0.0
    for name, share in TRACK_SPLITS:
        edge += share
        if x < edge:
            return name
    return TRACK_SPLITS[-1][0]


def build(source: str, split: str) -> tuple[list[Item], GoldStore]:
    """Items with planted errors, and their gold, for one dataset split."""
    from faithguard.data import finqa, tatqa
    from faithguard.inject import inject

    loader = tatqa if source == "tatqa" else finqa
    gold = GoldStore("unused")
    items: list[Item] = []
    for ex in loader.load(SOURCES[(source, split)]):
        pairs = inject(ex)
        if pairs:
            gold.add_question(ex.gold)
        for item, injection in pairs:
            q = item.question.model_copy(update={"split": None})
            items.append(item.model_copy(update={"question": q}))
            gold.add_injection(injection)
    return items, gold


def _replay_chunk(args):
    from faithguard.replay import replay

    items, gold = args
    return [r.model_dump(mode="json") for r in replay(items, gold)]


def replay_parallel(items: list[Item], gold: GoldStore, workers: int | None = None, chunk: int = 200):
    """Replay records for every item, computed in parallel processes."""
    from faithguard.replay import ReplayRecord

    workers = workers or max(1, (os.cpu_count() or 2) - 1)
    main_file = getattr(sys.modules.get("__main__"), "__file__", None)
    if not main_file or not Path(main_file).exists():
        workers = 1  # Windows starts workers by re-importing __main__, which needs a real file
    chunks = []
    for i in range(0, len(items), chunk):
        part = items[i : i + chunk]
        sub = GoldStore("unused")
        for it in part:
            sub.add_question(gold.questions[it.question.id])
            sub.add_injection(gold.injections[it.id])
        chunks.append((part, sub))
    if workers == 1:
        results = [_replay_chunk(c) for c in chunks]
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(_replay_chunk, chunks))
    return [ReplayRecord.model_validate(r) for rs in results for r in rs]


def load_or_build(source: str, split: str, root: str | Path = "runs/controlled", rebuild: bool = False):
    """(items, gold, replay records), cached on disk."""
    from faithguard.replay import ReplayRecord

    out = Path(root) / f"{source}-{split}"
    if not rebuild and (out / "replay.jsonl").exists() and (out / "items.jsonl").exists():
        items = list(read_jsonl(out / "items.jsonl", Item))
        gold = GoldStore.load(out / "gold")
        records = list(read_jsonl(out / "replay.jsonl", ReplayRecord))
        return items, gold, records
    items, gold = build(source, split)
    records = replay_parallel(items, gold)
    for r in records:
        r.split = track_split(r.issuer)
    gold.root = out / "gold"
    gold.save()
    write_jsonl(out / "items.jsonl", items)
    write_jsonl(out / "replay.jsonl", records)
    return items, gold, records
