"""FaithGuard Stage: the presentation demo, a live 3D model of the pipeline.

    .venv\\Scripts\\python stage\\serve.py              # live pipeline; trained models live if installed
    .venv\\Scripts\\python stage\\serve.py --no-models  # live pipeline only, answers recorded at rehearsal

It serves its own pages on the demo's server and API (demo/app.py), so every check, refusal and note is the demo's.
Offline after setup. See stage/README.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "demo"))

import app  # noqa: E402

PORT = 8770


def main(argv: list[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--port" not in args:
        args = ["--port", str(PORT), *args]
    app.STATIC = HERE / "static"
    app.main(args)


if __name__ == "__main__":
    main()
