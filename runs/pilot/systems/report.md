# Repair on the pilot's natural answers

Counts only. Original answers are judged by their labels where they exist, repairs by the gold scorer. Narrative questions are left out. See `faithguard.evaluate.systems`.

| Repairer, spans | Items | Wrong originals | Corrected | Withheld when needed | New errors | Damage | Gate pass |
| --- | --- | --- | --- | --- | --- | --- | --- |
| rule repairer, channel_a_spans | 104 | 23 | 21.7% | 69.6% | 0.0% | 0.0% | 85.7% |
| rule repairer, rule_spans | 104 | 23 | 43.5% | 39.1% | 0.0% | 0.0% | 100.0% |
| trained repairer, channel_a_spans | 104 | 23 | 26.1% | 47.8% | 1.4% | 0.0% | 50.8% |
| trained repairer, rule_spans | 104 | 23 | 21.7% | 60.9% | 0.0% | 0.0% | 22.2% |
