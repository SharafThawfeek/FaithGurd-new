"""Narration for the intro video: one MP3 per sentence with edge-tts (run in its own environment).

    python tts.py script.json OUT_DIR
"""

import asyncio
import json
import sys
from pathlib import Path

import edge_tts


async def main(script_path: str, out_dir: str) -> None:
    script = json.loads(Path(script_path).read_text(encoding="utf-8"))
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for si, scene in enumerate(script["scenes"]):
        for k, sentence in enumerate(scene["sentences"]):
            path = out / f"{si:02d}-{k:02d}.mp3"
            await edge_tts.Communicate(sentence, script["voice"], rate=script.get("rate", "+0%")).save(str(path))
            print(path.name, len(sentence.split()), "words")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2]))
