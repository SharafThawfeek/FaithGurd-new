# Phase 7: the pre-registered analyses on the main benchmark

Test split; intervals are issuer-clustered bootstrap 95% (2,000 resamples). Labels: code labels with an audit (D-100) and Claude's labelling passes (D-103). See `faithguard.evaluate.analysis`.

## Hypotheses

| Hypothesis | Estimate [95% interval] | Verdict |
| --- | --- | --- |
| D-H1 XBRL negatives raise wrong-context recall (difference) | 25.0% [0.0%, 100.0%] | untestable (fewer than 20 wrong-context test answers) |
| D-H2 A + B beats B on Sri Lanka (span F1 difference) | 0.024 [-0.059, 0.146] | no difference |
| D-H3 US threshold on Sri Lanka (risk as-is; restored with 100 labels 0.0%; curve 100: 0.0%, 200: 0.0%, all: 0.0%) | - | untestable (no US threshold certified) |
| R-H1 programs make fewer new errors (difference; correction 28.9% [16.5%, 43.7%]) | -10.6% [-13.7%, -7.7%] | confirmed |
| R-H2 self-training helps out of distribution (basis 0.0% [0.0%, 0.0%]) | Gemma 18.2% [4.7%, 31.0%] | not confirmed |
| R-H3 KEEP training cuts damage (difference) | 0.4% [-0.9%, 1.8%] | no difference |
| P-H1 outcome-aware beats the detector threshold (useful coverage difference) | 0.0% [0.0%, 0.0%] | outcome-aware policy not certified |
| P-H2 alpha = 0.10 certifiable at useful coverage | - | not confirmed |
| P-H3 v0 policy on v1 | - | untestable (the v0 policy is not certifiable) |

P-H1 secondary (D-102): against the threshold policy at its most cautious uncertified setting (risk<0.25), useful coverage difference -51.5% [-55.7%, -47.2%].

P-H2: not certified with every calibration answer; at the rates seen the first setting of the fixed sequence cannot certify at any label count tried.

## Detectors on the test split

Threshold set to flag 10% of the clean calibration answers (the share it does flag is shown: tied scores can make it less).

| Detector | AUROC | Calibration false alarms | Test false alarms | Recall | Wrong-context recall |
| --- | --- | --- | --- | --- | --- |
| channel-a | 0.579 [0.532, 0.624] | 9.9% | 11.8% [6.9%, 18.1%] | 8.1% [2.7%, 14.0%] | 25.0% [0.0%, 100.0%] |
| channel-a-noxbrl | 0.592 [0.543, 0.645] | 9.9% | 6.6% [3.7%, 10.0%] | 4.7% [0.0%, 9.8%] | 0.0% [0.0%, 0.0%] |
| channel-a-noslot | 0.614 [0.557, 0.672] | 9.9% | 13.8% [7.5%, 20.5%] | 12.8% [6.2%, 19.8%] | 25.0% [0.0%, 100.0%] |
| channel-b | 0.803 [0.764, 0.838] | 0.0% | 0.0% [0.0%, 0.0%] | 0.0% [0.0%, 0.0%] | 0.0% [0.0%, 0.0%] |
| fused-a+b | 0.849 [0.804, 0.895] | 2.3% | 3.0% [1.2%, 4.9%] | 62.8% [51.1%, 75.3%] | 0.0% [0.0%, 0.0%] |
| lettuce-v1 | 0.641 [0.565, 0.713] | 9.9% | 5.9% [3.3%, 8.3%] | 4.7% [1.2%, 8.9%] | 0.0% [0.0%, 0.0%] |
| lettuce-v2 | 0.688 [0.607, 0.762] | 9.9% | 6.9% [3.4%, 10.8%] | 14.0% [7.6%, 20.5%] | 0.0% [0.0%, 0.0%] |
| hhem | 0.609 [0.565, 0.662] | 9.9% | 5.9% [3.5%, 8.7%] | 5.8% [1.1%, 12.3%] | 0.0% [0.0%, 0.0%] |
| granite | 0.610 [0.556, 0.659] | 0.0% | 0.0% [0.0%, 0.0%] | 0.0% [0.0%, 0.0%] | 0.0% [0.0%, 0.0%] |

| AUROC difference | Estimate [95% interval] |
| --- | --- |
| fused-a+b minus channel-a | 0.270 [0.207, 0.336] |
| fused-a+b minus channel-a-noxbrl | 0.257 [0.180, 0.332] |
| fused-a+b minus channel-a-noslot | 0.235 [0.161, 0.312] |
| fused-a+b minus channel-b | 0.047 [0.013, 0.079] |
| fused-a+b minus lettuce-v1 | 0.208 [0.126, 0.282] |
| fused-a+b minus lettuce-v2 | 0.161 [0.096, 0.231] |
| fused-a+b minus hhem | 0.240 [0.187, 0.290] |
| fused-a+b minus granite | 0.239 [0.175, 0.309] |
| channel-a minus channel-a-noslot | -0.035 [-0.081, 0.008] |

