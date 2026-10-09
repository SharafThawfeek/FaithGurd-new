# Thin end-to-end slice (rules only)

32 items: 6 hand-written on a fictional Sri Lankan bank, the rest injected into FinQA and TAT-QA development examples.
Every item runs the full pipeline: Channel B rule checker, threshold policy v0, rule-only repairer v0 with the hard gate.
These items were made by the project's own templates, so the numbers show the pipeline works end to end; they are not results.

- Expected action taken: 29 of 32
- Answers sent (original or fixed): 24 of 32; unsupported among them: 0
- Useful answers sent: 24 of 32

| # | Source | Planted error | Expected | Action | Outcome | Answer | Output or reason |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | synthetic | none | send | send | supported_useful | Group profit after tax rose 9.3% to Rs. 14,213 million in FY2025. | Group profit after tax rose 9.3% to Rs. 14,213 million in FY2025. |
| 2 | synthetic | entity | repair | repair | supported_useful | Group profit after tax rose 7.0% to Rs. 12,450 million. | Group profit after tax rose 9.3% to Rs. 14,213 million. |
| 3 | synthetic | scale | repair | repair | supported_useful | Group profit after tax was Rs. 14,212,560 million in FY2025. | Group profit after tax was Rs. 14,213 million in FY2025. |
| 4 | synthetic | period | repair | repair | supported_useful | Group profit after tax was Rs. 13,004 million in FY2025. | Group profit after tax was Rs. 14,213 million in FY2025. |
| 5 | synthetic | sign | repair | repair | supported_useful | Group profit after tax fell 9.3% in FY2025. | Group profit after tax rose 9.3% in FY2025. |
| 6 | synthetic | missing_operand | abstain | abstain | abstained | The Group's return on equity was 15.2% in FY2025. | ABSTAIN: the evidence lacks a value the answer needs |
| 7 | tatqa | basis | repair | repair | supported_useful | Inventories, net fell 3.0% from $43,486 thousand in 2018 to $42,237 thousand in 2019. | Inventories, net fell 2.9% from $43,486 thousand in 2018 to $42,237 thousand in 2019. |
| 8 | tatqa | basis | repair | repair | supported_useful | Raw material rose 14.0% from $191 thousand in 2018 to $222 thousand in 2019. | Raw material rose 16.2% from $191 thousand in 2018 to $222 thousand in 2019. |
| 9 | tatqa | metric | repair | repair | supported_useful | In 2018, Deferred compensation plan assets was $6.00 million. | In 2018, Deferred compensation plan assets was $31.00 million. |
| 10 | tatqa | metric | repair | repair | supported_useful | In 2019, Net decrease in cash and cash equivalents was 901.3 million. | In 2019, Net decrease in cash and cash equivalents was -472.7 million. |
| 11 | tatqa | missing_operand | abstain | abstain | abstained | Effective income tax rate was 18.3% in 2019. | ABSTAIN: no rule can confirm or fix this answer. The report shows: effective income tax rate 2018: 18.3% |
| 12 | tatqa | missing_operand | abstain | abstain | abstained | Current: Federal fell 66.9% from $1,294,253 in 2018 to $428,501 in 2019. | ABSTAIN: the evidence lacks a value the answer needs. The report shows: current state 2019: 428,501 |
| 13 | tatqa | none | send | send | supported_useful | In 2019, Carrying amount /assets) was -494 million. | In 2019, Carrying amount /assets) was -494 million. |
| 14 | tatqa | none | send | send | supported_useful | Adjusted EBITDA was 31.0%. | Adjusted EBITDA was 31.0%. |
| 15 | tatqa | period | repair | repair | supported_useful | United States fell 26.7% from $784,469 in 2018 to $575,264 in 2019. | United States rose 18.9% from $784,469 in 2018 to $933,054 in 2019. |
| 16 | tatqa | period | repair | repair | supported_useful | In 2017, Total other income, net was -$2,935 thousand. | In 2017, Total other income, net was $1,758 thousand. |
| 17 | tatqa | scale | repair | repair | supported_useful | Other was 8.10 billion in 2018. | Other was 0.008 billion in 2018. |
| 18 | tatqa | scale | repair | repair | supported_useful | Total EMEA was 294,954 million in 2018. | Total EMEA was 295 million in 2018. |
| 19 | tatqa | sign | repair | repair | supported_useful | Basic increased by $1.32 from $1.75 in 2017 to $0.430 in 2018. | Basic decreased by $1.32 from $1.75 in 2017 to $0.430 in 2018. |
| 20 | tatqa | sign | repair | repair | supported_useful | Software delivery, support and maintenance increased by $1,508 thousand from $10,949 thousand in 2017 to $9,441 thousand in 2018. | Software delivery, support and maintenance decreased by $1,508 thousand from $10,949 thousand in 2017 to $9,441 thousand in 2018. |
| 21 | finqa | basis | repair | repair | supported_useful | Lkq corporation rose 51.0% from $100 in 2011 to $204 in 2016. | Lkq corporation rose 104.0% from $100 in 2011 to $204 in 2016. |
| 22 | finqa | basis | repair | repair | supported_useful | Commodities net was 47.0% in 2017, down 55.3% from 73.0% in 2016. | Commodities net was 47.0% in 2017, down 35.6% from 73.0% in 2016. |
| 23 | finqa | metric | repair | repair | supported_useful | Inventories net increased by $126.7 million from $257.6 million in 2002 to $384.3 million in 2003. | Inventories net increased by $270.1 million from $257.6 million in 2002 to $527.7 million in 2003. |
| 24 | finqa | metric | repair | abstain | abstained | Total africa was 2.0% of total in 2017. | ABSTAIN: no rule can confirm or fix this answer. The report shows: u s 2017: $89.0 thousand; other africa 2017: $4,352 thousand |
| 25 | finqa | missing_operand | abstain | abstain | abstained | Raw materials and supplies rose 102.1% from $488.8 in 2017 to $988.1 in 2018. | ABSTAIN: the evidence lacks a value the answer needs. The report shows: finished products 2018: $988 |
| 26 | finqa | missing_operand | abstain | abstain | abstained | Cabinets fell 9.4% from $2,397.8 million in 2016 to $2,173.4 million in 2017. | ABSTAIN: no rule can confirm or fix this answer. The report shows: cabinets 2016: $2,398 million; cabinets 2015: $2,173 million; cabinets 2015: $2,173 million |
| 27 | finqa | none | send | send | supported_useful | Total was $412 million in 2017, down 42.5% from $716 million in 2016. | Total was $412 million in 2017, down 42.5% from $716 million in 2016. |
| 28 | finqa | none | send | send | supported_useful | Other revenues was 4.7% of total in 2008. | Other revenues was 4.7% of total in 2008. |
| 29 | finqa | period | repair | abstain | abstained | Total africa was 4.2% of total in 2017. | ABSTAIN: no rule can confirm or fix this answer. The report shows: e g 2018: $36.0 thousand; other africa 2018: $854 thousand |
| 30 | finqa | period | repair | abstain | abstained | Risk solutions was 56.9% of total revenue in 2011. | ABSTAIN: the evidence lacks a value the answer needs |
| 31 | finqa | sign | repair | repair | supported_useful | Total redeemable stock of subsidiaries decreased by $244 million from $538 million in 2015 to $782 million in 2016. | Total redeemable stock of subsidiaries increased by $244 million from $538 million in 2015 to $782 million in 2016. |
| 32 | finqa | sign | repair | repair | supported_useful | Finished goods decreased by $177.6 million from $206.7 million in 2002 to $384.3 million in 2003. | Finished goods increased by $177.6 million from $206.7 million in 2002 to $384.3 million in 2003. |
