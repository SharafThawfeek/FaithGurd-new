# Pilot answers

Counts only. The gold scorer is strict (any figure outside the gold program counts as unsupported), so its error rate is an upper bound; the labels decide. See `faithguard.evaluate.pilot`.

| Country, generator | answers | empty | thinking_leaks | mean_words | narrative | supported_useful | supported_unhelpful | unsupported | checker_flagged | flagged_and_auto_wrong | flagged_but_auto_right | missed_auto_wrong |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| LK gemma | 33 | 0 | 0 | 24.8 | 4 | 19 | 2 | 8 | 8 | 8 | 0 | 0 |
| LK qwen | 33 | 0 | 0 | 44.9 | 4 | 23 | 2 | 4 | 5 | 2 | 3 | 2 |
| US gemma | 27 | 0 | 0 | 25.6 | 4 | 17 | 0 | 6 | 12 | 6 | 6 | 0 |
| US qwen | 27 | 0 | 0 | 47.9 | 4 | 16 | 0 | 7 | 10 | 6 | 4 | 1 |

## Automatic score by question type

| Type | supported_useful | supported_unhelpful | unsupported |
| --- | --- | --- | --- |
| comparison | 2 | 0 | 2 |
| difference | 14 | 0 | 0 |
| growth | 14 | 1 | 11 |
| lookup | 33 | 0 | 5 |
| ratio | 3 | 0 | 1 |
| share | 9 | 3 | 6 |

## What the rule checker flagged

| Slot or verdict | Claims |
| --- | --- |
| metric | 19 |
| value | 13 |
| period | 11 |
| sign | 9 |
| missing_operand | 8 |
| scale_currency | 5 |
| entity_scope | 2 |
| basis | 1 |

## Labels

Labelled by: claude (120). Numeric answers are the answers to every question type but narrative; ambiguous labels are left out of the agreement counts.

**Error rate:** 23 of 120 answers labelled incorrect (19.2%); 23 of 104 numeric answers (22.1%).

| Country, generator | labelled | correct | incorrect | ambiguous | unhelpful | useful | numeric | numeric_incorrect |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| LK gemma | 33 | 23 | 8 | 0 | 2 | 23 | 29 | 8 |
| LK qwen | 33 | 28 | 4 | 0 | 1 | 29 | 29 | 4 |
| US gemma | 27 | 21 | 6 | 0 | 0 | 21 | 23 | 6 |
| US qwen | 27 | 22 | 5 | 0 | 0 | 24 | 23 | 5 |
| all | 120 | 94 | 23 | 0 | 3 | 97 | 104 | 23 |

### Rule checker and gold scorer against the labels (numeric answers)

| Country, generator | checker flagged, labelled incorrect | flagged, labelled right | missed, labelled incorrect | passed, labelled right | scorer wrong, labelled incorrect | scorer wrong, labelled right | scorer right, labelled incorrect |
| --- | --- | --- | --- | --- | --- | --- | --- |
| LK gemma | 8 | 0 | 0 | 21 | 8 | 0 | 0 |
| LK qwen | 1 | 4 | 3 | 21 | 1 | 3 | 3 |
| US gemma | 6 | 6 | 0 | 11 | 6 | 0 | 0 |
| US qwen | 4 | 6 | 1 | 12 | 5 | 2 | 0 |
| all | 19 | 16 | 4 | 65 | 20 | 5 | 3 |

### Labels by question type

| Type | correct | incorrect | ambiguous | unhelpful |
| --- | --- | --- | --- | --- |
| comparison | 2 | 1 | 0 | 1 |
| difference | 14 | 0 | 0 | 0 |
| growth | 14 | 12 | 0 | 0 |
| lookup | 35 | 3 | 0 | 0 |
| narrative | 16 | 0 | 0 | 0 |
| ratio | 3 | 1 | 0 | 0 |
| share | 10 | 6 | 0 | 2 |

### Labelled spans by slot

| Slot | Spans |
| --- | --- |
| value | 15 |
| sign | 6 |
| scale_currency | 4 |
| unsupported_text | 2 |
