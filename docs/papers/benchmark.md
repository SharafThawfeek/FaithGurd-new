# A Sri Lankan and US Benchmark for Faithful Answers about Annual Reports

`[Working title.]` Authors: M.L Ahamed, M.S.A Ahamed, Sharaf `[order by contribution, to settle when drafted (docs/authorship.md)]`

> **Draft status (2026-10-29).** The test set is locked (394 questions, 788 answers; D-104), the main answers are labelled (D-105), and the results on the main answers are filled from the pre-registered analysis (runs/main, D-109 to D-112). Filled: the question counts and exclusions (§3.3), the label statistics in the abstract and §3.5 (status by country, generator and question type, error rate, spans by slot, kappa per field, adjudication, the audit of code labels), the statement that every label, check and adjudication was made by Claude, not people (D-103), and the note that the extracted-evidence condition was not run on the main answers in this version (§3.6). Detector, repair and policy results on the main answers are in the companion papers. Pilot figures come from development issuers and an AI annotator's provisional labels, and test nothing. Still to do: check the citations marked `[verify]` or `[CITE: …]` against the source and enter them in [related-work/benchmark.md](../related-work/benchmark.md), and the final editing before submission. Benchmark content stays out of the public repository until release.

## Abstract

We release a benchmark for checking AI answers about annual reports from two markets: Sri Lanka, for which we found no comparable public resource, and the United States. It holds 394 question groups about the latest income statements and balance sheets of 48 listed companies, 24 per country; 400 were built and 6 with two readings were left out before the test set was locked. Each question is written with its gold answer as an expression over cells of hand-corrected tables, so code can check every number an answer states. Two open models answer every question, giving 788 answers. Each answer is labelled blind to the model, and each unsupported span is marked with the part of its context that fails: entity or scope, metric, period, scale or currency, sign, basis or missing operand. The labels, and the second reading of every question and of the table rows it uses, are made by separate passes of an AI model, Claude, not by people. Questions are written to invite "right number, wrong context" errors, such as the Bank's figure given for the Group or last year's for this year. A second set of evidence, read from the reports by an automatic table extractor, is included to measure how table-reading errors change a checker's decisions; that analysis was not run on the main answers in this version. Of the 788 answers, 177 (22.5%) are incorrect, and 170 of the 672 numeric answers (25.3%). Gemma and Qwen give 54 and 53 incorrect answers of 248 each on Sri Lankan questions, and 41 and 29 of 146 each on US questions. Growth questions err most: 88 answers incorrect against 65 correct. Two blind labelling passes agree on status for 95% of 80 double-labelled answers (kappa 0.89); this is agreement between passes of one model, not between people.

## 1. Introduction

Financial question answering benchmarks mostly measure whether a model's final answer is right. Systems that check answers before a user sees them need something else: which part of an answer is unsupported, why, and whether a correct answer would be wrongly flagged. They also need evidence the checker can trust. When tables are read automatically from PDF reports, a checker cannot tell a model's error from a table-reading error.

Existing resources are almost all built on US filings. Sri Lankan listed companies publish annual reports in English with conventions that trip both people and models: Group and Company (or Bank) figures side by side, amounts in thousands of rupees, falls printed in brackets, and comparatives restated from the previous year. We found no public question-answering or faithfulness resource on Sri Lankan reports (`[record where and how the search was done — docs/related-work/benchmark.md]`).

This benchmark is built for faithfulness checking:

1. **Questions with executable gold.** Each question's gold answer is an expression over table cells (`growth(t1r3c1, t1r3c2)`), recomputed by code and compared with the author's own reading of the report, so misread figures and wrong cells surface before any answer is labelled.
2. **Hand-corrected evidence.** The income statement and balance sheet of every report, copied exactly as printed and checked so that every subtotal and total adds up. Their second reader is a pass by Claude, not a person (§3.2).
3. **Natural answers with span labels.** Two open generators answer every question once; each answer is labelled with its unsupported spans and their relation slots, its status and its usefulness. The labelling passes are made by Claude, not people (§3.5).
4. **Two markets and a held-out future.** Issuer-disjoint test, calibration and development splits in each country, and the next annual report of every test issuer held back unopened for a future refresh.
5. **A real-world condition.** The same questions and answers with evidence read by an automatic table extractor, uncorrected.

