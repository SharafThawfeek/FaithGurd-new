# Labelling triage: code labels and a person's labels (D-100)

Counts only. Code labels an answer correct when every number matches the gold cells and nothing else in it could still be wrong; a person labels the rest, plus a hidden, stratified audit sample of the code labels. See `faithguard.evaluate.triage`.

| Answers | Code labels | A person labels | Audit sample (also a person) |
| --- | --- | --- | --- |
| 120 | 61 | 59 | 61 |

| Why a person labels it (an answer can have several reasons) | Answers |
| --- | --- |
| a number the gold values do not cover | 23 |
| narrative question | 16 |
| an explanation or judgement | 7 |
| a difference between two entities | 6 |
| no number states the answer | 4 |
| comparison question | 4 |
| a negation, hedge or guess | 3 |
| a direction word the scorer cannot check | 3 |
| an entity that is not its figure's | 2 |
| a year that is not its figure's | 2 |
| a metric name that is not its figure's | 1 |
| a currency the report does not use | 1 |

### Against the other labels in the gold store (claude: 120)

| Routed to | Labels: correct | incorrect | unhelpful | ambiguous |
| --- | --- | --- | --- | --- |
| code | 61 | 0 | 0 | 0 |
| person | 33 | 23 | 3 | 0 |

Code labels those labels overrule: 0 of 61.
