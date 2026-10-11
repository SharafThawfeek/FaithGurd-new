# Transfer study: the v0 policy when the repairer changes

Alpha 0.1, delta 0.05. Items per split (v0, v1): {'fit': [1000, 1000], 'tune': [1000, 1000], 'calibration': [1000, 1000], 'test': [1000, 1000]}. See `faithguard.policy.transfer`.

| Arm | Setting | Sent | Wrong among sent | Useful | Within alpha |
| --- | --- | --- | --- | --- | --- |
| v0 policy on v0 test | send<0.005,fix>0.5 | 72.2% | 1.9% | 70.8% | yes |
| v0 policy on v1 test, as-is | send<0.005,fix>0.5 | 71.6% | 1.0% | 70.9% | yes |
| refitted on v1 | send<0.005,fix>0.5 | 73.2% | 1.0% | 72.5% | yes |

## Recalibrated on v1 labels (v0's outcome models kept)

| v1 calibration labels | Draws | Certified | Mean wrong among sent | Within alpha | Mean useful |
| --- | --- | --- | --- | --- | --- |
| 25 | 50 | 0.0% | - | - | - |
| 50 | 50 | 0.0% | - | - | - |
| 100 | 50 | 76.0% | 0.9% | 100.0% | 69.7% |
| 200 | 50 | 100.0% | 1.0% | 100.0% | 70.6% |
| 1000 | 1 | 100.0% | 1.0% | 100.0% | 70.9% |
