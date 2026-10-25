# Repair evaluation: program repairer, Qwen/Qwen3.5-2B + /kaggle/working/outputs/repair-v1/adapter, tune track

500 items (411 with a wrong original). Run time 1524.8 s.

| Measure | Value |
| --- | --- |
| Correction rate (wrong originals made fully correct) | 65.7% |
| Withheld when a fix was needed | 32.4% |
| Still wrong when sent | 2.9% |
| New-error rate (sent repairs with a new wrong number) | 0.5% |
| Damage rate (correct originals made wrong) | 0.0% |
| Valid programs | 100.0% |
| Gate pass rate | 93.8% |
| Mean attempts | 1.044 |

| Planted error | Items | Correction | Withheld | New errors | Damage |
| --- | --- | --- | --- | --- | --- |
| basis | 26 | 100.0% | 0.0% | 0.0% | – |
| metric | 112 | 91.1% | 8.0% | 1.0% | – |
| missing_operand | 121 | 0.0% | 98.4% | 0.0% | – |
| none | 89 | – | – | 0.0% | 0.0% |
| period | 61 | 90.2% | 8.2% | 1.8% | – |
| scale | 28 | 100.0% | 0.0% | 0.0% | – |
| sign | 63 | 93.7% | 0.0% | 0.0% | – |
