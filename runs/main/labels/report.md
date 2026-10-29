# Pilot answers

Counts only. The gold scorer is strict (any figure outside the gold program counts as unsupported), so its error rate is an upper bound; the labels decide. See `faithguard.evaluate.pilot`.

| Country, generator | answers | empty | thinking_leaks | mean_words | narrative | supported_useful | supported_unhelpful | unsupported | checker_flagged | flagged_and_auto_wrong | flagged_but_auto_right | missed_auto_wrong |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| LK gemma | 248 | 0 | 0 | 26.6 | 36 | 155 | 3 | 54 | 74 | 54 | 20 | 0 |
| LK qwen | 248 | 0 | 0 | 48.8 | 36 | 141 | 5 | 66 | 76 | 46 | 30 | 20 |
| US gemma | 146 | 0 | 0 | 26.2 | 22 | 85 | 1 | 38 | 56 | 38 | 18 | 0 |
| US qwen | 146 | 0 | 0 | 43.1 | 22 | 85 | 2 | 37 | 48 | 28 | 20 | 9 |

## Automatic score by question type

| Type | supported_useful | supported_unhelpful | unsupported |
| --- | --- | --- | --- |
| comparison | 31 | 0 | 5 |
| difference | 99 | 2 | 19 |
| growth | 65 | 0 | 89 |
| lookup | 203 | 1 | 46 |
| ratio | 27 | 0 | 13 |
| share | 41 | 8 | 23 |

## What the rule checker flagged

| Slot or verdict | Claims |
| --- | --- |
| value | 122 |
| metric | 92 |
| period | 69 |
| entity_scope | 37 |
| scale_currency | 31 |
| missing_operand | 27 |
| sign | 26 |
| basis | 2 |

## Labels

Labelled by: claude-labeller@d103 (773), claude-adjudicator@d103 (15). Numeric answers are the answers to every question type but narrative; ambiguous labels are left out of the agreement counts.

**Error rate:** 177 of 788 answers labelled incorrect (22.5%); 170 of 672 numeric answers (25.3%).

| Country, generator | labelled | correct | incorrect | ambiguous | unhelpful | useful | numeric | numeric_incorrect |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| LK gemma | 248 | 186 | 54 | 1 | 7 | 206 | 212 | 54 |
| LK qwen | 248 | 188 | 53 | 0 | 7 | 218 | 212 | 47 |
| US gemma | 146 | 101 | 41 | 2 | 2 | 112 | 124 | 41 |
| US qwen | 146 | 117 | 29 | 0 | 0 | 131 | 124 | 28 |
| all | 788 | 592 | 177 | 3 | 16 | 667 | 672 | 170 |

### Rule checker and gold scorer against the labels (numeric answers)

| Country, generator | checker flagged, labelled incorrect | flagged, labelled right | missed, labelled incorrect | passed, labelled right | scorer wrong, labelled incorrect | scorer wrong, labelled right | scorer right, labelled incorrect |
| --- | --- | --- | --- | --- | --- | --- | --- |
| LK gemma | 51 | 23 | 3 | 135 | 51 | 3 | 3 |
| LK qwen | 32 | 44 | 15 | 121 | 34 | 32 | 13 |
| US gemma | 38 | 18 | 3 | 65 | 38 | 0 | 3 |
| US qwen | 23 | 25 | 5 | 71 | 22 | 15 | 6 |
| all | 144 | 110 | 26 | 392 | 145 | 50 | 25 |

### Labels by question type

| Type | correct | incorrect | ambiguous | unhelpful |
| --- | --- | --- | --- | --- |
| comparison | 29 | 7 | 0 | 0 |
| difference | 102 | 17 | 0 | 1 |
| growth | 65 | 88 | 0 | 1 |
| lookup | 222 | 24 | 0 | 4 |
| narrative | 100 | 7 | 3 | 6 |
| ratio | 31 | 9 | 0 | 0 |
| share | 43 | 25 | 0 | 4 |

### Labelled spans by slot

| Slot | Spans |
| --- | --- |
| value | 130 |
| unsupported_text | 30 |
| scale_currency | 28 |
| sign | 17 |
| entity_scope | 5 |
| period | 3 |
| basis | 2 |
| metric | 1 |
