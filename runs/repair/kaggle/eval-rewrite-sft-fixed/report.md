# Repair evaluation: rewrite repairer, Qwen/Qwen3.5-2B + /kaggle/input/notebooks/sharafthawfeek/faithguard-repair-baselines/outputs/rewrite-sft/adapter, tune track

500 items (411 with a wrong original). Run time 1171.3 s.

| Measure | Value |
| --- | --- |
| Correction rate (wrong originals made fully correct) | 51.8% |
| Withheld when a fix was needed | 28.5% |
| Still wrong when sent | 27.6% |
| New-error rate (sent repairs with a new wrong number) | 15.1% |
| Damage rate (correct originals made wrong) | 0.0% |
| Valid programs | 28.9% |
| Gate pass rate | 100.0% |
| Mean attempts | 1.0 |

| Planted error | Items | Correction | Withheld | New errors | Damage |
| --- | --- | --- | --- | --- | --- |
| basis | 26 | 7.7% | 0.0% | 26.9% | – |
| metric | 112 | 70.5% | 0.0% | 29.5% | – |
| missing_operand | 121 | 0.0% | 96.7% | 50.0% | – |
| none | 89 | – | – | 0.0% | 0.0% |
| period | 61 | 75.4% | 0.0% | 24.6% | – |
| scale | 28 | 100.0% | 0.0% | 0.0% | – |
| sign | 63 | 92.1% | 0.0% | 1.6% | – |
