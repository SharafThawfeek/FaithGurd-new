# Repair evaluation: program repairer, Qwen/Qwen3.5-2B (zero-shot), tune track

500 items (411 with a wrong original). Run time 2078.4 s.

| Measure | Value |
| --- | --- |
| Correction rate (wrong originals made fully correct) | 8.0% |
| Withheld when a fix was needed | 90.3% |
| Still wrong when sent | 17.5% |
| New-error rate (sent repairs with a new wrong number) | 0.8% |
| Damage rate (correct originals made wrong) | 0.0% |
| Valid programs | 100.0% |
| Gate pass rate | 8.4% |
| Mean attempts | 1.946 |

| Planted error | Items | Correction | Withheld | New errors | Damage |
| --- | --- | --- | --- | --- | --- |
| basis | 26 | 26.9% | 73.1% | 0.0% | – |
| metric | 112 | 4.5% | 95.5% | 0.0% | – |
| missing_operand | 121 | 0.0% | 98.4% | 0.0% | – |
| none | 89 | – | – | 0.0% | 0.0% |
| period | 61 | 6.6% | 93.4% | 0.0% | – |
| scale | 28 | 17.9% | 82.1% | 0.0% | – |
| sign | 63 | 19.1% | 73.0% | 5.9% | – |