## Spans on the test split (character overlap; ambiguous answers left out)

| Detector | Span F1 | Slot accuracy | Recall: basis | Recall: entity_scope | Recall: metric | Recall: none | Recall: period | Recall: scale_currency | Recall: sign | Recall: value |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| channel-b | 0.234 [0.150, 0.343] | - | 50.0% [22.2%, 100.0%] | 0.0% [0.0%, 0.0%] | 0.0% [0.0%, 0.0%] | 0.1% [0.0%, 0.5%] | 0.0% [0.0%, 0.0%] | 65.6% [40.6%, 92.0%] | 0.0% [0.0%, 0.0%] | 77.3% [66.8%, 89.4%] |
| fused-a+b | 0.245 [0.141, 0.411] | - | 14.3% [0.0%, 22.2%] | 0.0% [0.0%, 0.0%] | 0.0% [0.0%, 0.0%] | 0.0% [0.0%, 0.0%] | 0.0% [0.0%, 0.0%] | 0.0% [0.0%, 0.0%] | 0.0% [0.0%, 0.0%] | 69.9% [59.4%, 81.7%] |
| channel-a | 0.126 [0.082, 0.179] | 3.4% [0.0%, 8.7%] | 50.0% [22.2%, 100.0%] | 87.5% [79.2%, 95.8%] | 0.0% [0.0%, 0.0%] | 0.0% [0.0%, 0.0%] | 0.0% [0.0%, 0.0%] | 9.3% [0.0%, 23.9%] | 0.0% [0.0%, 0.0%] | 58.5% [50.2%, 69.5%] |
| channel-a-noslot | 0.145 [0.095, 0.210] | - | 50.0% [22.2%, 100.0%] | 12.5% [0.0%, 25.0%] | 56.0% [56.0%, 56.0%] | 0.0% [0.0%, 0.0%] | 0.0% [0.0%, 0.0%] | 28.4% [0.0%, 69.6%] | 0.0% [0.0%, 0.0%] | 63.2% [56.1%, 74.1%] |

Answers labelled ambiguous, left out of these metrics: 2 on test, 1 on calibration; test ones flagged at each detector's threshold: channel-a 0, channel-a-noxbrl 0, channel-a-noslot 0, channel-b 0, fused-a+b 0, lettuce-v1 0, lettuce-v2 0, hhem 1, granite 0.

Fused probabilities on test: per claim Brier 0.034 [0.023, 0.049], ECE 0.022 [0.012, 0.038]; per answer Brier 0.114 [0.091, 0.141], ECE 0.100 [0.085, 0.137].

Coverage at certified selective risk (fused risk, threshold certified on every calibration answer at alpha = 0.10): no threshold certified.

## Repair on the test split

| Repairer, spans | Wrong originals | Corrected | Withheld when needed | New errors | Damage |
| --- | --- | --- | --- | --- | --- |
| repair-sft, channel_a_spans | 83 | 31.3% | 38.6% | 0.8% | 0.8% |
| repair-sft, rule_spans | 83 | 28.9% | 56.6% | 0.4% | 0.0% |
| repair-sft-nokeep, channel_a_spans | 83 | 32.5% | 39.8% | 0.5% | 0.4% |
| repair-sft-nokeep, rule_spans | 83 | 39.8% | 38.6% | 0.8% | 2.4% |
| repair-v1, channel_a_spans | 83 | 41.0% | 28.9% | 0.4% | 0.0% |
| repair-v1, gold_spans | 83 | 49.4% | 33.7% | 0.3% | 0.0% |
| repair-v1, rule_spans | 83 | 50.6% | 34.9% | 0.4% | 0.0% |
| rewrite-v1, channel_a_spans | 83 | 20.5% | 0.0% | 24.0% | 20.0% |
| rewrite-v1, gold_spans | 83 | 20.5% | 0.0% | 10.9% | 0.0% |
| rewrite-v1, rule_spans | 83 | 20.5% | 0.0% | 15.4% | 6.3% |
| rule repairer, channel_a_spans | 83 | 26.5% | 44.6% | 4.9% | 2.8% |
| rule repairer, gold_spans | 83 | 43.4% | 42.2% | 1.0% | 0.0% |
| rule repairer, rule_spans | 83 | 50.6% | 22.9% | 6.2% | 6.3% |
| stage-b, channel_a_spans | 83 | 36.1% | 33.7% | 0.8% | 3.5% |
| stage-b, rule_spans | 83 | 43.4% | 42.2% | 0.8% | 0.4% |

