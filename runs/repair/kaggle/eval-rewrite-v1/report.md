# Repair evaluation: rewrite repairer, Qwen/Qwen3.5-2B + /kaggle/working/outputs/rewrite-v1/adapter, tune track

500 items (411 with a wrong original). Run time 1449.4 s.

| Measure | Value |
| --- | --- |
| Correction rate (wrong originals made fully correct) | 53.0% |
| Withheld when a fix was needed | 28.5% |
| Still wrong when sent | 25.9% |
| New-error rate (sent repairs with a new wrong number) | 17.0% |
| Damage rate (correct originals made wrong) | 0.0% |
| Valid programs | 28.9% |
| Gate pass rate | 100.0% |
| Mean attempts | 1.0 |

| Planted error | Items | Correction | Withheld | New errors | Damage |
| --- | --- | --- | --- | --- | --- |
| basis | 26 | 15.4% | 0.0% | 69.2% | – |
| metric | 112 | 72.3% | 0.0% | 26.8% | – |
| missing_operand | 121 | 0.0% | 95.9% | 60.0% | – |
| none | 89 | – | – | 0.0% | 0.0% |
| period | 61 | 75.4% | 1.6% | 23.3% | – |
| scale | 28 | 100.0% | 0.0% | 0.0% | – |
| sign | 63 | 93.7% | 0.0% | 0.0% | – |
