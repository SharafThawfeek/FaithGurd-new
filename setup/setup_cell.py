# Paste this as the first cell of every FaithGuard Kaggle or Colab notebook.
# Generated from requirements/gpu.txt by pilots/build_notebooks.py; do not edit by hand.
# Setup: pinned GPU packages (requirements/gpu.txt) and a look at the GPU.
import shutil, socket
try:
    socket.gethostbyname("pypi.org")
except OSError:
    raise RuntimeError("No internet in this session. Kaggle: verify your phone number (Settings), then switch Internet on in the right-hand panel.")
if not shutil.which("nvidia-smi"):
    raise RuntimeError("No GPU in this session. Kaggle: verify your phone number (Settings), then set Accelerator to GPU T4 x2. Colab: Runtime > Change runtime type > T4 GPU.")
import subprocess, sys
REQUIREMENTS = ['transformers==5.19.0', 'peft==0.21.2', 'accelerate==1.15.0', 'bitsandbytes==0.50.2', 'huggingface_hub==1.33.0', 'datasets==5.1.0', 'lettucedetect==0.2.3']
subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", *REQUIREMENTS])
# Kaggle's image ships torchao 0.10, which PEFT 0.21 rejects when it adds LoRA to fp16 weights; nothing here uses it
subprocess.call([sys.executable, "-m", "pip", "uninstall", "-y", "-q", "torchao"])
!nvidia-smi --query-gpu=name,memory.total,driver_version,compute_cap --format=csv
