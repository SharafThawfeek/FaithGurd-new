# Related work: detection paper (M.L Ahamed)

Fill in a row only after opening the work itself. Mark preprints. The "Plan says" column repeats what the revised plan claims, so each claim can be checked against the source.

| Work | Link | Peer-reviewed or preprint | Plan says | What it actually does | How our paper differs | Opened by |
| --- | --- | --- | --- | --- | --- | --- |
| **LettuceDetect v2 taxonomy head** (new, June 2026; read first) | [taxonomy head](https://huggingface.co/KRLabsOrg/lettucedect-v2-taxonomy-head), [v2 mmBERT](https://huggingface.co/KRLabsOrg/lettucedect-v2-mmbert-base), [v2 Qwen 2B](https://huggingface.co/KRLabsOrg/lettucedect-v2-qwen-2b) | | Not in the plan. Its model card reports typed hallucination output (typed-F1 0.461 for the encoder with the head, 0.585 for the generative 2B model) | | | |
| VeriFin | | | Uses XBRL only at inference time | | | |
| LettuceDetect v1 | [large ModernBERT v1](https://huggingface.co/KRLabsOrg/lettucedect-large-modernbert-en-v1) | | Warm-start option and baseline | | | |
| HHEM-2.1-Open | | | Baseline | | | |
| Granite Guardian 4.1-8B | | | Baseline (cut-list item 2) | | | |
| RAGTruth | | | General span training data (MIT) | | | |
| LFM2.5-Encoder-350M hallucination detector (new, August 2026) | [model](https://huggingface.co/KRLabsOrg/LFM2.5-Encoder-350M-hallucination-detector) | | Not in the plan; a possible extra baseline | | | |
| Learn-then-Test | | | Picks the detector threshold | | | |

**Claims to avoid** (from the plan): the first financial hallucination detector; the first typed or span-plus-evidence detector.