## 2. Related work

FinQA (Chen et al., 2021) and TAT-QA (Zhu et al., 2021) pose numerical questions over financial tables and text from US reports, with gold answers and, for FinQA, executable programs; they measure answer accuracy. FinanceBench (Islam et al., 2023 `[verify]`) tests open-book question answering over US filings. RAGTruth (Niu et al., 2024) labels unsupported spans in retrieval-augmented answers across general tasks, not finance. `[CITE: FinRank — verify; fresh 2024–25 US questions, a possible external test.]` Our benchmark differs in pairing natural answers with span-level, slot-typed labels and executable gold, in covering Sri Lankan reports, and in holding the evidence fixed and hand-corrected. `[Add Sri Lankan and South Asian financial NLP resources found, if any.]`

## 3. Construction

### 3.1 Issuers and splits

Candidates were drawn per country with seed 2026, stratified by sector: 33 Sri Lankan companies listed on the Colombo Stock Exchange (CSE) and 32 US companies that file with the SEC. No US candidate is one of FinQA's 137 companies, so training data that uses FinQA never shares an issuer with the test. Every ticker was checked against the exchange's or the SEC's own list before any report was collected. Three candidates were no longer listed or no longer filed, and each was replaced by a company from the same sector: Nestlé Lanka by Ceylon Grain Elevators, Synovus by F.N.B. Corporation, and Webster Financial by WSFS Financial.

| Split | Sri Lanka | US | Use |
| --- | --- | --- | --- |
| Test | 12 | 12 | Reported results; locked before any tuning |
| Calibration | 12 | 12 | Thresholds and certificates |
| Development | 4 | 4 | Pilot questions and design decisions |
| Training | 5 | 4 | Training-only |

Splits are issuer-disjoint: a company never appears in two. The manifest is fixed by its SHA-256 hash (`db0433…c771`).

### 3.2 Reports and evidence

For each issuer we take its latest annual report: on the CSE, financial years ending 31 December 2025 or 31 March 2026 (the amended report where one supersedes the original); on SEC EDGAR, the original 10-K for fiscal years ending September 2025 to February 2026. Every file is listed with its link, size and checksum.

From each report we copy two tables exactly as printed: the income statement and the statement of financial position (balance sheet), 96 tables in all. Sri Lankan tables are drafted from the PDF's own text by word position and then corrected by hand; US tables are drafted from the 10-K's HTML tables and then checked by hand the same way. A statement that runs over two pages is one table. Every table is also checked by arithmetic: each total must equal the rows above it, allowing for each figure being rounded on its own, and all 96 pass. Units are read from each page (thousands for most reports; whole rupees or millions for a few).

The tables' second reader is not a person but a separate pass by Claude (D-103), the same pass that checked the questions (§3.3). It checked the table rows the questions use against the source pages and filings. It found note-reference marks inside some row labels of one report and one row label split from its category prefix in another; the generators saw the same evidence, so the tables were left as they are (D-104).

### 3.3 Questions

Each question group has a question, a type, a gold answer as a cell expression, the value as the author read it in the report, an author and a second reader. A build step recomputes every gold answer from its cells and compares it with the author's reading. The table below counts the 400 questions built.

| | Sri Lanka | US |
| --- | --- | --- |
| Question groups (test / calibration) | 250 (123 / 127) | 150 (74 / 76) |
| Lookup | 84 | 42 |
| Growth | 47 | 30 |
| Difference | 36 | 24 |
| Share | 24 | 15 |
| Ratio | 11 | 9 |
| Comparison | 12 | 6 |
| Answer not in the evidence | 36 | – |
| Narrative | – | 24 |

Questions are written to invite wrong-context errors. Sri Lankan questions use Group against Company or Bank columns, amounts in whole rupees or millions asked in billions, falls stated as changes, and shares of total assets. US statements have no entity columns, so each US question is chosen to carry a trap from its own tables: a line item printed twice under different headings, net income with or without non-controlling interests, gross against net loans, tables in thousands asked in millions or billions, small falls, diluted against basic earnings per share, prior-year columns, and fiscal years ending in January, February or September.

