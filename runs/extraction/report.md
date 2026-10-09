# Automatic-extraction run: three tools on 20 tables

Scores against the hand-corrected tables (counts only; see `faithguard.data.extraction`). *Figures found*: share of the corrected table's figures that come out in the matching row, in order. The project's own reader (`pdf_tables`) was built on these reports, so it is shown as a reference and is never a candidate.

| Tool | Strategy | Tables | Figures found | Wrong figures | Rows complete | Tables complete | Seconds | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| camelot | hybrid | 20 | 1350/2507 (53.8%) | 91 | 317/675 (47.0%) | 8 | 10 | 0 |
| camelot | lattice | 20 | 124/2507 (5.0%) | 154 | 1/675 (0.1%) | 0 | 10 | 0 |
| camelot | network | 20 | 1350/2507 (53.8%) | 92 | 317/675 (47.0%) | 8 | 5 | 0 |
| camelot | stream (best) | 20 | 2191/2507 (87.4%) | 32 | 558/675 (82.7%) | 11 | 4 | 0 |
| pdf_tables | project (best) | 20 | 2501/2507 (99.8%) | 0 | 674/675 (99.9%) | 19 | 1 | 0 |
| pdfplumber | lines | 20 | 307/2507 (12.2%) | 128 | 76/675 (11.3%) | 2 | 10 | 0 |
| pdfplumber | text (best) | 20 | 2066/2507 (82.4%) | 215 | 532/675 (78.8%) | 9 | 11 | 0 |
| pymupdf | lines | 20 | 1504/2507 (60.0%) | 53 | 359/675 (53.2%) | 5 | 4 | 0 |
| pymupdf | text (best) | 20 | 2256/2507 (90.0%) | 220 | 523/675 (77.5%) | 8 | 6 | 0 |

**Best tool:** pymupdf (text), the eligible tool with the most figures found (ties: more tables complete, then faster), a rule fixed before the run.

## Figures found per table, each tool at its best strategy

| Table | Pages | pymupdf | pdfplumber | camelot | pdf_tables |
| --- | --- | --- | --- | --- | --- |
| DIAL t1 | 208 | 98/100 | 98/100 | 98/100 | 100/100 |
| DIAL t2 | 206, 207 | 120/139 | 120/139 | 121/139 | 139/139 |
| DIPD t1 | 501 | 67/73 | 68/73 | 73/73 | 73/73 |
| DIPD t2 | 503 | 129/129 | 129/129 | 129/129 | 129/129 |
| HAYL t1 | 360 | 76/97 | 76/97 | 65/97 | 97/97 |
| HAYL t2 | 362, 363 | 173/173 | 173/173 | 173/173 | 173/173 |
| KVAL t1 | 286 | 77/80 | 77/80 | 80/80 | 80/80 |
| KVAL t2 | 288, 289 | 111/145 | 145/145 | 145/145 | 145/145 |
| NTB t1 | 152 | 122/122 | 122/122 | 86/122 | 122/122 |
| NTB t2 | 151 | 154/154 | 154/154 | 154/154 | 154/154 |
| PABC t1 | 226, 227 | 120/120 | 120/120 | 120/120 | 120/120 |
| PABC t2 | 228 | 69/104 | 69/104 | 104/104 | 104/104 |
| PLC t1 | 320 | 92/144 | 0/144 | 92/144 | 138/144 |
| PLC t2 | 322 | 133/199 | 0/199 | 133/199 | 199/199 |
| RCL t1 | 220, 221 | 76/78 | 76/78 | 78/78 | 78/78 |
| RCL t2 | 218, 219 | 140/140 | 140/140 | 118/140 | 140/140 |
| SLTL t1 | 207 | 100/104 | 100/104 | 56/104 | 104/104 |
| SLTL t2 | 208, 209 | 166/166 | 166/166 | 166/166 | 166/166 |
| WATA t1 | 145 | 95/102 | 95/102 | 62/102 | 102/102 |
| WATA t2 | 146 | 138/138 | 138/138 | 138/138 | 138/138 |
