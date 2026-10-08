# Thin end-to-end slice (rules only)

32 items: 6 hand-written on a fictional Sri Lankan bank, the rest injected into FinQA and TAT-QA development examples.
Every item runs the full pipeline: Channel B rule checker, threshold policy v0, rule-only repairer v0 with the hard gate.
These items were made by the project's own templates, so the numbers show the pipeline works end to end; they are not results.

- Expected action taken: 29 of 32
- Answers sent (original or fixed): 24 of 32; unsupported among them: 1
- Useful answers sent: 23 of 32

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
| 19 | tatqa | sign | repair | repair | supported_useful | Basic increased by $1.32 million from $1.75 million in 2017 to $0.430 million in 2018. | Basic decreased by $1.32 million from $1.75 million in 2017 to $0.430 million in 2018. |
| 20 | tatqa | sign | repair | repair | supported_useful | Software delivery, support and maintenance increased by $1,508 thousand from $10,949 thousand in 2017 to $9,441 thousand in 2018. | Software delivery, support and maintenance decreased by $1,508 thousand from $10,949 thousand in 2017 to $9,441 thousand in 2018. |
| 21 | finqa | basis | repair | repair | supported_useful | Net earnings for basic and diluted eps fell 15.4% from $6,948 in 2016 to $6,021 in 2017. | Net earnings for basic and diluted eps fell 13.3% from $6,948 in 2016 to $6,021 in 2017. |
| 22 | finqa | basis | repair | repair | supported_useful | Commodities net was 47.0% in 2017, down 55.3% from 73.0% in 2016. | Commodities net was 47.0% in 2017, down 35.6% from 73.0% in 2016. |
| 23 | finqa | metric | repair | abstain | abstained | Other revenues was 95.3% of total in 2008. | ABSTAIN: no rule can confirm or fix this answer. The report shows: freight revenues 2008: $17,118 million; total 2008: $17,970 million |
| 24 | finqa | metric | repair | abstain | abstained | Operating profit was 185.0% of net sales in 2014. | ABSTAIN: the evidence lacks a value the answer needs |
| 25 | finqa | missing_operand | abstain | abstain | abstained | Interest cost was 44.9% of service cost in 2018. | ABSTAIN: the evidence lacks a value the answer needs |
| 26 | finqa | missing_operand | abstain | abstain | abstained | Credit net fell 98.1% from 2,504.0% in 2016 to 47.0% in 2017. | ABSTAIN: the evidence lacks a value the answer needs. The report shows: commodities net 2017: 47.0% |
| 27 | finqa | none | send | send | supported_useful | Total long-term debt net changed from $6,142 million in 2014 to $15,261 million in 2015, a change of $9,119 million. | Total long-term debt net changed from $6,142 million in 2014 to $15,261 million in 2015, a change of $9,119 million. |
| 28 | finqa | none | send | send | supported_useful | Ending balance rose 13.4% from $172,945 thousand in 2017 to $196,152 thousand in 2018. | Ending balance rose 13.4% from $172,945 thousand in 2017 to $196,152 thousand in 2018. |
| 29 | finqa | period | repair | repair | unsupported | Henry hub natural gas rose 31.8% from $6.86 in 2007 to $9.04 in 2009. | Henry hub natural gas fell 41.8% from $6.86 in 2007 to $9.04 in 2009. |
| 30 | finqa | period | repair | abstain | abstained | Agricultural was 16.6% of total freight revenues in 2012. | ABSTAIN: the evidence lacks a value the answer needs |
| 31 | finqa | sign | repair | repair | supported_useful | Total redeemable stock of subsidiaries decreased by $244 million from $538 million in 2015 to $782 million in 2016. | Total redeemable stock of subsidiaries increased by $244 million from $538 million in 2015 to $782 million in 2016. |
| 32 | finqa | sign | repair | repair | supported_useful | Fair value of forward exchange contracts asset rose 65.9% from $7,256 in 2010 to $2,472 in 2011. | Fair value of forward exchange contracts asset fell 65.9% from $7,256 in 2010 to $2,472 in 2011. |
