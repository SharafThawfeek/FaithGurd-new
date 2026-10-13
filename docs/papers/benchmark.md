# A Sri Lankan and US Benchmark for Faithful Answers about Annual Reports

`[Working title.]` Authors: M.L Ahamed, M.S.A Ahamed, Sharaf `[order by contribution, to settle when drafted (docs/authorship.md)]`

> **Draft status (2026-10-13).** Written before the benchmark is labelled and before the test set is locked. Construction (§3) describes what has been built; statistics of human labels are placeholders, `[RESULT: …]`, filled after labelling. Pilot figures come from development issuers and an AI annotator's provisional labels, and test nothing. Citations marked `[verify]` or `[CITE: …]` must be checked against the source and entered in [related-work/benchmark.md](../related-work/benchmark.md) before submission. Benchmark content stays out of the public repository until release.

## Abstract

We release a benchmark for checking AI answers about annual reports from two markets: Sri Lanka, for which we found no comparable public resource, and the United States. It holds 400 question groups about the latest income statements and balance sheets of 48 listed companies, 24 per country. Each question is written with its gold answer as an expression over cells of hand-corrected tables, so code can check every number an answer states. Two open models answer every question, and annotators blind to the model mark each unsupported span with the part of its context that fails: entity or scope, metric, period, scale or currency, sign, basis or missing operand. Questions are written to invite "right number, wrong context" errors, such as the Bank's figure given for the Group or last year's for this year. A second set of evidence, read from the reports by an automatic table extractor, measures how table-reading errors change a checker's decisions. `[RESULT: answers labelled; error rate by country, generator and question type; agreement.]`

## 1. Introduction

Financial question answering benchmarks mostly measure whether a model's final answer is right. Systems that check answers before a user sees them need something else: which part of an answer is unsupported, why, and whether a correct answer would be wrongly flagged. They also need evidence the checker can trust. When tables are read automatically from PDF reports, a checker cannot tell a model's error from a table-reading error.

Existing resources are almost all built on US filings. Sri Lankan listed companies publish annual reports in English with conventions that trip both people and models: Group and Company (or Bank) figures side by side, amounts in thousands of rupees, falls printed in brackets, and comparatives restated from the previous year. We found no public question-answering or faithfulness resource on Sri Lankan reports (`[record where and how the search was done — docs/related-work/benchmark.md]`).

This benchmark is built for faithfulness checking:

1. **Questions with executable gold.** Each question's gold answer is an expression over table cells (`growth(t1r3c1, t1r3c2)`), recomputed by code and compared with the author's own reading of the report, so misread figures and wrong cells surface before anyone labels an answer.
2. **Hand-corrected evidence.** The income statement and balance sheet of every report, copied exactly as printed and checked so that every subtotal and total adds up.
3. **Natural answers with span labels.** Two open generators answer every question once; annotators mark unsupported spans with a relation slot, the answer's status and its usefulness.
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

From each report we copy two tables exactly as printed: the income statement and the statement of financial position (balance sheet), 96 tables in all. Sri Lankan tables are drafted from the PDF's own text by word position, and US tables from the 10-K's HTML tables, then corrected by hand cell by cell. A statement that runs over two pages is one table. Every table is also checked by arithmetic: each total must equal the rows above it, allowing for each figure being rounded on its own, and all 96 pass. Units are read from each page (thousands for most reports; whole rupees or millions for a few).

### 3.3 Questions

Each question group has a question, a type, a gold answer as a cell expression, the value as the author read it in the report, an author and a second reader. A build step recomputes every gold answer from its cells and compares it with the author's reading.

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

`[Before release: state that the questions and gold answers were drafted with an AI assistant and checked by a person, with the number of corrections the check made.]`

### 3.4 Answers

