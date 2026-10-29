# Transfer study: the v0 policy when the repairer changes

Alpha 0.1, delta 0.05. Items per split (v0, v1): {'fit': [1000, 1000], 'tune': [1000, 1000], 'calibration': [1000, 1000], 'test': [1000, 1000]}. See `faithguard.policy.transfer`.

| Arm | Setting | Sent | Wrong among sent | Useful | Within alpha |
| --- | --- | --- | --- | --- | --- |
| v0 policy on v0 test | send<0.005,fix>0.5 | 72.2% | 1.9% | 70.8% | yes |
| v0 policy on v1 test, as-is | send<0.005,fix>0.5 | 71.6% | 1.0% | 70.9% | yes |
| refitted on v1 | send<0.5,fix>0.5 | 72.9% | 1.0% | 72.2% | yes |

As-is risk on v1's test records: 1.0% [0.2%, 1.9%] (issuer-clustered 95% interval); unsafe as-is: no. P-H3: rejected: safe as-is.

## Recalibrated on v1 labels (v0's outcome models kept)

| v1 calibration labels | Draws | Certified | Restored (certified, within alpha) | Mean wrong among sent | Within alpha | Mean useful |
| --- | --- | --- | --- | --- | --- | --- |
| 100 | 50 | 48.0% | 48.0% | 0.9% | 100.0% | 69.3% |
| 200 | 50 | 100.0% | 100.0% | 1.0% | 100.0% | 70.5% |
| 1000 | 1 | 100.0% | 100.0% | 1.0% | 100.0% | 70.9% |
