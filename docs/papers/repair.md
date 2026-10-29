# Edit Programs, Not Rewrites: Verifiable Repair of Numeric Errors in Financial Answers with Small Local Models

M.S.A Ahamed, M.L Ahamed, Sharaf

> **Draft status (2026-10-29).** The test set is locked, the pre-registration filed (D-104) and the main answers labelled (D-105). Now filled: the benchmark and label description and the gold-span setting (§5.1), and the limitations and AI assistance statement, which say that every label and check was made by Claude, not by people (D-103). Repairer v1 is frozen and the rewrite baseline fixed (D-101; §4.4, §5.2); the hypotheses' decision rules are those filed (D-102; §5.3); the repair check is a blind Claude pass with a fixed draw (D-106; §5.1), the rewrite baseline declines narrative answers with no numbers (D-111; §5.2), and information preserved is judged by a further blind Claude pass on the same sample (D-109; §5.1, §5.3). Still waiting for the main runs: every result on the main answers (repairs with gold spans, Channel A's spans and the rule checker's, the baselines and variants, the repair check and the information-preserved check). The introduction, related work and method remain drafts to revise. Results are placeholders, `[RESULT: …]`, filled in phase 7 from the pre-registered analysis ([preregistration](../preregistration.md)). Numbers marked *development* come from the controlled track or the pilot's development issuers and test no hypothesis. Citations marked `[verify]` or `[CITE: …]` must be checked against the source and entered in [related-work/repair.md](../related-work/repair.md) before submission.

## Abstract