Every question is answered once by each of two open models: Qwen3.5-9B (Q4_K_M) and Gemma 4 12B instruction-tuned (Google's quantisation-aware Q4_0), both Apache-2.0, served by llama.cpp (release b11490) on a free T4 GPU with thinking off, a fixed seed and fixed sampling settings. The generators see the tables as a reader would, without cell ids, under one system prompt (version `1f13b3d92d8a`). This gives 800 answers, generated in 0.95 GPU hours, with no empty answers and no leaked reasoning. Each answer records the model file, settings, seed, runtime release and prompt version, and the answer files are fixed by SHA-256.

### 3.5 Labels

Annotators see the question, the evidence and one answer, never which model wrote it, and follow a written guide ([annotation-guide.md](../annotation-guide.md)):

- **Spans**: every wrong or unsupported span, with its slot: entity or scope, metric, period, unit, scale or currency, sign, basis, missing operand, value, or unsupported text.
- **Status**: correct, incorrect, ambiguous or unhelpful.
- **Usefulness**: whether the answer gives what was asked.

The guide fixes the hard cases the pilot raised. Every printed digit of a computed figure counts, and "about" does not loosen rounding. A wrong statement stays wrong when the answer later corrects it. A wrong currency name is a scale or currency error. A figure the table itself prints is supported, even if recomputing it gives a slightly different value. 20% of answers are labelled independently by two annotators, agreement is reported with Cohen's kappa per field, and disagreements are settled by an accounting adjudicator. Labelling time is logged per sitting.

`[RESULT: labelled answers, status distribution by country, generator and question type; span counts by slot; kappa per field; minutes per item.]`

### 3.6 Real-world condition

To measure how table-reading errors affect a checker, the Sri Lankan questions also come with evidence read by an automatic extractor, uncorrected. Three open tools were compared on 20 tables from 10 reports, with every table-finding strategy each offers and the same clean-up. Under a rule fixed before the run (most figures in the right row and column), PyMuPDF's text strategy was chosen. On all 48 Sri Lankan tables it places 94.2% of figures correctly, completes 23 tables, and detects the unit correctly for 42 of 48. US filings are HTML, whose tables read the same automatically as by hand, so US evidence is identical in both conditions.

| Tool (best strategy), 20 tables | Figures right | Wrong figures | Tables complete |
| --- | --- | --- | --- |
| PyMuPDF (text) | 90.0% | 220 | 8 |
| camelot (stream) | 87.4% | 32 | 11 |
| pdfplumber (text) | 82.4% | 215 | 9 |

### 3.7 Future-period set

The next annual report of each of the 24 test issuers is listed with the period it will cover and when it should appear, and is held back unopened. It supports a refresh in 2027 that no model, or author, has seen.

## 4. Pilot

Before the main questions were written, 60 pilot questions (33 Sri Lankan, 27 US) on the 8 development issuers were answered by both generators. The pilot fixed one generation bug (US tables shown with a rupee unit line) and set the annotation guide's hard cases. Labelled provisionally by an AI annotator, 23 of the 120 answers (19.2%) were incorrect: 14 from Gemma, 9 from Qwen. Errors concentrated in computed figures (growth 12 of 26 answers, share 6 of 18), against 3 of 38 lookups. The labelled spans were mostly a computed percentage off in its last digit (15), then reversed signs (6) and scale or currency errors (4). These labels are being reviewed by a person and are not part of the benchmark.

## 5. Uses

The benchmark supports three companion studies, each with pre-registered hypotheses: span detection with relation slots (`[cross-reference]`), program-based repair (`[cross-reference]`), and certified accept-repair-abstain policies (`[cross-reference]`). Each answer's numbers can be scored automatically against the gold expressions, so repaired or regenerated answers can be evaluated without new labels. Human labels remain the reference for the original answers.

## 6. Release

`[Settle before release: licence and terms; what is released (tables, questions, gold, answers, labels, code); where.]` The reports are public filings (CSE, SEC EDGAR). The questions, tables, answers and labels stay private until the test set is locked and the companion papers are submitted, so that no system is tuned on them.

## Limitations

- **Scale.** 24 issuers per country, two statements per report and 400 question groups; results come with issuer-clustered intervals.
- **Two generators**, both open models of 9–12B parameters at 4 bits; larger or proprietary models may err differently.
- **Fixed evidence.** Every system sees the same two statements; retrieval errors are out of scope.
- **Authoring.** Questions and gold answers were drafted with an AI assistant and checked by people; the pilot labels came from an AI annotator and are not part of the release.
- **English-language reports** only; Sri Lankan reports in Sinhala or Tamil are not covered.

## AI assistance statement

`[Finalise before submission.]` Claude (Anthropic) drafted the questions and gold answers, wrote the project's code, produced provisional pilot labels used only for design decisions, and drafted this paper. Every table and question is checked by a person before the test set is locked, the released labels are human, and the authors take responsibility for all content.

## References

`[Check every entry against the source and fill docs/related-work/benchmark.md.]`

- Chen, Z. et al. 2021. FinQA: A dataset of numerical reasoning over financial data. EMNLP.
- Islam, P. et al. 2023. FinanceBench: A new benchmark for financial question answering. arXiv. `[verify]`
- Niu, C. et al. 2024. RAGTruth: A hallucination corpus for developing trustworthy retrieval-augmented language models. ACL.
- Zhu, F. et al. 2021. TAT-QA: A question answering benchmark on a hybrid of tabular and textual content in finance. ACL.
- `[CITE: FinRank]`
- `[CITE: Qwen3.5 and Gemma 4 model cards; llama.cpp]`
- `[CITE: PyMuPDF, pdfplumber, camelot]`
