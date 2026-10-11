# Repair evaluation: program repairer, server:http://127.0.0.1:8080 (unconstrained), tune track

500 items (411 with a wrong original). Run time 2176.5 s.

| Measure | Value |
| --- | --- |
| Correction rate (wrong originals made fully correct) | 44.5% |
| Withheld when a fix was needed | 52.8% |
| Still wrong when sent | 5.7% |
| New-error rate (sent repairs with a new wrong number) | 1.8% |
| Damage rate (correct originals made wrong) | 0.0% |
| Valid programs | 100.0% |
| Gate pass rate | 49.0% |
| Mean attempts | 1.526 |

| Planted error | Items | Correction | Withheld | New errors | Damage |
| --- | --- | --- | --- | --- | --- |
| basis | 26 | 57.7% | 38.5% | 6.2% | – |
| metric | 112 | 62.5% | 34.8% | 4.1% | – |
| missing_operand | 121 | 0.8% | 97.5% | 0.0% | – |
| none | 89 | – | – | 0.0% | 0.0% |
| period | 61 | 57.4% | 41.0% | 2.8% | – |
| scale | 28 | 82.1% | 17.9% | 0.0% | – |
| sign | 63 | 61.9% | 31.8% | 0.0% | – |
