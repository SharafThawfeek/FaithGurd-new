"""The two answer generators (decision D-009) and their sampling settings.

Sampling is each vendor's recommended non-thinking setting, read from the model cards
on 2026-10-08. Final generation settings are fixed and pre-registered in phase 5.
"""

MODELS = {
    "qwen": {
        "repo": "unsloth/Qwen3.5-9B-GGUF",
        "file": "Qwen3.5-9B-Q4_K_M.gguf",
        "sampling": {"temperature": 1.0, "top_p": 1.0, "top_k": 20, "presence_penalty": 2.0},
    },
    "gemma": {
        "repo": "google/gemma-4-12B-it-qat-q4_0-gguf",
        "file": "gemma-4-12b-it-qat-q4_0.gguf",
        "sampling": {"temperature": 1.0, "top_p": 0.95, "top_k": 64},
    },
}

LLAMA_TAG = "b11490"  # llama.cpp release used for every generation run (decision D-008)
