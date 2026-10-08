# Paste this as the first cell of every FaithGuard Kaggle or Colab notebook.
# Generated from requirements/gpu.txt by pilots/build_notebooks.py; do not edit by hand.
# Setup: pinned GPU packages (requirements/gpu.txt) and a look at the GPU.
import subprocess, sys
REQUIREMENTS = ['transformers==5.19.0', 'peft==0.21.2', 'accelerate==1.15.0', 'bitsandbytes==0.50.2', 'huggingface_hub==1.33.0', 'datasets==5.1.0', 'lettucedetect==0.2.3']
subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", *REQUIREMENTS])
!nvidia-smi --query-gpu=name,memory.total,driver_version,compute_cap --format=csv
