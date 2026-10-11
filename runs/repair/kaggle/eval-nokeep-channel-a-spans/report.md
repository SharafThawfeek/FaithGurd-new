# Repair evaluation: program repairer, Qwen/Qwen3.5-2B + /kaggle/working/outputs/repair-sft-nokeep/adapter, Channel A spans at 0.5, tune track

500 items (411 with a wrong original). Run time 1805.5 s.

| Measure | Value |
| --- | --- |
| Correction rate (wrong originals made fully correct) | 63.3% |
| Withheld when a fix was needed | 35.3% |
| Still wrong when sent | 2.3% |
| New-error rate (sent repairs with a new wrong number) | 0.6% |
| Damage rate (correct originals made wrong) | 0.0% |
| Valid programs | 100.0% |
| Gate pass rate | 89.2% |
| Mean attempts | 1.08 |

| Planted error | Items | Correction | Withheld | New errors | Damage |
| --- | --- | --- | --- | --- | --- |
| basis | 26 | 100.0% | 0.0% | 0.0% | – |
| metric | 112 | 81.2% | 15.2% | 1.1% | – |
| missing_operand | 121 | 0.0% | 99.2% | 0.0% | – |
| none | 89 | – | – | 0.0% | 0.0% |
| period | 61 | 85.2% | 13.1% | 1.9% | – |
| scale | 28 | 100.0% | 0.0% | 0.0% | – |
| sign | 63 | 100.0% | 0.0% | 0.0% | – |
