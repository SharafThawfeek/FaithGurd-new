# Annotation guide v1

This guide says how to label AI answers about financial reports in Label Studio. Version 1 is used for the pilot (phase 3). Version 2, revised from the pilot's disagreements, is frozen before full labelling.

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

## Process rules

- **Blinding:** never try to find out which model or system produced an answer.
- **Own work:** where possible, do not label outputs of the component you built.
- **Double labelling:** 20% of items are labelled by two people independently; do not discuss them before both are done.
- **Disagreements** go to the adjudicator, an accounting lecturer or senior accounting student, whose decision is final.
- **Time:** note roughly how long each batch took; the pilot uses this to measure minutes per item.

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
