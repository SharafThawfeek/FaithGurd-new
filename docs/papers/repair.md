# Edit Programs, Not Rewrites: Verifiable Repair of Numeric Errors in Financial Answers with Small Local Models

M.S.A Ahamed, M.L Ahamed, Sharaf

> **Draft status (2026-10-13).** Written before the benchmark is labelled and before repairer v1 is frozen. The introduction, related work, method, setup and limitations are drafts to revise. Results are placeholders, `[RESULT: …]`, filled in phase 7 from the pre-registered analysis ([preregistration](../preregistration.md)). Numbers marked *development* come from the controlled track or the pilot's development issuers and test no hypothesis. Citations marked `[verify]` or `[CITE: …]` must be checked against the source and entered in [related-work/repair.md](../related-work/repair.md) before submission.

## Abstract

When an answer about a financial report contains a wrong number, the usual remedies are to withhold the answer or to ask a language model to rewrite it. Rewriting can fix the number but can also change others. We instead have a small local model write an *edit program*: for each flagged claim, keep it, copy a value from a named table cell, calculate it from named cells, or decline. A deterministic executor applies the program in the answer's own number format, and a hard gate checks provenance, dependency closure, that nothing outside the flagged claims changed, and that every number in the result traces to the evidence; a program that fails gets one retry, then the answer is withheld. A 2B-parameter model, fine-tuned on a free T4 GPU from FinQA and TAT-QA programs and then self-trained on its own executor-verified programs, `[RESULT: correction and new-error rates against free rewriting with the same backbone and data, on human-labelled natural errors]`. `[RESULT: self-training on held-out error types and generator]`. `[RESULT: predicted spans and KEEP training]`.

## 1. Introduction

A detector that finds a wrong number in an answer leaves two options: withhold the answer, losing whatever was right in it, or repair it. Repair by free rewriting asks a model to produce a corrected answer; it is flexible, but nothing constrains what else the model changes, and every new number it writes is a fresh chance to be wrong. In financial answers, where a single wrong figure can mislead, the errors a repair introduces matter as much as the errors it removes.

This paper restricts repair to a small, checkable action space. For each claim the detector flags, the model chooses one of four operations: KEEP the claim, COPY a value from a named table cell, CALCULATE it with arithmetic over named cells, or CANNOT_FIX with a reason. The model never writes a number itself. A deterministic executor computes every new value with exact decimal arithmetic and writes it in the claim's original printed style, and a hard gate rejects any program whose result is not traceable to the evidence. Because the program names its cells, every repaired figure can be shown to a user with its source.

The design targets free hardware: a 2B-parameter model with LoRA, trained in fp16 on one T4 GPU, run locally at 4 bits. That makes the question sharper. Can a small model, given the right action space, repair more safely than the same model rewriting freely?

Our contributions:

1. **An edit language and executor** for numeric repair: four typed operations, an arithmetic grammar over cell references that cannot express arbitrary code, and rendering in the answer's own number format.
2. **A hard gate** that checks provenance, dependency closure, the edit envelope, re-verification by the rule checker, and relevance, with one retry and abstention.
3. **A training recipe** that fits a free GPU: supervised fine-tuning on targets derived from FinQA and TAT-QA programs, with false-flag (KEEP) and evidence-removed (CANNOT_FIX) items, then rejection-sampling self-training on executor-verified programs.
4. **An evaluation of correction against harm** on human-labelled natural errors: corrections, new errors, damage to correct answers, and withheld answers, with gold and predicted spans.

Executable edits, deterministic copying and verify-repair-abstain loops are not new in themselves (§2). The contribution is their combination in a small local model and the measurement of harm against free rewriting.

## 2. Related work

**Revision by rewriting.** `[CITE: FRED — open and verify]` revises answers with free-text editing; our main baseline follows its style, with the same backbone and data as our repairer.

**Executable verification in finance.** `[CITE: VeriFin — open and verify]` and `[CITE: FinGround — open and verify]` verify financial answers with executable checks and cover parts of a verify-repair-abstain loop. We differ in having a small model write typed edit programs over flagged claims, in the gate's provenance and closure checks, and in measuring harm to correct answers.

**Programs for numerical reasoning.** Program-aided language models (Gao et al., 2023 `[verify]`) and program-of-thoughts prompting (Chen et al., 2023 `[verify]`) delegate arithmetic to an interpreter. FinQA (Chen et al., 2021) supplies gold programs over table cells, and TAT-QA (Zhu et al., 2021) gold answers over tables and text; we convert both into repair targets.

