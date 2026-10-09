# Benchmark guide (phase 3)

This guide says how to turn annual reports into benchmark questions with gold answers. The format is checked by code, so most mistakes are caught before anyone labels anything.

A complete working example is in [benchmark-example/](../benchmark-example/) (a fictional bank).

## 1. Where things go

| What | Where | In git? |
| --- | --- | --- |
| Report files (Sri Lankan PDFs, US 10-K web pages) | `data/raw/reports/<country>/<ISSUER>/<period end>.pdf` or `.htm`, copied to the shared Drive `FaithGuard/reports/` | No |
| Corrected tables and questions | `data/benchmark/<country>/<ISSUER>/<fiscal year>.yaml` and `data/benchmark/<country>/<ISSUER>/<fiscal year>/<table id>.csv` | No: keep them in the private Drive and a private Kaggle Dataset |
| Built questions and gold | `data/benchmark-build/` (made by `faithguard benchmark build`) | No |

The repository is public, so benchmark content stays out of it until the test set is locked and released.

## 2. Which reports

Use the issuers in [manifests/splits.json](../manifests/splits.json): 12 test, 12 calibration and 4 development issuers per country (decision D-007). For Sri Lanka, each issuer's latest annual report on the CSE is already listed in [manifests/lk-reports.csv](../manifests/lk-reports.csv) (period, filing date, link, size). List or fetch them by split; the pilot needs only `dev` (4 reports, 43 MB):

```bash
faithguard reports list --splits dev
```

```bash
faithguard reports download --splits dev
```

Downloads go to `data/raw/reports/LK/<ISSUER>/<period end>.pdf` and their checksums are recorded in the manifest. Put the link in the report file's `source` field.

For the US, [manifests/us-reports.csv](../manifests/us-reports.csv) lists each issuer's latest 10-K on SEC EDGAR (decision D-041); the pilot's four are 9 MB. The SEC needs a declared contact, so set `FG_SEC_USER_AGENT` first (see the README):

```bash
faithguard reports download --country US --splits dev
```

Each 10-K's main document is saved as `data/raw/reports/US/<ISSUER>/<period end>.htm`, byte for byte as filed (the script tag the SEC's web server adds is removed, so checksums agree). `faithguard reports locate --country US` rebuilds the manifest from EDGAR, for example to find next year's reports.

Pilot questions come only from the 4 development issuers per country (decision D-004).

## 3. Correct the tables

For each table a question will use, make one CSV that copies the table **exactly as printed**:

- header rows first (for example `Group, Group, Bank, Bank` then `2025, 2024, 2025, 2024`), with the unit line (`Rs. '000`) in the first column;
- one row per line item, label in the first column;
- numbers as printed, including commas and brackets for negatives (`(2,104,330)`), and `-` for nil;
- nothing added, nothing rounded.

Usually the income statement and the statement of financial position are enough; add segment or ratio tables when a question needs them. Check every CSV against the PDF, cell by cell. That correction is what makes the main test free of table-reading errors.

Don't type the tables: draft each CSV from the PDF, then correct the draft. Give the page numbers a PDF viewer shows (not the folio printed on the page). A statement that runs over two pages is one table, so give both pages:

```bash
python -m faithguard.data.pdf_tables data/raw/reports/LK/SAMP/2025-12-31.pdf 374,375 data/benchmark/LK/SAMP/2025/t2.csv
```

The reader takes the figures from the PDF's own text, so the digits are exact. What can still go wrong is a figure in the wrong row or column, or a label that wraps onto a second line starting with a capital letter ("Impact on restructuring of Sri Lanka / International Sovereign Bonds"): join such labels by hand. It also reports how many subtotals add up. In a full statement every "Total ..." row equals the rows above it, so a total that does not add up points at a misplaced or misread figure. Scanned reports have no text to read; type those tables.

For a US 10-K, list its tables by the text above each one, then draft the one you need by its number:

```bash
python -m faithguard.data.html_tables data/raw/reports/US/MEDP/2025-12-31.htm list "balance sheet|statements? of operations"
```

```bash
python -m faithguard.data.html_tables data/raw/reports/US/MEDP/2025-12-31.htm extract 14 data/benchmark/US/MEDP/2025/t1.csv
```

