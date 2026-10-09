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
| oracle (hindsight) | – | – | 72.9% | 0.0% | 72.9% | 0 |

## Outcome models on test

| Model | Target | AUROC | Brier | ECE |
| --- | --- | --- | --- | --- |
| lightgbm | P(unsafe) | 0.997 | 0.008 | 0.005 |
| lightgbm | P(fix) | 0.991 | 0.013 | 0.006 |

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

Random calibration subsets of each size; share of draws in which at least one setting is certified, and the useful coverage on test of the setting then chosen.

| Calibration answers | Certified | Useful coverage on test |
| --- | --- | --- |
| 50 | 0.0% | – |
| 100 | 1.0% | 59.7% |
| 200 | 75.0% | 67.6% |
| 400 | 100.0% | 72.5% |
| 800 | 100.0% | 72.6% |
| 1600 | 100.0% | 72.7% |
| 3200 | 100.0% | 72.7% |

## Issuer-level sensitivity check

Treating each issuer as one draw, the chosen setting's p-value on calibration is 0.002 (item-level: 1.49e-50); certified at delta = 0.05: True.

## SCoRE comparator (send or abstain only)

SCoRE-SDR (score-select 0.1.1) with the same P(unsafe) scores, alpha = gamma = 0.1, 'homo' boosting; guarantee: expected risk among sent answers <= alpha (not a high-probability bound). All 5,423 calibration answers against 3 random test subsamples of 500.

Answers sent 22.7%; wrong among sent 5.5%; useful 21.4%. It decides only send or abstain, so compare it with verified_only; repair is what lifts the other policies' useful coverage.

Run time: 58.9 s.
