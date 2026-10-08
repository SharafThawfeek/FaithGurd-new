# Decision log

Every choice that changes scope, method, data or compute goes here, with its reason. Fallbacks count as decisions. Newest entries at the bottom. To change a decision, add a new entry that replaces it; don't edit the old one.

| ID | Logged | Decision | Why | Owner |
| --- | --- | --- | --- | --- |
| D-001 | 2026-10-08 | Use free Colab and Kaggle GPUs and laptop CPUs only | No university GPU is available; no paid compute | All |
| D-002 | 2026-10-08 | GRPO (repair) and a 27B answer generator move to future work | They might fit free GPUs but would be slow and fragile there, and no paper's minimum result needs them | All |
| D-003 | 2026-10-08 | Repair training fallback order: fp16 LoRA, then QLoRA (fp32 LoRA maths), then Qwen3 1.7B, then Qwen3 0.6B, then a prompt-only repairer | Each step is more likely to run on a free T4 | M.S.A Ahamed |
| D-004 | 2026-10-08 | Pilot questions come from development issuers, never test issuers | The pilot drives design decisions; seeing test items would break the locked-test rule | All |
| D-005 | 2026-10-08 | Work follows the eight-phase, gate-based plan in `docs/FaithGuard-Phase-Plan.md` | Phases end on exit checklists, not dates | All |
| D-006 | 2026-10-08 | Error injector owned by M.S.A Ahamed; automatic-extraction run owned by Sharaf | The revised plan gave these tasks no owner | All |
| D-007 | 2026-10-08 | Calibration data: option B, about 12 extra issuers per country for calibration, same 400 questions; fall back to option A (split the same issuers) if table correction is too slow | Keeps 12 test issuers per country and the labelling hours unchanged; see phase 2 of the phase plan | All |
| D-008 | 2026-10-08 | Phase-1 pilots pin transformers 5.19.0, peft 0.21.2, accelerate 1.15.0, bitsandbytes 0.50.2, huggingface_hub 1.33.0, datasets 5.1.0, lettucedetect 0.2.3 and llama.cpp release b11490; torch comes from the platform | Same versions on every account. Latest stable releases on the day of setup, except huggingface_hub: 2.x conflicts with the others, so pip's compatible choice is pinned | Sharaf |
| D-009 | 2026-10-08 | Generator files: `unsloth/Qwen3.5-9B-GGUF` (Q4_K_M, 5.7 GB) and Google's `gemma-4-12B-it-qat-q4_0-gguf` (QAT Q4_0, 7.0 GB) | Both public, Apache-2.0 and about 4-bit; Gemma's own quantisation-aware file keeps more quality than a generic Q4_0 | Sharaf |
| D-010 | 2026-10-08 | Generators run with thinking turned off in the pilot | Thinking multiplies tokens and GPU hours; the final setting is fixed and pre-registered in phase 5 | Sharaf |
| D-011 | 2026-10-08 | Use the RTX 4050 laptop GPU (6 GB, supports bf16) for debugging and small tests; all timed pilots still run on a T4 | Saves Kaggle quota; the T4 is what the real runs use, so only T4 timings go into the budget | All |
| D-012 | 2026-10-08 | No supervisor sign-off steps anywhere in the plan; the open-items list and supervisor email are removed | The supervisor has already approved the project | All |
| D-013 | 2026-10-08 | Authorship order as in `docs/authorship.md`: each paper's lead author first | Settles it now, so it never blocks a paper | All |