The 10-K's own HTML table gives the digits and layout, so drafts are usually right as they stand (decision D-048): a lone "$" is dropped, a bracket or "%" in its own cell is joined to its number, and the unit line ("(in thousands, except per share data)") goes in the first column. Still compare every row with the filing, and run `faithguard benchmark check`, which adds up the totals. A 10-K has no page numbers to give; leave `page` out and use the statement's title. For a fiscal year that ends in January (Dick's Sporting Goods, Silicon Labs), `fiscal_year` is the calendar year it ends in, and questions should name the year-end date ("the fiscal year ended January 31, 2026") rather than the company's own "fiscal 2025".

Name tables `t1`, `t2`, ... in the report file:

```yaml
issuer: COMB
country: LK
name: Commercial Bank of Ceylon PLC
fiscal_year: "2025"
year_end: "2025-12-31"
source: <the URL you downloaded the PDF from>
tables:
  t1:
    title: Income statement
    page: 214
    currency: LKR
  t2:
    title: Statement of financial position
    page: 216
    currency: LKR
questions: []
```

## 4. Find the cell ids

```bash
faithguard benchmark cells data/benchmark/LK/COMB/2025.yaml
```

This lists every cell with its id (`t1r3c1` = table 1, row 3, column 1, counting from 0 in the CSV) and the entity, line item and year the code reads from the headers. If those look wrong, fix the CSV headers.

## 5. Write questions

Each question has:

| Field | What to write |
| --- | --- |
| `id` | `<ISSUER>-<year>-<number>`, unique |
| `text` | The question, as a user would ask it |
| `type` | lookup, growth, difference, share, ratio, sum, average, comparison or narrative |
| `answer` | The gold answer as a cell expression: `t1r3c1`, `growth(t1r3c1, t1r3c2)`, `t1r2c1 - t1r2c3`, `share(t2r4c3, t2r4c1)` |
| `expect` | The answer as you read it in the report, with units: `Rs. 14,212,560 thousand`, `9.3%` |
| `author` / `checked_by` | Your name; then a different member's name once they have checked it |
| `pilot` | `true` for pilot questions (development issuers only) |

Narrative questions (type `narrative`) need no `answer`; put a reference answer in `expect`. They are labelled by people only.

**Aim for questions that invite wrong-context mistakes**, because those are what the project studies:

- Group versus Company or Bank figures (the same line item, two entities);
- this year versus last year;
- tables in Rs. '000 or millions, asked about in millions or billions;
- growth and differences, where the base year matters;
- shares of a total (which total?);
- a few questions whose answer is not in the report, where the right reply is to decline.

A rough mix per issuer: lookups 30%, growth 20%, differences 15%, shares and ratios 15%, comparisons 5%, narrative 15%.

## 6. Check

```bash
faithguard benchmark check
```

It recomputes every gold answer from its cells and compares it with `expect`. Errors (must fix): a mismatch (wrong cell, wrong row, misread number), an expression that fails, a duplicate id, a pilot question from a non-development issuer. Warnings (should fix): a question not yet cross-checked, or checked by its own author, or a type that does not match its expression, or a table row labelled "Total ..." (or left unlabelled) that is not the sum of the rows above it. Tables where no subtotal adds up at all are taken to be extracts and are not summed.

Run it until there are no errors.

## 7. Build, generate, label

1. Build the questions with their frozen evidence and gold. Add `--pilot-only` for the pilot:

```bash
faithguard benchmark build --pilot-only
```

Rebuilding (after a table fix, say) replaces only the gold answers: labels and injections already in the gold store are kept.

2. Upload `data/benchmark-build/questions.jsonl` (never the gold store) as a **private** Kaggle Dataset and run [notebooks/generate_answers.ipynb](../notebooks/generate_answers.ipynb). It answers every question with both generators.

3. Download `answers-qwen.jsonl` and `answers-gemma.jsonl`, and join them with the questions:

```bash
faithguard items --questions data/benchmark-build/questions.jsonl --answers answers-qwen.jsonl answers-gemma.jsonl --out data/benchmark-build/items.jsonl
```

4. Make blinded Label Studio tasks and label them as in the [annotation guide](annotation-guide.md):

```bash
faithguard labelling tasks --items data/benchmark-build/items.jsonl
```

## 8. Pilot decisions (agreed in advance)

After labelling the 120 pilot answers, record in the decision log:

- **Minutes per item.** Above 6, cut US question groups to 120 first.
- **Error rate.** Below about 10%, add harder question types.
- **Thinking leaks and empty answers.** These come from the generation summary; if either is common, fix the settings before the full run.
