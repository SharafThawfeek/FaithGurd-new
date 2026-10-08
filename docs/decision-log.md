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
| D-014 | 2026-10-08 | Parse SEC XBRL instance documents directly (standard library) instead of with Arelle | Mining needs concepts, values, periods, units, decimals and dimensions, all in the instance; Arelle would download the full US-GAAP taxonomy per filing | Sharaf |
| D-015 | 2026-10-08 | SEC requests read the contact from `FG_SEC_USER_AGENT` ("Name email@domain") | The SEC blocks undeclared tools; a GitHub no-reply address was also refused | Sharaf |
| D-016 | 2026-10-08 | Gold values for FinQA and TAT-QA are recomputed from the converted program on the cells' base-unit values; a program is kept only if it reproduces the dataset's answer | The datasets' answer strings and scale labels are sometimes inconsistent (FinQA "18.6" vs executed 19.2) | Sharaf |
| D-017 | 2026-10-08 | A number found only in text that does not name the intended metric is "unverifiable", not "supported" | Weak evidence; abstaining is safer than sending an unconfirmed number under a certified risk limit | Sharaf |
| D-018 | 2026-10-08 | Repairer v0 does not repair share or ratio claims; it returns CANNOT_FIX and the answer is withheld | The correct denominator cannot be identified from the claim alone; guessing caused harm in early runs | Sharaf |
| D-019 | 2026-10-08 | When a metric appears in several table rows with different values, the checker uses the row the answer's other numbers came from; if none, no fix is offered | Duplicate rows were the main source of wrong fixes in early runs | Sharaf |
| D-020 | 2026-10-08 | Split manifest built from 32 US and 32 Sri Lankan candidate issuers (seed 2026, sector-stratified); US candidates exclude all 137 FinQA companies; Sri Lankan tickers and US CIKs to be verified | Issuer-disjoint splits with option B (D-007); verification needs CSE and SEC access | Sharaf |
| D-021 | 2026-10-08 | Report both certification budgets: 29 answers (exact binomial, zero errors) and 32 (linearised Hoeffding-Bentkus certificate actually used) for alpha = 0.10 | The certificate the policy uses is slightly more demanding than the plan's example | Sharaf |
| D-022 | 2026-10-08 | Label Studio Community 1.23.2 runs in its own environment (`.venv-labelstudio`) | Its dependencies are heavy and would clash with the project's pinned packages | Sharaf |
