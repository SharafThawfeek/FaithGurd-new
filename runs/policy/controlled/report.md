# Policy study (controlled track)

Risk target alpha = 0.1, confidence 1 - delta = 0.95. Splits are issuer-disjoint:

| Split | Items | Issuers |
| --- | --- | --- |
| fit | 13,157 | 964 |
| tune | 2,401 | 190 |
| calibration | 5,336 | 390 |
| test | 6,258 | 381 |

These answers were made by the project's error injector from FinQA and TAT-QA gold programs, so they rehearse the method; the paper's claims rest on the human-labelled natural test.

## Certified policies on the test split

Each family's grid is ordered on the tune split and certified on the calibration split (Learn-then-Test, Hoeffding-Bentkus, fixed sequence). The chosen setting is then applied to test; brackets are 95% intervals from an issuer-clustered bootstrap.

| Policy | Certified settings | Chosen | Answers sent | Wrong among sent | Useful answers | Regret vs oracle |
| --- | --- | --- | --- | --- | --- | --- |
| send_all | 0 of 1 | none (p = 1) | 100.0% | 79.0% | 21.0% | – |
| repair_all | 1 of 1 | `repair` | 73.8% | 1.5% [0.9%, 2.1%] | 72.7% [70.4%, 74.9%] | 0.1% |
| verified_only | 1 of 3 | `risk<0.25` | 21.5% | 2.8% [1.7%, 4.0%] | 20.9% [20.5%, 21.3%] | 51.9% |
| threshold_v0 | 1 of 3 | `risk<0.25` | 73.8% | 1.5% [0.9%, 2.1%] | 72.7% [70.4%, 74.9%] | 0.1% |
| four_state | 6 of 6 | `conf>=0.5` | 73.6% | 1.4% [0.8%, 2.0%] | 72.6% [70.3%, 74.8%] | 0.3% |
| outcome_aware[lightgbm] | 56 of 56 | `send<0.3,fix>0.5` | 73.7% | 1.4% [0.8%, 2.0%] | 72.6% [70.3%, 74.9%] | 0.2% |
| oracle (hindsight) | – | – | 72.9% | 0.0% | 72.8% | 0 |

## Outcome models on test

| Model | Target | AUROC | Brier | ECE |
| --- | --- | --- | --- | --- |
| lightgbm | P(unsafe) | 0.997 | 0.007 | 0.005 |
| lightgbm | P(fix) | 0.990 | 0.012 | 0.007 |

## The chosen outcome-aware policy

Actions on test: {'send': 1333, 'repair': 3286, 'abstain': 1639}.

Flip matrix on test (state of the original answer → state after repair):

| Original | Unsupported | Supported, unhelpful | Supported, useful | Abstained |
| --- | --- | --- | --- | --- |
| unsupported | 65 | 2 | 3241 | 1633 |
| supported_unhelpful | 0 | 0 | 1 | 0 |
| supported_useful | 2 | 0 | 1309 | 5 |

By source:

| Group | Items | Sent | Wrong among sent | Useful |
| --- | --- | --- | --- | --- |
| finqa | 2124 | 67.4% | 0.8% | 66.9% |
| tatqa | 4134 | 76.9% | 1.6% | 75.6% |

By question type:

| Group | Items | Sent | Wrong among sent | Useful |
| --- | --- | --- | --- | --- |
| difference | 1566 | 76.8% | 1.7% | 75.4% |
| growth | 2393 | 81.3% | 0.6% | 80.8% |
| lookup | 1669 | 77.5% | 2.2% | 75.7% |
| share | 630 | 26.8% | 1.2% | 26.5% |

By planted error:

| Group | Items | Sent | Wrong among sent | Useful |
| --- | --- | --- | --- | --- |
| basis | 414 | 99.5% | 0.7% | 98.8% |
| metric | 1271 | 83.8% | 0.7% | 83.2% |
| missing_operand | 1297 | 1.7% | 100.0% | 0.0% |
| none | 1317 | 99.5% | 0.2% | 99.3% |
| period | 838 | 82.3% | 1.6% | 81.0% |
| scale | 322 | 99.4% | 0.3% | 98.8% |
| sign | 799 | 99.0% | 2.0% | 97.0% |

## Certification budget

Random calibration subsets of each size; share of draws in which at least one setting is certified, and the useful coverage on test of the setting then chosen.

| Calibration answers | Certified | Useful coverage on test |
| --- | --- | --- |
| 50 | 0.0% | – |
| 100 | 2.0% | 65.5% |
| 200 | 80.0% | 71.0% |
| 400 | 100.0% | 72.5% |
| 800 | 100.0% | 72.6% |
| 1600 | 100.0% | 72.6% |
| 3200 | 100.0% | 72.6% |

## Issuer-level sensitivity check

Treating each issuer as one draw, the chosen setting's p-value on calibration is 0.000762 (item-level: 7.21e-53); certified at delta = 0.05: True.

## SCoRE comparator (send or abstain only)

SCoRE-SDR (score-select 0.1.1) with the same P(unsafe) scores, alpha = gamma = 0.1, 'homo' boosting; guarantee: expected risk among sent answers <= alpha (not a high-probability bound). All 5,336 calibration answers against 3 random test subsamples of 500.

Answers sent 22.9%; wrong among sent 6.2%; useful 21.4%. It decides only send or abstain, so compare it with verified_only; repair is what lifts the other policies' useful coverage.

Run time: 44.1 s.