When an answer about a financial report contains a wrong number, the usual remedies are to withhold the answer or to ask a language model to rewrite it. Rewriting can fix the number but can also change others. We instead have a small local model write an *edit program*: for each flagged claim, keep it, copy a value from a named table cell, calculate it from named cells, or decline. A deterministic executor applies the program in the answer's own number format, and a hard gate checks provenance, dependency closure, that nothing outside the flagged claims changed, and that every number in the result traces to the evidence; a program that fails gets one retry, then the answer is withheld. A 2B-parameter model, fine-tuned on a free T4 GPU from FinQA and TAT-QA programs and arithmetic slips, `[RESULT: correction and new-error rates against free rewriting with the same backbone and data, on natural errors in the benchmark's 392 test answers, labelled by Claude]`. `[RESULT: self-training on its own executor-verified programs, on held-out error types and generator]`. `[RESULT: predicted spans and KEEP training]`.

## 1. Introduction

A detector that finds a wrong number in an answer leaves two options: withhold the answer, losing whatever was right in it, or repair it. Repair by free rewriting asks a model to produce a corrected answer; it is flexible, but nothing constrains what else the model changes, and every new number it writes is a fresh chance to be wrong. In financial answers, where a single wrong figure can mislead, the errors a repair introduces matter as much as the errors it removes.

This paper restricts repair to a small, checkable action space. For each claim the detector flags, the model chooses one of four operations: KEEP the claim, COPY a value from a named table cell, CALCULATE it with arithmetic over named cells, or CANNOT_FIX with a reason. The model never writes a number itself. A deterministic executor computes every new value with exact decimal arithmetic and writes it in the claim's original printed style, and a hard gate rejects any program whose result is not traceable to the evidence. Because the program names its cells, every repaired figure can be shown to a user with its source.

The design targets free hardware: a 2B-parameter model with LoRA, trained in fp16 on one T4 GPU, run locally at 4 bits. That makes the question sharper. Can a small model, given the right action space, repair more safely than the same model rewriting freely?

Our contributions:

1. **An edit language and executor** for numeric repair: four typed operations, an arithmetic grammar over cell references that cannot express arbitrary code, and rendering in the answer's own number format.
2. **A hard gate** that checks provenance, dependency closure, the edit envelope, re-verification by the rule checker, and relevance, with one retry and abstention.
3. **A training recipe** that fits a free GPU: supervised fine-tuning on targets derived from FinQA and TAT-QA programs, with false-flag (KEEP) and evidence-removed (CANNOT_FIX) items, then rejection-sampling self-training on executor-verified programs.
4. **An evaluation of correction against harm** on natural errors in a locked benchmark, labelled by separate blind passes of an AI model (§5.1): corrections, new errors, damage to correct answers, and withheld answers, with gold and predicted spans.

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

Errors on the wrong growth base are held out of training entirely, so RQ2 can test repair on an unseen error type. Repairer v1 adds one repair-only error type, the arithmetic slip: a growth rate or share computed from the right figures but misstated by 1 to 30 units in its last printed digit. It was the commonest error in the pilot's natural answers (§6.1). Stage A trained on the 10,082 of its 10,587 examples that fit in 2,048 tokens, in 5 h 50 min. Repairer v1 is stage A's recipe with 1,133 slip examples added: 11,128 examples within 2,048 tokens, in 6.1 hours. v1, not stage A, is the frozen method that R-H1 tests (D-101); it has no self-training rounds.

**Stage B: executor-verified self-training.** Each round samples four programs per training item from the current model (temperature above zero) and keeps the first that the executor runs and the gate accepts. No gold answer is used. The model is then fine-tuned further on the kept programs, mixed with half as many stage A examples; the replay of supervised data keeps CANNOT_FIX alive, since an abstention cannot be verified without gold. We run two rounds, starting from stage A, and R-H2 compares the result with stage A. This is rejection-sampling fine-tuning, not reinforcement learning.

## 5. Experimental setup

### 5.1 Data

**Benchmark.** The locked test set of the benchmark paper `[cross-reference]`: 788 answers, from two generators (Gemma and Qwen), to 394 questions about the annual reports of 48 US and Sri Lankan issuers (12 test and 12 calibration issuers per country). The plan had 400 questions; a second-reader pass excluded 6 before filing because their wording admits a second reading, though their gold is right (D-104). The test set was locked, and the pre-registration filed, before any system ran on a main answer.

**Who labels.** Every label and check on the benchmark was made by Claude (Anthropic), not by people (D-103). The second reader of the questions, the labeller, the second labeller, the adjudicator, the repair check and the information-preserved check (below; D-106, D-109) are separate, blind passes by Claude. The second reader re-derived each gold answer from the report without the author's value; the labelling passes see neither code labels nor which generator wrote the answer. Labels follow annotation guide v2: a status (correct, incorrect, ambiguous or unhelpful), usefulness, and spans typed by slot.

**How the labels were made** (D-100, D-105). Code triage first labelled 311 answers correct and useful, with no spans, where every number and word matched the gold cells, and routed the other 477 to the labeller; a stratified random audit of 150 code labels was hidden among them. A first labelling pass was discarded unused: its tasks left out each table's units note, which the generators saw, so scale and currency errors could not be judged. In the relabel, the labeller labelled all 627 routed and audit tasks, and a second labeller the 80 pre-registered double-labelled tasks (60 routed, 20 audit). On those 80, status agreed in 95% (kappa 0.89), usefulness in 91% (kappa 0.71) and whether the answer has a wrong span in 100% (kappa 1.00). These kappas measure agreement between Claude's passes, not between people. The 15 tasks whose labels differed went to the adjudicator, whose label decides. The audit overruled 4 of the 150 code labels (95% upper bound 6.0%); the pre-registration let the code labels stand only if at most 1 was overruled, so they fell and the labeller labelled the other 161 code-labelled answers. No code label decides any answer: 773 answers are decided by the labeller and 15 by the adjudicator.

**Labels.** Of the 788 answers, 592 are labelled correct, 177 incorrect (22.5%), 16 unhelpful and 3 ambiguous; 170 of the 672 numeric answers are incorrect (25.3%). Incorrect answers are commonest on growth questions (88) and shares (25). The labelled spans are mostly wrong values (130), then unsupported text (30), scale or currency (28) and sign (17), with few entity (5), period (3), basis (2) or metric (1) spans. The rule checker, which supplies the repair gate's recheck, flags 144 of the 170 incorrect numeric answers.

**Spans and scoring.** Repairs are run on the 392 test answers with gold spans, with predicted spans (from the detection paper's Channel A, which flags a claim at probability 0.5; D-104) and with the rule checker's spans. The gold spans are the span offsets of each test answer's deciding label; 86 of the 392 have spans. Answers to narrative questions are left out of repair scoring. An original's state is its label; an answer labelled ambiguous counts as wrong (D-089). Every repaired answer is scored by code against the gold answer, read with the answer's evidence (D-100); an answer sent unchanged keeps its label's state.

**Repair check** (D-100, D-106). A blind Claude pass, not a person, checks a sample of repairs, as D-103 does for the other labelling roles; the procedure and seed were fixed before any repair output on a main answer existed. The pool is every numeric test answer a trained repairer sent with changed text (repaired, or sent with nothing to fix but text different from the original); withheld repairs and calibration answers are left out. With seed 2026 we draw 50 changed repairs from each R-H1 arm (repairer v1 and free rewriting, both on the gold spans) and 50 pooled across the other variants (every other trained repairer and span source). Each becomes a blinded task with the original's question and evidence and the repaired text as the answer, labelled with the annotation guide as an original answer is. The label's state (correct is supported and useful, unhelpful is supported and unhelpful, incorrect or ambiguous is unsupported) is set against the code state. If the two disagree on more than 10% of a group's checked repairs, every changed repair of that group is labelled. As fixed before those labels were imported (D-112), their states then replace the gold scorer's for that group's arms in the repair summaries, R-H2 and R-H3, with the scorer's results reported beside them; the policy's records keep the scorer's states, since only test repairs are labelled.

**Information preserved** (D-109). The same sample gets a second check, by a separate blind Claude pass with its own task keys. Each task shows the question, the evidence, the original answer and the repaired answer, and asks whether the repair kept every piece of the original's information that the evidence supports. The share kept is reported per group (the two R-H1 arms and the other variants) with its issuer-clustered interval. It is a metric, not a hypothesis test.

**Controlled track** *(development)*. 500 items from the tune share of the controlled track, and 207 tune-share arithmetic slips.

**Pilot** *(development)*. 120 natural answers on 8 development issuers, 23 of them wrong. Claude labelled them from tasks that left out each table's units note, as in the discarded first pass; they are development-only labels and test no hypothesis (D-105).

### 5.2 Systems

| System | Role |
| --- | --- |
| Edit programs, repairer v1 (stage A's recipe plus the arithmetic slips; D-101) | The method; R-H1 |
| Free rewriting: same backbone and settings, retrained on v1's data (stage A's items plus the slips) with its own system prompt; the reply is the corrected answer text or CANNOT_FIX; no executor and no gate. Like the edit repairer, it declines narrative answers with no numbers, which no repair analysis scores (D-111) | R-H1 (RQ1), the main baseline |
| Edit programs, stage A and stage B (two self-training rounds from stage A) | R-H2 (RQ2) |
| Rule-only COPY and CALCULATE from the rule checker's correct-value expressions, no model | What rules alone can fix |
| Zero-shot programs from the untrained 2B model, and from Qwen3.5-9B at 4 bits on llama.cpp | Is training needed at all? |
| Stage A trained without KEEP items, against stage A | R-H3 (RQ3) |
| Dependency closure on vs off | Does closure prevent half-fixed answers? |

`[Consider for reviewers: free rewriting followed by the same recheck gate, to separate the effect of the program representation from that of the gate. Not pre-registered; report as exploratory if run.]`

### 5.3 Metrics and hypotheses

- **Correction rate**: wrong originals made fully correct.
- **New-error rate**: sent answers containing a wrong number the original did not have.
- **Damage rate**: originals not labelled wrong (correct or unhelpful) made wrong.
- **Withheld when needed**, **still wrong when sent**, and abstention calibration.
- **Information preserved**: of the repair check's sample, the share of repairs that kept every piece of the original's information the evidence supports, judged by a separate blind Claude pass, not by a person (§5.1; D-103, D-109). Reported per group with its interval; it tests no hypothesis.
- Valid-program rate in the deployed 4-bit runtime, gate pass rate and latency.

| Hypothesis | Confirmed if | Rejected if |
| --- | --- | --- |
| R-H1. Programs create fewer new errors than free rewriting | With gold spans, each system at its own operating point: v1's new-error rate minus rewriting's is below 0, and v1's correction rate is no more than 5 points below rewriting's (a non-inferiority margin) | No difference; reported as a negative result. If v1 corrects more than 5 points less, R-H1 is reported as not decidable at a matched rate |
| R-H2. Self-training improves out-of-distribution repair | With the rule checker's spans, correction rate of stage B minus stage A is above 0 both on held-out basis errors and on Gemma's answers | Not above 0 on either or both, as when gains come only on seen error types |
| R-H3. KEEP training cuts harm from detector false positives | Damage rate with Channel A's spans, KEEP-trained (stage A) minus no-KEEP, is below 0 | No change |

How each is decided (D-102): "above" and "below" 0 mean that the 95% interval of the paired difference on the test split excludes zero in that direction; otherwise the hypothesis is rejected as "no difference". Intervals come from an issuer-clustered bootstrap: whole issuers resampled with replacement, 2,000 resamples, percentile intervals, seed 0. The labels mark only 2 basis spans in all 788 answers (§5.1), so R-H2's held-out basis arm has at most 2 test answers. The filed rule stands, confirmed only if both arms are above 0, and the arm's answer and issuer counts are reported with it (D-107).

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

Stage A's row was run before later changes to the gate and executor. Run again on current code (D-095), stage A corrects 65.7%, withholds 32.1%, is still wrong when sent in 3.2% and makes new errors in 0.8%; repairer v1 corrects 65.7%, withholds 32.4%, 2.9% and 0.5%; neither damages a correct answer. On the 207 tune-share slips, stage A corrects 84.5%, v1 84.1% and the rule-only repairer 59.9%. The free-rewriting row understates that baseline: it was trained with its own system prompt but evaluated with the edit-program one (D-101). Evaluated again with its own prompt, it corrects 51.8% and makes new errors in 15.1%, so the wrong prompt had cost it almost nothing. Retrained on v1's data (stage A's items plus the slips; D-110), the rewrite baseline corrects 53.0%, withholds 28.5%, is still wrong when sent in 25.9% and makes new errors in 17.0%, against v1's 65.7%, 32.4%, 2.9% and 0.5%; on the 207 slips it corrects 33.8%, with new errors in 42.0% of sent repairs, against v1's 84.1%. Neither rewrite model damages a correct answer.

On the held-out base errors, programs corrected 100%, free rewriting 7.7% and zero-shot programs 26.9%. With replies constrained to the program schema, the 9B model wrote KEEP for every flagged claim and corrected nothing: a decoding constraint that guarantees valid JSON can silently change what a model writes. With the detection paper's Channel A supplying the spans, stage A corrected 63.3% with no damage. Channel A flagged a claim in 41 of the 89 correct answers; both the KEEP-trained and the no-KEEP model returned 35 of them unchanged and withheld 6, so false flags cost coverage, not correctness.

On the pilot's 23 wrong natural answers the picture differs. Stage A corrected 34.8% with the rule checker's spans and 39.1% with Channel A's, damaging none of the 81 correct answers, against 43.5% for the rule-only repairer. The commonest natural error, 7 of the 23, was an arithmetic slip, which the controlled track did not contain; stage A kept the smallest slips (29.59% for 29.58%) as written. KEEP training cut both ways. With Channel A's spans it protected correct answers (19 of 81 withheld, against 27 without KEEP training). With the rule checker's spans it kept claims the checker still rejected. The dry runs also exposed three faults in the checks: a share's two line items failing provenance, a difference written into a percentage claim, and a calculation made of typed-in numbers. All three were fixed before freezing (§4.2, §4.3). These findings motivated repairer v1 (§4.4). With both adapters rerun on the fixed code (D-101), v1 corrected 9 of the 23 wrong answers with the rule checker's spans against stage A's 8, and both corrected 9 with Channel A's; neither made a new error or damaged an answer. With the rule checker's spans, v1 corrected two small slips stage A had left uncorrected; it lost one answer stage A corrected (its program failed the gate), and withheld 3 more correct answers with Channel A's spans (21 against 18). On this, v1 was frozen as the method.

### 6.2 Natural errors (test split)

- R-H1: `[RESULT with gold spans: new-error and correction differences, v1 minus free rewriting, with intervals and verdict]`
- R-H2: `[RESULT with the rule checker's spans: stage B minus stage A on held-out basis errors and on Gemma's answers, with each arm's answer and issuer counts]`
- R-H3: `[RESULT with Channel A's spans: damage, stage A minus no-KEEP]`
- Repair check: `[RESULT: code-label agreement per group, and whether any group was fully labelled]`
- Information preserved: `[RESULT: share of checked repairs that kept the original's supported information, per group, with intervals]`
- Rule-only, zero-shot, closure and runtime measures: `[RESULT]`

## Limitations

- **Numeric errors only.** Unsupported narrative claims lead to abstention; free-text replacement is future work.
- **Template training data.** Stage A learns from template answers with planted errors. The pilot showed natural errors differ (arithmetic slips, accounting formats), and v1 adds one natural-like error type; others may remain.
- **The gate shares the rule checker's blind spots.** Recheck uses the same checker that flags claims. A wrong repair the checker cannot see, such as a value it traces under the wrong relation, can pass; we count these among new errors, scored against gold.
- **The main baseline has no gate.** Free rewriting cannot be executed, so R-H1 compares two complete systems; the representation's own effect is separated only if the exploratory gated-rewrite run is added.
- **One small backbone** (2B) and two self-training rounds, on free GPUs; a 4B model and other backbones are future work.
- **No human labels.** The labeller, second labeller, adjudicator, second reader of the questions, repair check and information-preserved check are separate blind passes by Claude (Anthropic), not people (D-103, D-106, D-109). Information preserved is therefore Claude's judgement too, made only on the checked sample. The kappas in §5.1 measure agreement between Claude's passes, not between people. There is no human agreement figure and no external adjudicator. An error Claude makes the same way in every pass would pass every check, and the gold spans that R-H1's repairs start from are Claude's. Claude also drafted the questions and gold answers, so one model made both the gold and the labels.
- **Repairs are scored by code.** The gold scorer that scores every repair also underlies the triage's code labels. The 4 code labels the audit overruled show what the scorer and the triage rules miss: unit words copied onto per-share figures, a currency code, and a claim with no figure (D-105). A repair that makes such an error could be counted correct; the repair check (§5.1), itself a Claude pass, bounds this only on the checked sample, unless a group's disagreement passes 10% and all its changed repairs are labelled.
- **Small test set.** 392 test answers, 86 with gold spans, from 24 test issuers; intervals are issuer-clustered and wide where errors are few. 86 test answers are labelled incorrect, 44 from Gemma and 42 from Qwen; 83 of them are among the 338 numeric test answers (Gemma 44, Qwen 39). R-H2's held-out basis arm has at most 2 test answers (D-107), so its verdict rests on very few answers.

## AI assistance statement

`[Finalise before submission.]` Claude (Anthropic) wrote most of the project's code, drafted the benchmark questions and gold answers, and drafted this paper. Claude also took the roles the plan gave to people (D-103): the second reading of every main question and table, the labelling of every answer routed to a person and of the audit sample, the labelling of the code-labelled answers after the audit, the second labelling for kappa, and the adjudication, each a separate blind pass; it also takes the check of the repair sample (D-106) and, in a separate blind pass on that sample, the judgement of whether each repair preserved the original's information (D-109). No person labelled an answer, checked a gold answer or a repair, or adjudicated a disagreement. The pilot labels, used only for design decisions, are Claude's too. The authors take responsibility for all content.

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
