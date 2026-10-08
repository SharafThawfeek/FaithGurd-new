"""Running llama.cpp's server for the generators (Linux with CUDA on Kaggle or Colab; any OS with --server-binary).

The release is pinned (LLAMA_TAG). The prebuilt Linux CUDA binary is tried with the
system's CUDA libraries, then with llama.cpp's own CUDA runtime, and otherwise
llama.cpp is built from source once. On Kaggle's two T4s, run one server per GPU.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tarfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from faithguard.generation.models import LLAMA_TAG, MODELS

RELEASE_URL = f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_TAG}"
PREBUILT = f"llama-{LLAMA_TAG}-bin-ubuntu-cuda-12.8-x64.tar.gz"
CUDART = f"cudart-llama-{LLAMA_TAG}-bin-ubuntu-cuda-12.8-x64.tar.gz"


def _download(url: str, dest: Path) -> None:
    with urllib.request.urlopen(url) as response, open(dest, "wb") as out:
        shutil.copyfileobj(response, out)


def _find_server(root: Path) -> Path | None:
    for name in ("llama-server", "llama-server.exe"):
        for path in root.rglob(name):
            if path.is_file():
                return path
    return None


def _env(server: Path) -> dict:
    env = os.environ.copy()
    lib_dirs = {str(p.parent) for p in server.parent.parent.rglob("*.so*")} | {str(server.parent)}
    env["LD_LIBRARY_PATH"] = ":".join(sorted(lib_dirs) + [env.get("LD_LIBRARY_PATH", "")])
    return env


def _sees_gpu(server: Path) -> bool:
    proc = subprocess.run([str(server), "--list-devices"], capture_output=True, text=True, env=_env(server))
    return proc.returncode == 0 and "CUDA0" in proc.stdout + proc.stderr


def _compute_capability() -> str:
    out = subprocess.run(["nvidia-smi", "--query-gpu=compute_cap", "--format=csv,noheader"], capture_output=True, text=True)
    first = out.stdout.strip().splitlines()[0] if out.stdout.strip() else "7.5"
    return first.replace(".", "")


def prepare(workdir: str | Path = "llama_work") -> Path:
    """A llama-server binary that can see the GPU."""
    workdir = Path(workdir)
    folder = workdir / f"llama-{LLAMA_TAG}-prebuilt"
    folder.mkdir(parents=True, exist_ok=True)
    try:
        for name in (PREBUILT, CUDART):
            archive = folder / name
            if not archive.exists():
                _download(f"{RELEASE_URL}/{name}", archive)
            with tarfile.open(archive) as tar:
                tar.extractall(folder)
            server = _find_server(folder)
            if server is not None:
                server.chmod(0o755)
                if _sees_gpu(server):
                    return server
    except (urllib.error.URLError, tarfile.TarError, OSError) as err:
        print(f"prebuilt llama.cpp unusable: {err}")
    src = workdir / f"llama.cpp-{LLAMA_TAG}"
    if not src.exists():
        subprocess.check_call(["git", "clone", "--depth", "1", "--branch", LLAMA_TAG, "https://github.com/ggml-org/llama.cpp", str(src)])
    subprocess.check_call(["cmake", "-S", str(src), "-B", str(src / "build"), "-DGGML_CUDA=ON", "-DLLAMA_CURL=OFF",
                           f"-DCMAKE_CUDA_ARCHITECTURES={_compute_capability()}", "-DCMAKE_BUILD_TYPE=Release"])
    subprocess.check_call(["cmake", "--build", str(src / "build"), "--config", "Release", "-j", str(os.cpu_count() or 4), "--target", "llama-server"])
    server = _find_server(src / "build")
    if server is None:
        raise RuntimeError("llama.cpp build finished but llama-server was not found")
    return server


def model_path(name: str) -> str:
    from huggingface_hub import hf_hub_download

    spec = MODELS[name]
    return hf_hub_download(spec["repo"], spec["file"])


class LlamaServer:
    def __init__(self, server: str | Path, model: str, port: int = 8080, gpu: str | None = None,
                 ctx: int = 6144, slots: int = 1, log: str | Path | None = None):
        server = Path(server)
        args = [str(server), "-m", model, "--host", "127.0.0.1", "--port", str(port), "-ngl", "all",
                "-c", str(ctx * slots), "-np", str(slots), "--jinja", "--no-webui"]
        env = _env(server)
        if gpu is not None:
            env["CUDA_VISIBLE_DEVICES"] = gpu
        self.log_path = Path(log or f"llama-server-{port}.log")
        self.log = open(self.log_path, "w", encoding="utf-8")
        self.proc = subprocess.Popen(args, stdout=self.log, stderr=subprocess.STDOUT, env=env)
        self.url = f"http://127.0.0.1:{port}"

    def wait_ready(self, timeout: int = 900) -> float:
        started = time.perf_counter()
        while time.perf_counter() - started < timeout:
            if self.proc.poll() is not None:
                self.log.flush()
                raise RuntimeError("llama-server exited: " + self.log_path.read_text(encoding="utf-8", errors="replace")[-1500:])
            try:
                with urllib.request.urlopen(f"{self.url}/health", timeout=5) as r:
                    if r.status == 200:
                        return time.perf_counter() - started
            except (urllib.error.URLError, ConnectionError, TimeoutError):
                pass
            time.sleep(2)
        raise RuntimeError("llama-server did not become ready in time")

    def stop(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self.log.close()
