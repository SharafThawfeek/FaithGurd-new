# Annotation guide v2

This guide says how to label AI answers about financial reports in Label Studio. Version 1 was used for the pilot (phase 3). Version 2 adds the hard cases the pilot raised ([Hard cases](#hard-cases), and [Changes from v1](#changes-from-v1) at the end) and is used for all main labelling. It is frozen once a person has reviewed the pilot labels and found no case it leaves open; after that, any change needs a decision-log entry.

## What you see

Each task shows a **question**, the **evidence** (report tables and text) and one **answer**. You never see which model wrote the answer or whether it has been repaired. Judge the answer against the evidence shown and nothing else, not your own knowledge of the company.

## What you do

1. **Select every wrong or unsupported span** in the answer and pick what is wrong with it (the slot, below). Select the number together with its currency and unit ("Rs. 12,450 million", not just "12,450"). Select a direction word ("rose", "fell") only if the word itself is wrong.
2. **Choose the overall status:** correct, incorrect, ambiguous or unhelpful.
3. **Choose usefulness:** useful if the answer gives what the question asked for.
4. **Add a note** whenever you choose ambiguous, or when the adjudicator should look at something.

## Slots: what is wrong with a span

| Slot | Use when | Example (evidence: Group PAT 2025 = Rs. 14,212,560 '000; Bank PAT 2025 = Rs. 12,450,330 '000) |
| --- | --- | --- |
| entity_scope | The number belongs to another entity or scope | "Group profit was Rs. 12,450 million" (that is the Bank's) |
| metric | The number belongs to another line item | Profit before tax quoted as profit after tax |
| period | The number belongs to another year or quarter | The 2024 figure given for 2025 |
| unit | The kind of quantity is wrong | "12.4 million shares" for a currency amount |
| scale_currency | Right digits, wrong scale or currency | "Rs. 14,212,560 million" (the table is in Rs. '000) |
| sign | Up stated as down, or a wrong minus | "fell 9.3%" when it rose |
| basis | Growth or share computed on the wrong base | Change divided by this year instead of last year |
| missing_operand | The evidence does not contain what the claim needs | A return on equity the report extract never shows |
| value | Simply the wrong number, no better description | "Rs. 15,000 million" with no matching figure anywhere |
| unsupported_text | A non-numeric statement the evidence does not support | "driven by record loan growth" with no such statement |

If two slots apply (wrong entity *and* wrong scale), pick the one that explains the number best and mention the other in the note.

## Rounding

A number is correct if it rounds to the printed precision of the true value. "Rs. 14.2 billion" and "Rs. 14,213 million" are both correct for Rs. 14,212,560 thousand. "Rs. 14.3 billion" is wrong (slot: value). Percentages follow the same rule: 9.29% may be written 9.3% or 9%.

## Status

| Status | Use when |
| --- | --- |
| correct | Every statement is supported by the evidence |
| incorrect | At least one span is wrong or unsupported |
| ambiguous | The evidence allows more than one reasonable reading (for example, restated comparatives, or a question that could mean Group or Company). Always add a note. |
| unhelpful | Nothing is wrong, but the answer does not address the question (or says it cannot answer when the evidence does answer it) |

"Ambiguous" is a valid, honest label. Do not force unclear accounting into right or wrong.

## Hard cases

These come from the 120 pilot answers (decision D-066). The examples use the fictional bank above, whose Group profit after tax grew 9.2922% (from Rs. 13,004,180 thousand to Rs. 14,212,560 thousand).

| Case | Rule | Example |
| --- | --- | --- |
| A computed figure | Every printed digit counts. A worked-out percentage or ratio is right only if the true value rounds to it at the precision the answer prints. "About" or "roughly" does not loosen this. Most wrong pilot answers were a computed percentage off in its last digit. | "9.29%", "9.3%" and "9%" are right; "9.30%", "9.2%" and "about 10%" are wrong (slot: value) |
| A wrong statement the answer later corrects | Still wrong. Select the wrong part and choose incorrect; choose useful if the answer's final figure is what was asked. | "Profit fell ... in fact it rose 9.3%": select "fell" (sign) |
| A claim that the evidence lacks something | If the evidence does hold it, the claim is unsupported_text. If the evidence really lacks it, saying so is correct. | "The extract gives no profit figure for the Bank" (it does) |
| Right figures, wrong question | If nothing is wrong but the answer gives an amount when a share was asked, or compares years when the question compares Group and Bank: choose unhelpful and not useful, and select no spans. | Asked for the Bank's share of Group profit, answers only "Rs. 12,450 million" |
| Currency and unit words | A wrong currency name, or a unit that contradicts the figure, is scale_currency even when the digits are right. Select the word, or the figure with its unit. | "Indian rupees" for Sri Lankan rupees; "Rs. 14,212,560,000 ('000)" |
| A figure the table itself prints | Supported, even if recomputing it from the amounts gives a slightly different number. | A change column printed "(3)%" where the amounts give a 2.8% fall |
| Working shown in the answer | Intermediate figures are judged like any other figure. Leaving the table's unit off the operands is not an error when the result is right. | "12,450,330 / 14,212,560 = 87.6%" |
| Falls and losses | A fall may be written "fell 9.3%", "a 9.3% decrease" or "-9.3%"; a loss "a loss of Rs. 2.1 billion" or "Rs. (2.1) billion". A minus sign with "rose", or "increase" for a fall, is a sign error. | "rose -9.3%": sign |
| Harmless extras | Explaining a term, naming the table's unit, or hedging about a name is not an error if no figure is wrong. | "the Group (which the report calls ...) earned Rs. 14,213 million" |

## Process rules

- **Blinding:** never try to find out which model or system produced an answer.
- **Own work:** where possible, do not label outputs of the component you built.
- **Double labelling:** 20% of items are labelled by two people independently; do not discuss them before both are done.
- **Disagreements** go to the adjudicator, an accounting lecturer or senior accounting student, whose decision is final.
- **Time:** after each sitting, add a line to [logs/labelling-hours.csv](../logs/labelling-hours.csv): the date, your name, the task file, how many items you finished and how many minutes it took. Minutes per item come from this log.
- **Pre-filled labels:** a task may come with suggested labels (the pilot's labels by Claude, for example). They are suggestions: read every task, check each span and choice against the evidence, and correct what is wrong. Never accept one unread. Main-benchmark tasks come without suggestions, so they cannot anchor the labels.

## Setting up Label Studio

Label Studio runs in its own environment, separate from the project's:

```bash
python -m venv .venv-labelstudio
```

```bash
.venv-labelstudio/Scripts/python -m pip install label-studio==1.23.2
```

```bash
.venv-labelstudio/Scripts/label-studio start
```

Then create a project, paste `labelling/label_config.xml` into *Settings → Labeling Interface → Code*, and import the tasks file made by `faithguard labelling tasks`. Export results as JSON and convert them with `faithguard labelling import`.

To review the pilot's suggested labels, import `data/benchmark-build/labels/tasks-with-labels.json` (not in git) instead, and turn on *Settings → Annotation → Use predictions to prelabel tasks*: each task then opens with the suggestions filled in. Submit each task after checking it, export, and convert the export as above with the pilot's mapping (`--mapping data/benchmark-build/gold/task-mapping.json --gold data/benchmark-build/gold`). Your labels then decide each answer in `faithguard pilot`, ahead of the suggestions.

## Changes from v1

- The [Hard cases](#hard-cases) table, from the pilot answers.
- Time is logged per sitting in `logs/labelling-hours.csv`, so minutes per item can be measured.
- Pre-filled labels are suggestions to check; main-benchmark tasks have none.