**Self-training.** STaR (Zelikman et al., 2022) and ReST (Gulcehre et al., 2023 `[verify]`) improve a model by fine-tuning on its own samples that pass a check. Our stage B is rejection-sampling fine-tuning of this kind, with the executor and gate as the check and no gold answer; we do not use reinforcement learning.

## 3. Task

The input is a question, frozen evidence (report tables, each cell with an id, and any text passages), an answer, and a set of flagged claims from a detector. The output is either a repaired answer, in which only flagged claims (and the direction words attached to them) have changed and every number is traceable to the evidence, or an abstention with a reason. Errors that are not numeric (unsupported narrative text) are out of scope and lead to abstention.

## 4. Method

### 4.1 Edit language

| Operation | Effect |
| --- | --- |
| `{"op":"KEEP","claim":"k1"}` | The claim is right as written |
| `{"op":"COPY","claim":"k2","cell":"t1r3c1"}` | Replace the number with a cell's value |
| `{"op":"CALCULATE","claim":"k1","expr":"growth(t1r3c1, t1r3c2)"}` | Replace it with a calculation on cells |
| `{"op":"CANNOT_FIX","reason":"missing_operand","claim":"k2"}` | The evidence lacks what is needed |

Expressions allow cell ids, decimal literals, `+ - * /`, brackets and the functions `growth(now, before)`, `share(part, whole)`, `ratio`, `diff`, `sum`, `avg` and `abs`. They are parsed into a tree and evaluated with Decimal arithmetic; nothing is passed to an interpreter, so arbitrary code cannot be expressed. Reason codes for CANNOT_FIX are missing_operand, ambiguous_evidence, non_numeric and conflicting_evidence.

### 4.2 Executor

The executor applies a program to the answer. New values are written in the claim's printed style: its currency prefix, scale word, decimals and negative convention (so "Rs. 12,450 million" is replaced by "Rs. 14,213 million", and a fall printed "(3)%" stays in brackets). When a calculation's sign disagrees with the claim's direction word, the word is corrected ("rose" to "fell"). The executor refuses programs that name unknown cells, edit a claim twice or produce overlapping edits; that copy a percentage into an amount claim or the reverse; that calculate from no evidence cell at all; or whose function gives the wrong kind of value for the claim (growth and share give percentages; differences, sums and averages give the kind of what they combine).

### 4.3 Hard gate

A repaired answer is released only if it passes every check:

- **Provenance.** Each copied cell, and each operand of a calculation, belongs to the metric, entity and period the claim is about (the period is not checked for growth rates and differences, which span two). A share or ratio may also use the other line item the question names, since a share's part and whole are different line items by nature.
- **Closure.** A growth rate or change that depends on a changed amount was recomputed too.
- **Envelope.** Nothing outside the edited claims and their direction words changed.
- **Recheck.** The rule checker (detection paper, Channel B) supports every claim in the repaired answer.
- **Relevance.** The repaired answer still answers the question.

If the executor or the gate rejects a program, the model gets one retry with the failure reason appended to its prompt. If the retry fails too, the answer is withheld with the evidence and a reason.

### 4.4 The repairer

**Prompt.** The model sees the evidence with a cell id and column label on every number, the question, the answer with each numeric claim marked by its id (`[k1: 7.0%]`), the list of claims it may edit, and the instructions above. The editable claims are those the detector flags, plus growth rates built on a flagged amount (dependency closure). Annual-report statements of 40–80 rows are focused on the rows the rule checker traced the claims to and the line items the claims or question name; controlled-track evidence (at most 25 rows) is shown whole.

**Model.** Qwen3.5-2B (Apache-2.0) in non-thinking mode, with LoRA (r = 16 on all linear layers). Training uses the prompt exactly as at inference, with the loss on the reply only, for one epoch at learning rate 2e-4 and up to 2,048 tokens, in fp16 on one T4 GPU.

**Stage A: supervised targets.** Items come from the controlled track: FinQA and TAT-QA questions whose gold program the error injector can express (a lookup, difference, growth rate or share), with an answer written from a template and one planted error (a wrong period, metric or entity cell, a wrong scale, a reversed sign, growth on the wrong base, or a wrong figure whose correct cell is removed from the evidence). Only issuers in the training share are used. For each item the detector decides which claims are editable, as in deployment, and the target is the gold program restricted to those claims:

