# A + B fusion on the controlled track

Per-claim logistic regression, isotonic calibration, item risk = P(any claim wrong); items split by hash: half fit, a quarter calibrate, a quarter evaluate. Template answers favour Channel B (risk R-20): a pipeline check, not a test of H2. See `faithguard.train.fusion_study`.

| Channel A variant | Features | Claim AUROC | Item AUROC | Brier | ECE | False alarms (clean, risk >= 0.5) | Recall (wrong) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| full | B only | 0.996 | 0.993 | 0.008 | 0.004 | 1.0% | 99.2% |
| full | A only | 0.988 | 0.920 | 0.085 | 0.041 | 49.5% | 96.8% |
| full | A + B | 0.999 | 0.995 | 0.007 | 0.006 | 1.0% | 99.2% |
| no-XBRL | B only | 0.996 | 0.993 | 0.008 | 0.004 | 1.0% | 99.2% |
| no-XBRL | A only | 0.988 | 0.923 | 0.085 | 0.038 | 56.2% | 100.0% |
| no-XBRL | A + B | 0.999 | 0.994 | 0.006 | 0.003 | 1.0% | 99.5% |
| no-slot | B only | 0.996 | 0.993 | 0.008 | 0.004 | 1.0% | 99.2% |
| no-slot | A only | 0.989 | 0.923 | 0.086 | 0.030 | 54.3% | 99.2% |
| no-slot | A + B | 0.999 | 0.995 | 0.007 | 0.004 | 1.0% | 99.2% |

Evaluated on 475 items (1037 claims); fitted on 2216 claims and calibrated on 1063.
