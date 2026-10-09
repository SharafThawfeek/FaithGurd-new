# Pilot answers: automatic first look

Counts only. The gold scorer is strict (any figure outside the gold program counts as unsupported), so its error rate is an upper bound; the labels decide. See `faithguard.evaluate.pilot`.

| Country, generator | answers | empty | thinking_leaks | mean_words | narrative | supported_useful | supported_unhelpful | unsupported | checker_flagged | flagged_and_auto_wrong | flagged_but_auto_right | missed_auto_wrong |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| LK gemma | 33 | 0 | 0 | 24.8 | 4 | 18 | 2 | 9 | 9 | 9 | 0 | 0 |
| LK qwen | 33 | 0 | 0 | 44.9 | 4 | 22 | 2 | 5 | 5 | 3 | 2 | 2 |
| US gemma | 27 | 0 | 0 | 25.6 | 4 | 13 | 0 | 10 | 12 | 9 | 3 | 1 |
| US qwen | 27 | 0 | 0 | 47.9 | 4 | 13 | 0 | 10 | 10 | 8 | 2 | 2 |

## Automatic score by question type

| Type | supported_useful | supported_unhelpful | unsupported |
| --- | --- | --- | --- |
| comparison | 1 | 0 | 3 |
| difference | 12 | 0 | 2 |
| growth | 12 | 1 | 13 |
| lookup | 30 | 0 | 8 |
| ratio | 2 | 0 | 2 |
| share | 9 | 3 | 6 |

## What the rule checker flagged

| Slot or verdict | Claims |
| --- | --- |
| metric | 20 |
| value | 13 |
| period | 11 |
| sign | 9 |
| missing_operand | 8 |
| scale_currency | 5 |
| entity_scope | 3 |
| basis | 1 |