Every changed repair of a group the check failed is labelled, and its label's state replaces the gold scorer's (D-112): repair-v1, channel_a_spans 35 changed, 3 scored differently; repair-v1, rule_spans 43 changed, 3 scored differently; repair-sft, channel_a_spans 29 changed, 3 scored differently; repair-sft, rule_spans 25 changed, 2 scored differently; repair-sft-nokeep, channel_a_spans 29 changed, 3 scored differently; repair-sft-nokeep, rule_spans 46 changed, 14 scored differently; stage-b, channel_a_spans 39 changed, 9 scored differently; stage-b, rule_spans 38 changed, 2 scored differently; rewrite-v1, channel_a_spans 137 changed, 8 scored differently; rewrite-v1, rule_spans 88 changed, 5 scored differently.
With the gold scorer's states instead: R-H2 basis 0.0% [0.0%, 0.0%], Gemma 18.2% [4.7%, 31.0%] (not confirmed); R-H3 0.4% [0.0%, 1.3%] (no difference).
The policy's natural records keep the gold scorer's states for repairer v1 on the rule checker's spans: the check labels test repairs only, and the policy is certified on calibration answers; on test the labels score 3 of its 43 changed repairs differently.

Scored by the gold scorer instead (D-112, sensitivity):

| Repairer, spans | Wrong originals | Corrected | Withheld when needed | New errors | Damage |
| --- | --- | --- | --- | --- | --- |
| repair-v1, channel_a_spans | 83 | 38.6% | 28.9% | 0.4% | 0.4% |
| repair-v1, rule_spans | 83 | 49.4% | 34.9% | 0.4% | 0.0% |
| repair-sft, channel_a_spans | 83 | 30.1% | 38.6% | 0.8% | 0.8% |
| repair-sft, rule_spans | 83 | 28.9% | 56.6% | 0.4% | 0.0% |
| repair-sft-nokeep, channel_a_spans | 83 | 31.3% | 39.8% | 0.5% | 0.4% |
| repair-sft-nokeep, rule_spans | 83 | 44.6% | 38.6% | 0.8% | 0.0% |
| stage-b, channel_a_spans | 83 | 34.9% | 33.7% | 0.8% | 0.4% |
| stage-b, rule_spans | 83 | 43.4% | 42.2% | 0.8% | 0.4% |
| rewrite-v1, channel_a_spans | 83 | 19.3% | 0.0% | 24.0% | 22.0% |
| rewrite-v1, rule_spans | 83 | 19.3% | 0.0% | 15.4% | 7.1% |

## Repair check (D-106)

| Group | Checked | Code and label disagree | Every changed repair labelled |
| --- | --- | --- | --- |
| other variants | 50 of 50 | 8 (16.0%) | yes |
| repair-v1, gold_spans | 43 of 43 | 3 (7.0%) | no |
| rewrite-v1, gold_spans | 50 of 50 | 3 (6.0%) | no |

## Information preserved (D-109)

| Group | Checked | Preserved |
| --- | --- | --- |
| other variants | 50 | 66.0% [51.9%, 81.5%] |
| repair-v1, gold_spans | 43 | 97.7% [92.5%, 100.0%] |
| rewrite-v1, gold_spans | 50 | 90.0% [81.6%, 97.4%] |

## Policies on the test split (certified on calibration, alpha = 0.10)

| Policy | Certified | Sent | Wrong among sent | Useful |
| --- | --- | --- | --- | --- |
| send_all | 0 of 1 | - | - | - |
| repair_all | 0 of 1 | - | - | - |
| verified_only | 0 of 3 | - | - | - |
| threshold_v0 | 0 of 3 | - | - | - |
| four_state | 0 of 6 | - | - | - |
| outcome_aware[lightgbm] | 0 of 56 | - | - | - |
| outcome_aware[neural] | 0 of 56 | - | - | - |

| Outcome model | Target | AUROC | Brier | ECE |
| --- | --- | --- | --- | --- |
| lightgbm | P(unsafe) | 0.807 | 0.317 | 0.329 |
| lightgbm | P(fix) | 0.624 | 0.244 | 0.229 |
| neural | P(unsafe) | 0.795 | 0.188 | 0.183 |
| neural | P(fix) | 0.394 | 0.360 | 0.356 |

SCoRE (send or abstain, expected-risk guarantee): sent 72.7%, wrong among sent 11.9%, useful 62.5%.

Certification budget (lightgbm): 100 answers certify in 0.0% of 50 draws; 200 answers certify in 0.0% of 50 draws; 396 answers certify in 0.0% of 1 draws.

Certification budget (neural): 100 answers certify in 0.0% of 50 draws; 200 answers certify in 2.0% of 50 draws; 396 answers certify in 0.0% of 1 draws.

Neural outcome model minus LightGBM, useful coverage on test: 0.0% [0.0%, 0.0%] (certified: neural no, LightGBM no; a model that certifies nothing withholds every answer).

Answers labelled ambiguous count as unsafe: 2 on test, 0 of them sent by the LightGBM policy.

## Generator shift: certified on Qwen calibration answers, reported on Gemma test answers

| Policy | Certified | Sent | Wrong among sent | Useful |
| --- | --- | --- | --- | --- |
| verified_only | 0 of 3 | - | - | - |
| outcome_aware[lightgbm] | 0 of 56 | - | - | - |