- a flagged claim the gold program edits gets that COPY or CALCULATE;
- a flagged claim the gold program leaves alone gets KEEP; in 30% of items one correct claim is flagged on purpose, so the model learns to reject false flags;
- an item whose needed cell was removed gets CANNOT_FIX missing_operand;
- items whose wrong claim the detector did not flag are skipped, since the envelope would forbid fixing them.

Errors on the wrong growth base are held out of training entirely, so RQ2 can test repair on an unseen error type. Repairer v1 adds one repair-only error type, the arithmetic slip: a growth rate or share computed from the right figures but misstated by 1 to 30 units in its last printed digit. It was the commonest error in the pilot's natural answers (§6.1). `[Update when v1 is frozen: stage A trained on 10,587 examples (10,082 within 2,048 tokens) in 5 h 50 min; v1 adds 1,133 slip examples.]`

**Stage B: executor-verified self-training.** Each round samples four programs per training item from the current model (temperature above zero) and keeps the first that the executor runs and the gate accepts. No gold answer is used. The model is then fine-tuned further on the kept programs, mixed with half as many stage A examples; the replay of supervised data keeps CANNOT_FIX alive, since an abstention cannot be verified without gold. We run two rounds. This is rejection-sampling fine-tuning, not reinforcement learning.

## 5. Experimental setup

### 5.1 Data