The questions and gold answers were drafted with an AI assistant, Claude. The second reader is not a person but a separate pass by Claude (D-103): it re-derived each gold answer from the report and the question's wording, without the author's reading, and checked the table rows each question uses against the source pages and filings. It found no wrong gold. It confirmed 394 questions and found 6 whose wording admits a second reading, though their gold is right: two "why" questions the tables partly answer, two on a line item the report prints twice, one on net income with or without the non-controlling share, and one on a company-defined ratio the filing rounds differently. Rewording them would have needed new answers, so they were excluded before the test set was locked (D-104). The locked test set is 394 questions, 248 Sri Lankan and 146 US, and 788 answers; 392 of the answers are on test issuers and the rest on calibration issuers.

### 3.4 Answers

Every question is answered once by each of two open models: Qwen3.5-9B (Q4_K_M) and Gemma 4 12B instruction-tuned (Google's quantisation-aware Q4_0), both Apache-2.0, served by llama.cpp (release b11490) on a free T4 GPU with thinking off, a fixed seed and fixed sampling settings. The generators see the tables as a reader would, without cell ids, under one system prompt (version `1f13b3d92d8a`). This gives 800 answers, generated in 0.95 GPU hours, with no empty answers and no leaked reasoning; 788 answer the 394 locked questions (§3.3). Each answer records the model file, settings, seed, runtime release and prompt version, and the answer files are fixed by SHA-256.

### 3.5 Labels

No person labels an answer. The plan gave the labelling and checking to people, but no labellers, second readers or adjudicator were available, so Claude (Anthropic) takes those roles (D-103). The labeller, the second labeller, the adjudicator and the second reader of questions and tables (§3.2, §3.3) are separate, blind passes by Claude, not people. Every label, check and adjudication in the benchmark is AI-made.

Each labelling pass sees the question, the evidence (with each table's units note, as the generators saw it) and one answer, never which model wrote it nor any code label, and follows a written guide, version 2 ([annotation-guide.md](../annotation-guide.md)):

- **Spans**: every wrong or unsupported span, with its slot: entity or scope, metric, period, unit, scale or currency, sign, basis, missing operand, value, or unsupported text.
- **Status**: correct, incorrect, ambiguous or unhelpful.
- **Usefulness**: whether the answer gives what was asked.

The guide fixes the hard cases the pilot raised. Every printed digit of a computed figure counts, and "about" does not loosen rounding. A wrong statement stays wrong when the answer later corrects it. A wrong currency name is a scale or currency error. A figure the table itself prints is supported, even if recomputing it gives a slightly different value.

**Triage and audit.** Code first sorts the answers (D-100). It gives an answer a code label (correct, useful, no spans) only when the question asks for a number, every number matches a gold value, every year, entity, metric and unit word belongs to its figure's cells, and the answer has no hedge, explanation or other wording code cannot check. Of the 788 locked answers, 311 got a code label and 477 went to the labeller. A stratified random sample of 150 code labels (seed 2026; strata: country, generator, one figure or several) was labelled as well, hidden among the other tasks, as an audit. The rule, fixed before labelling, was that the code labels stand only if at most 1 of the 150 is overruled.

**Passes.** A first labelling pass was discarded before anything used it: the tasks' evidence had left out each table's units note, which the generators saw, so a scale or currency error could not be judged (D-105). After the fix, a first labeller labelled all 627 routed and audit tasks, and a second labeller labelled the 80 pre-registered tasks for agreement (60 routed, 20 audit), both blind. The 15 tasks whose two labels differed in status, usefulness or span text went to an adjudicator pass, whose label decides.

| Field (80 double-labelled answers) | Agreement | Cohen's kappa |
| --- | --- | --- |
| Status | 95% | 0.89 |
| Usefulness | 91% | 0.71 |
| Answer has a wrong span | 100% | 1.00 |

Both passes marked the same 26 spans, with the same slots. All but one of the 7 usefulness disagreements are on answers both passes call incorrect. Kappa here measures agreement between two passes of the same model, not between people. There is no human agreement figure and no external adjudicator.

**Audit outcome.** Of the 150 audited code labels, 4 were overruled (95% upper bound 6.0%), all on lookup questions. Two Gemma answers copy a table's thousands note onto diluted earnings per share. One Qwen answer names a currency code the report does not use. One Qwen answer says its figure is also printed on another line, which shows a different figure. With more than 1 overruled, the code labels fall, as pre-registered: the labeller labelled the other 161 code-labelled answers, and no code label decides any answer. The four show what the triage rules miss: unit words copied onto per-share figures, currency codes, and claims with no figure.

**Labels.** Of the 788 answers, 773 are decided by the labeller and 15 by the adjudicator. 592 are correct, 177 incorrect (22.5%), 16 unhelpful and 3 ambiguous. Of the 672 numeric answers (every type but narrative), 170 are incorrect (25.3%).

| Country, generator | Answers | Correct | Incorrect | Ambiguous | Unhelpful | Useful | Numeric | Numeric incorrect |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Sri Lanka, Gemma | 248 | 186 | 54 | 1 | 7 | 206 | 212 | 54 |
| Sri Lanka, Qwen | 248 | 188 | 53 | 0 | 7 | 218 | 212 | 47 |
| US, Gemma | 146 | 101 | 41 | 2 | 2 | 112 | 124 | 41 |
| US, Qwen | 146 | 117 | 29 | 0 | 0 | 131 | 124 | 28 |
| All | 788 | 592 | 177 | 3 | 16 | 667 | 672 | 170 |

| Question type | Correct | Incorrect | Ambiguous | Unhelpful |
| --- | --- | --- | --- | --- |
| Lookup | 222 | 24 | 0 | 4 |
| Growth | 65 | 88 | 0 | 1 |
| Difference | 102 | 17 | 0 | 1 |
| Share | 43 | 25 | 0 | 4 |
| Ratio | 31 | 9 | 0 | 0 |
| Comparison | 29 | 7 | 0 | 0 |
| Narrative (including answer not in the evidence) | 100 | 7 | 3 | 6 |

Errors concentrate in computed figures. Growth answers are more often incorrect (88) than correct (65), and share answers are incorrect 25 times against 43 correct; lookups are incorrect 24 times against 222 correct.

| Slot | Labelled spans |
| --- | --- |
| Value | 130 |
| Unsupported text | 30 |
| Scale or currency | 28 |
| Sign | 17 |
| Entity or scope | 5 |
| Period | 3 |
| Basis | 2 |
| Metric | 1 |

Most spans are a wrong value, then unsupported text, scale or currency, and sign. Few are the other context slots: entity or scope 5, period 3, basis 2 and metric 1. No span is marked unit or missing operand.

Labelling time is not reported. The passes were made by Claude, not people, so there is no time per item to measure.

### 3.6 Real-world condition

To measure how table-reading errors affect a checker, the Sri Lankan questions also come with evidence read by an automatic extractor, uncorrected. Three open tools were compared on 20 tables from 10 reports, with every table-finding strategy each offers and the same clean-up. Under a rule fixed before the run (most figures in the right row and column), PyMuPDF's text strategy was chosen. On all 48 Sri Lankan tables it places 94.2% of figures correctly, completes 23 tables, and detects the unit correctly for 42 of 48. US filings are HTML, whose tables read the same automatically as by hand, so US evidence is identical in both conditions. The secondary analysis pre-registered in §7 (not a hypothesis test), which compares the full pipeline's emission coverage, residual risk and useful coverage on the locked Sri Lankan answers with extracted rather than hand-corrected evidence, and how often a checker's decision changes, was not run on the main answers in this version.

| Tool (best strategy), 20 tables | Figures right | Wrong figures | Tables complete |
| --- | --- | --- | --- |
| PyMuPDF (text) | 90.0% | 220 | 8 |
| camelot (stream) | 87.4% | 32 | 11 |
| pdfplumber (text) | 82.4% | 215 | 9 |

### 3.7 Future-period set

The next annual report of each of the 24 test issuers is listed with the period it will cover and when it should appear, and is held back unopened. It supports a refresh in 2027 that no model, or author, has seen.

## 4. Pilot

Before the main questions were written, 60 pilot questions (33 Sri Lankan, 27 US) on the 8 development issuers were answered by both generators. The pilot fixed one generation bug (US tables shown with a rupee unit line) and set the annotation guide's hard cases. Labelled provisionally by an AI annotator, 23 of the 120 answers (19.2%) were incorrect: 14 from Gemma, 9 from Qwen. Errors concentrated in computed figures (growth 12 of 26 answers, share 6 of 18), against 3 of 38 lookups. The labelled spans were mostly a computed percentage off in its last digit (15), then reversed signs (6) and scale or currency errors (4). These labels were made from tasks that left out each table's units note (§3.5); they are development-only and not part of the benchmark.

## 5. Uses

The benchmark supports three companion studies, each with pre-registered hypotheses: span detection with relation slots (`[cross-reference]`), program-based repair (`[cross-reference]`), and certified accept-repair-abstain policies (`[cross-reference]`). Each answer's numbers can be scored automatically against the gold expressions, so repaired or regenerated answers can be scored without labelling each one. The repair paper still checks the code's scores: a blind Claude pass labels 50 changed repairs from each arm of its main comparison and 50 across the other variants, and every changed repair of a group is labelled if code and labels disagree on more than 10% of its checked repairs (D-106). The labels of §3.5, made by Claude, remain the reference for the original answers.

## 6. Release

`[Settle before release: licence and terms; what is released (tables, questions, gold, answers, labels, code); where.]` The reports are public filings (CSE, SEC EDGAR). The test set is locked (D-104). The questions, tables, answers and labels stay private until the companion papers are submitted, so that no system is tuned on them.

## Limitations

- **Scale.** 24 issuers per country, two statements per report and 394 question groups in the locked set; results come with issuer-clustered intervals.
- **Two generators**, both open models of 9–12B parameters at 4 bits; larger or proprietary models may err differently.
- **Fixed evidence.** Every system sees the same two statements; retrieval errors are out of scope.
- **Authoring and labels.** Questions and gold answers were drafted with an AI assistant. The second reader, the labeller, the second labeller and the adjudicator are separate, blind passes by Claude (Anthropic), not people (D-103), so every released label, check and adjudication is AI-made. Kappa measures agreement between Claude's passes, which may share the same blind spots; there is no human agreement figure and no external adjudicator. The pilot labels also came from an AI annotator and are not part of the release.
- **Triage limits.** Code labels were planned for answers the gold cells decide, but the audit overruled 4 of 150 and they fell, so no code label decides any answer. The four show what the routing rules miss: unit words copied onto per-share figures, currency codes, and claims with no figure.
- **English-language reports** only; Sri Lankan reports in Sinhala or Tamil are not covered.

## AI assistance statement

`[Finalise before submission.]` Claude (Anthropic) drafted the questions and gold answers, wrote the project's code, produced provisional pilot labels used only for design decisions, and drafted this paper. Claude also took the roles the plan gave to people (D-103): the second reader of the 400 questions and 96 tables, the labeller of every answer and of the audit sample, the second labeller for agreement, and the adjudicator, each as a separate, blind pass; it also checks a sample of repaired answers for the repair paper (D-106). No released label, check or adjudication was made by a person. The authors take responsibility for all content.

## References

`[Check every entry against the source and fill docs/related-work/benchmark.md.]`

- Chen, Z. et al. 2021. FinQA: A dataset of numerical reasoning over financial data. EMNLP.
- Islam, P. et al. 2023. FinanceBench: A new benchmark for financial question answering. arXiv. `[verify]`
- Niu, C. et al. 2024. RAGTruth: A hallucination corpus for developing trustworthy retrieval-augmented language models. ACL.
- Zhu, F. et al. 2021. TAT-QA: A question answering benchmark on a hybrid of tabular and textual content in finance. ACL.
- `[CITE: FinRank]`
- `[CITE: Qwen3.5 and Gemma 4 model cards; llama.cpp]`
- `[CITE: PyMuPDF, pdfplumber, camelot]`
