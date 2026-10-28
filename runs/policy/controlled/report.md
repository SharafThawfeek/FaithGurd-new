# Policy study (controlled track)

Risk target alpha = 0.1, confidence 1 - delta = 0.95. Splits are issuer-disjoint:

| Split | Items | Issuers |
| --- | --- | --- |
| fit | 13,383 | 984 |
| tune | 2,447 | 194 |
| calibration | 5,423 | 401 |
| test | 6,450 | 391 |

These answers were made by the project's error injector from FinQA and TAT-QA gold programs, so they rehearse the method; the paper's claims rest on the human-labelled natural test.

## Certified policies on the test split

Each family's grid is ordered on the tune split and certified on the calibration split (Learn-then-Test, Hoeffding-Bentkus, fixed sequence). The chosen setting is then applied to test; brackets are 95% intervals from an issuer-clustered bootstrap.

| Policy | Certified settings | Chosen | Answers sent | Wrong among sent | Useful answers | Regret vs oracle |
| --- | --- | --- | --- | --- | --- | --- |
| send_all | 0 of 1 | none (p = 1) | 100.0% | 79.0% | 21.0% | – |
| repair_all | 1 of 1 | `repair` | 74.0% | 1.6% [1.0%, 2.2%] | 72.7% [70.4%, 74.7%] | 0.1% |
| verified_only | 1 of 3 | `risk<0.25` | 21.5% | 2.9% [1.7%, 4.2%] | 20.9% [20.5%, 21.2%] | 52.0% |
| threshold_v0 | 1 of 3 | `risk<0.25` | 74.0% | 1.6% [1.0%, 2.2%] | 72.7% [70.4%, 74.7%] | 0.1% |
| four_state | 6 of 6 | `conf>=0.5` | 73.8% | 1.5% [0.9%, 2.2%] | 72.7% [70.4%, 74.6%] | 0.2% |
| outcome_aware[lightgbm] | 56 of 56 | `send<0.5,fix>0.6` | 73.8% | 1.6% [1.0%, 2.2%] | 72.7% [70.4%, 74.6%] | 0.2% |
| outcome_aware[neural] | 56 of 56 | `send<0.005,fix>0.7` | 73.5% | 1.3% [0.7%, 1.9%] | 72.5% [70.2%, 74.5%] | 0.3% |
| oracle (hindsight) | – | – | 72.9% | 0.0% | 72.9% | 0 |

## Outcome models on test

The injector deletes the cell a missing_operand item needs, so that row reads shorter than the others. A model that reads the evidence text can see this, the checker's features mostly do not, and natural answers do not have the cue: the rows without those items are the like-for-like comparison.

| Model | Target | Test items | AUROC | Brier | ECE |
| --- | --- | --- | --- | --- | --- |
| lightgbm | P(unsafe), all | 6,450 | 0.997 | 0.0075 | 0.0052 |
| lightgbm | P(unsafe), excl. missing_operand | 5,114 | 0.996 | 0.0079 | 0.0057 |
| lightgbm | P(fix), all | 6,450 | 0.991 | 0.0127 | 0.0063 |
| lightgbm | P(fix), excl. missing_operand | 5,114 | 0.967 | 0.0123 | 0.0062 |
| neural | P(unsafe), all | 6,450 | 0.997 | 0.0069 | 0.0056 |
| neural | P(unsafe), excl. missing_operand | 5,114 | 0.997 | 0.0072 | 0.0055 |
| neural | P(fix), all | 6,450 | 0.993 | 0.0123 | 0.0062 |
| neural | P(fix), excl. missing_operand | 5,114 | 0.973 | 0.0116 | 0.0052 |

Brier score by planted error (AUROC is undefined where every item has the same target):

| Planted error | Items | P(unsafe), lightgbm | P(unsafe), neural | P(fix), lightgbm | P(fix), neural |
| --- | --- | --- | --- | --- | --- |
| basis | 434 | 0.0020 | 0.0023 | 0.0106 | 0.0095 |
| metric | 1,309 | 0.0015 | 0.0014 | 0.0128 | 0.0125 |
| missing_operand | 1,336 | 0.0060 | 0.0057 | 0.0145 | 0.0149 |
| none | 1,356 | 0.0097 | 0.0127 | 0.0057 | 0.0091 |
| period | 858 | 0.0102 | 0.0101 | 0.0170 | 0.0164 |
| scale | 327 | 0.0000 | 0.0000 | 0.0123 | 0.0117 |
| sign | 830 | 0.0189 | 0.0096 | 0.0181 | 0.0102 |

