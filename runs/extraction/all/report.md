# Automatic extraction on all 48 test and calibration tables

Scores against the hand-corrected tables (counts only; see `faithguard.data.extraction`). *Figures found*: share of the corrected table's figures that come out in the matching row, in order. The project's own reader (`pdf_tables`) was built on these reports, so it is shown as a reference and is never a candidate.

| Tool | Strategy | Tables | Figures found | Wrong figures | Rows complete | Tables complete | Seconds | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| pdf_tables | project (best) | 48 | 5835/5861 (99.6%) | 5 | 1637/1642 (99.7%) | 45 | 1 | 0 |
| pymupdf | text (best) | 48 | 5518/5861 (94.2%) | 438 | 1440/1642 (87.7%) | 23 | 14 | 0 |

**Best tool:** pymupdf (text), the eligible tool with the most figures found (ties: more tables complete, then faster), a rule fixed before the run.

## Figures found per table, each tool at its best strategy

| Table | Pages | pymupdf | pdf_tables |
| --- | --- | --- | --- |
| CARG t1 | 199 | 102/106 | 106/106 |
| CARG t2 | 200, 201 | 134/134 | 134/134 |
| CCS t1 | 276 | 68/72 | 72/72 |
| CCS t2 | 278 | 139/139 | 139/139 |
| CINS t1 | 140 | 108/133 | 116/133 |
| CINS t2 | 139 | 99/118 | 118/118 |
| DFCC t1 | 306, 307 | 180/180 | 180/180 |
| DFCC t2 | 308, 309 | 143/150 | 150/150 |
| DIAL t1 | 208 | 98/100 | 100/100 |
| DIAL t2 | 206, 207 | 120/139 | 139/139 |
| DIPD t1 | 501 | 67/73 | 73/73 |
| DIPD t2 | 503 | 129/129 | 129/129 |
| DIST t1 | 88 | 107/109 | 109/109 |
| DIST t2 | 89 | 130/130 | 130/130 |
| GRAN t1 | 330 | 88/92 | 92/92 |
| GRAN t2 | 331 | 124/124 | 124/124 |
| HASU t1 | 337 | 200/211 | 211/211 |
| HASU t2 | 336 | 116/116 | 116/116 |
| HAYL t1 | 360 | 76/97 | 97/97 |
| HAYL t2 | 362, 363 | 173/173 | 173/173 |
| HHL t1 | 156 | 56/58 | 58/58 |
| HHL t2 | 158 | 129/129 | 129/129 |
| HNB t1 | 334, 335 | 183/183 | 183/183 |
| HNB t2 | 336, 337 | 155/155 | 155/155 |
| JKH t1 | 465, 466 | 124/127 | 127/127 |
| JKH t2 | 467 | 150/150 | 150/150 |
| KVAL t1 | 286 | 77/80 | 80/80 |
| KVAL t2 | 288, 289 | 111/145 | 145/145 |
| LION t1 | 138 | 92/92 | 92/92 |
| LION t2 | 136, 137 | 132/132 | 132/132 |
| LLUB t1 | 95, 96 | 37/39 | 39/39 |
| LLUB t2 | 94 | 46/46 | 46/46 |
| NTB t1 | 152 | 122/122 | 122/122 |
| NTB t2 | 151 | 154/154 | 154/154 |
| PABC t1 | 226, 227 | 120/120 | 120/120 |
| PABC t2 | 228 | 69/104 | 104/104 |
| PLC t1 | 320 | 92/144 | 138/144 |
| PLC t2 | 322 | 133/199 | 199/199 |
| RCL t1 | 220, 221 | 76/78 | 78/78 |
| RCL t2 | 218, 219 | 140/140 | 140/140 |
| SLTL t1 | 207 | 100/104 | 104/104 |
| SLTL t2 | 208, 209 | 166/166 | 166/166 |
| UAL t1 | 255, 256 | 102/107 | 104/107 |
| UAL t2 | 257 | 55/55 | 55/55 |
| VONE t1 | 272, 273 | 141/145 | 145/145 |
| VONE t2 | 270, 271 | 122/122 | 122/122 |
| WATA t1 | 145 | 95/102 | 102/102 |
| WATA t2 | 146 | 138/138 | 138/138 |