**Benchmark.** 800 human-labelled answers (two generators × 400 questions about 48 US and Sri Lankan annual reports), described in the benchmark paper `[cross-reference]`. Repairs are run on the test split with gold spans (the human-labelled spans) and with predicted spans (from the detection paper's detector). Every repaired answer is scored by code against the gold answer; 400 sampled repairs are also checked by people, and if code and people disagree on more than about 10%, human checking is expanded.

**Controlled track** *(development)*. 500 items from the tune share of the controlled track, and 207 tune-share arithmetic slips.

**Pilot** *(development)*. 120 natural answers on 8 development issuers, 23 of them wrong, labelled by an AI annotator and awaiting human review.

### 5.2 Systems

| System | Role |
| --- | --- |
| Edit programs, stage A and stage B | The method |
| Free rewriting: same backbone, data and settings; the reply is the corrected answer text or CANNOT_FIX; no executor and no gate | RQ1, the main baseline |
| Rule-only COPY and CALCULATE from the rule checker's correct-value expressions, no model | What rules alone can fix |
| Zero-shot programs from the untrained 2B model, and from Qwen3.5-9B at 4 bits on llama.cpp | Is training needed at all? |
| Stage A trained without KEEP items | RQ3 |
| Dependency closure on vs off | Does closure prevent half-fixed answers? |

`[Consider for reviewers: free rewriting followed by the same recheck gate, to separate the effect of the program representation from that of the gate. Not pre-registered; report as exploratory if run.]`

### 5.3 Metrics and hypotheses

- **Correction rate**: wrong originals made fully correct.
- **New-error rate**: sent answers containing a wrong number the original did not have.
- **Damage rate**: correct originals made wrong.
- **Withheld when needed**, and **still wrong when sent**.
- Valid-program rate in the deployed 4-bit runtime, gate pass rate, latency, and information preserved (human-scored sample).

| Hypothesis | Confirmed if | Rejected if |
| --- | --- | --- |
| R-H1. Programs create fewer new errors than free rewriting | Lower new-error rate at a matched correction rate | No difference; reported as a negative result |
| R-H2. Self-training improves out-of-distribution repair | Gains on held-out error types and generator | Gains only on seen error types |
| R-H3. KEEP training cuts harm from detector false positives | Lower damage rate with predicted spans | No change |

`[Settle before filing: how correction rates are matched for R-H1 (pre-registration §5).]` Intervals come from an issuer-clustered bootstrap (2,000 resamples).

## 6. Results

### 6.1 Development results (not a test of the hypotheses)

On 500 tune-share template items with the rule checker's spans:

| System | Corrected | Withheld when needed | Still wrong when sent | New errors | Damage |
| --- | --- | --- | --- | --- | --- |
| Edit programs, stage A | 62.3% | 35.8% | 3.0% | 0.6% | 0% |
| Edit programs, stage B (two rounds) | 62.3% | 35.8% | 3.0% | 0.6% | 0% |
| Free rewriting | 51.8% | 28.2% | 27.8% | 15.4% | 0% |
| Rule-only | 59.6% | 38.2% | 3.5% | 0.9% | 0% |
| Zero-shot 2B | 8.0% | 90.3% | 17.5% | 0.8% | 0% |
| Zero-shot Qwen3.5-9B (free replies) | 44.5% | 52.8% | 5.7% | 1.8% | 0% |

On the held-out base errors, programs corrected 100%, free rewriting 7.7% and zero-shot programs 26.9%. With replies constrained to the program schema, the 9B model wrote KEEP for every flagged claim and corrected nothing: a decoding constraint that guarantees valid JSON can silently change what a model writes. With the detection paper's Channel A supplying the spans, stage A corrected 63.3% with no damage. Channel A flagged a claim in 41 of the 89 correct answers; both the KEEP-trained and the no-KEEP model returned 35 of them unchanged and withheld 6, so false flags cost coverage, not correctness.

On the pilot's 23 wrong natural answers the picture differs. Stage A corrected 34.8% with the rule checker's spans and 39.1% with Channel A's, damaging none of the 81 correct answers, against 43.5% for the rule-only repairer. The commonest natural error, 7 of the 23, was an arithmetic slip, which the controlled track did not contain; stage A kept the smallest slips (29.59% for 29.58%) as written. KEEP training cut both ways. With Channel A's spans it protected correct answers (19 of 81 withheld, against 27 without KEEP training). With the rule checker's spans it kept claims the checker still rejected. The dry runs also exposed three faults in the checks: a share's two line items failing provenance, a difference written into a percentage claim, and a calculation made of typed-in numbers. All three were fixed before freezing (§4.2, §4.3). These findings motivated repairer v1 (§4.4).

### 6.2 Natural errors (test split)

- R-H1: `[RESULT, with the correction-versus-new-error comparison]`
- R-H2: `[RESULT on held-out base errors and on the held-out generator]`
- R-H3: `[RESULT with predicted spans]`
- Rule-only, zero-shot, closure and runtime measures: `[RESULT]`

## Limitations

- **Numeric errors only.** Unsupported narrative claims lead to abstention; free-text replacement is future work.
- **Template training data.** Stage A learns from template answers with planted errors. The pilot showed natural errors differ (arithmetic slips, accounting formats), and v1 adds one natural-like error type; others may remain.
- **The gate shares the rule checker's blind spots.** Recheck uses the same checker that flags claims. A wrong repair the checker cannot see, such as a value it traces under the wrong relation, can pass; we count these among new errors, scored against gold.
- **The main baseline has no gate.** Free rewriting cannot be executed, so R-H1 compares two complete systems; the representation's own effect is separated only if the exploratory gated-rewrite run is added.
- **One small backbone** (2B) and two self-training rounds, on free GPUs; a 4B model and other backbones are future work.
- **Authoring and labels**: see the AI assistance statement.

## AI assistance statement

`[Finalise before submission.]` Claude (Anthropic) wrote most of the project's code, drafted the benchmark questions and gold answers, produced the pilot labels used only for design decisions, and drafted this paper. Every benchmark table and question is checked by a person before the test set is locked, the reported labels are human, and the authors take responsibility for all content.

## References

`[Check every entry against the source and fill docs/related-work/repair.md.]`

- Chen, W. et al. 2023. Program of thoughts prompting: Disentangling computation from reasoning for numerical reasoning tasks. TMLR. `[verify]`
- Chen, Z. et al. 2021. FinQA: A dataset of numerical reasoning over financial data. EMNLP.
- Gao, L. et al. 2023. PAL: Program-aided language models. ICML. `[verify]`
- Gulcehre, C. et al. 2023. Reinforced self-training (ReST) for language modeling. arXiv. `[verify]`
- Zelikman, E. et al. 2022. STaR: Bootstrapping reasoning with reasoning. NeurIPS.
- Zhu, F. et al. 2021. TAT-QA: A question answering benchmark on a hybrid of tabular and textual content in finance. ACL.
- `[CITE: FRED]`
- `[CITE: VeriFin]`
- `[CITE: FinGround]`
- `[CITE: Qwen3.5 model card or technical report]`
- `[CITE: LoRA (Hu et al.) — verify]`