## Certified outcome-aware policies by planted error

Each outcome model's chosen setting, on test.

| Planted error | Items | Wrong among sent (lightgbm) | Useful (lightgbm) | Wrong among sent (neural) | Useful (neural) |
| --- | --- | --- | --- | --- | --- |
| basis | 434 | 0.7% | 98.8% | 0.7% | 99.1% |
| metric | 1,309 | 0.8% | 83.3% | 0.8% | 83.3% |
| missing_operand | 1,336 | 100.0% | 0.0% | 100.0% | 0.0% |
| none | 1,356 | 0.3% | 99.3% | 0.3% | 98.6% |
| period | 858 | 1.8% | 80.9% | 1.6% | 80.9% |
| scale | 327 | 0.9% | 98.2% | 0.9% | 98.2% |
| sign | 830 | 2.2% | 97.0% | 1.0% | 97.1% |

## The chosen outcome-aware policy

Actions on test: {'send': 1385, 'repair': 3386, 'abstain': 1679}.

Flip matrix on test (state of the original answer → state after repair):

| Original | Unsupported | Supported, unhelpful | Supported, useful | Abstained |
| --- | --- | --- | --- | --- |
| unsupported | 73 | 2 | 3344 | 1675 |
| supported_unhelpful | 0 | 0 | 1 | 0 |
| supported_useful | 3 | 0 | 1347 | 5 |

By source:

| Group | Items | Sent | Wrong among sent | Useful |
| --- | --- | --- | --- | --- |
| finqa | 2217 | 67.8% | 0.7% | 67.3% |
| tatqa | 4233 | 77.0% | 1.9% | 75.5% |

By question type:

| Group | Items | Sent | Wrong among sent | Useful |
| --- | --- | --- | --- | --- |
| difference | 1609 | 76.9% | 1.9% | 75.5% |
| growth | 2506 | 81.3% | 0.6% | 80.8% |
| lookup | 1697 | 77.5% | 2.8% | 75.3% |
| share | 638 | 26.8% | 1.2% | 26.5% |

By planted error:

| Group | Items | Sent | Wrong among sent | Useful |
| --- | --- | --- | --- | --- |
| basis | 434 | 99.5% | 0.7% | 98.8% |
| metric | 1309 | 84.0% | 0.8% | 83.3% |
| missing_operand | 1336 | 1.8% | 100.0% | 0.0% |
| none | 1356 | 99.6% | 0.3% | 99.3% |
| period | 858 | 82.4% | 1.8% | 80.9% |
| scale | 327 | 99.4% | 0.9% | 98.2% |
| sign | 830 | 99.2% | 2.2% | 97.0% |

## Certification budget

Random calibration subsets of each size, for each outcome model whose policy certified: share of draws in which at least one setting is certified, and the useful coverage on test of the setting then chosen.

| Calibration answers | Certified (lightgbm) | Useful coverage on test (lightgbm) | Certified (neural) | Useful coverage on test (neural) |
| --- | --- | --- | --- | --- |
| 50 | 0.0% | – | 0.0% | – |
| 100 | 1.0% | 59.7% | 6.0% | 61.8% |
| 200 | 75.0% | 67.6% | 84.0% | 70.8% |
| 400 | 100.0% | 72.5% | 100.0% | 72.5% |
| 800 | 100.0% | 72.6% | 100.0% | 72.5% |
| 1600 | 100.0% | 72.7% | 100.0% | 72.5% |
| 3200 | 100.0% | 72.7% | 100.0% | 72.5% |

## Issuer-level sensitivity check

Treating each issuer as one draw, the chosen setting's p-value on calibration is 0.002 (item-level: 1.49e-50); certified at delta = 0.05: True.

## SCoRE comparator (send or abstain only)

SCoRE-SDR (score-select 0.1.1) with the same P(unsafe) scores, alpha = gamma = 0.1, 'homo' boosting; guarantee: expected risk among sent answers <= alpha (not a high-probability bound). All 5,423 calibration answers against 3 random test subsamples of 500.

Answers sent 22.7%; wrong among sent 5.5%; useful 21.4%. It decides only send or abstain, so compare it with verified_only; repair is what lifts the other policies' useful coverage.

Run time: 87.5 s.
