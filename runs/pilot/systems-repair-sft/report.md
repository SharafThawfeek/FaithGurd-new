# Repair on the pilot's natural answers (repair-sft, gate of D-087)

Counts only. Original answers are judged by their labels where they exist, repairs by the gold scorer. Narrative questions are left out. See `faithguard.evaluate.systems`.

| Repairer, spans | Items | Wrong originals | Corrected | Withheld when needed | New errors | Damage | Gate pass |
| --- | --- | --- | --- | --- | --- | --- | --- |
| rule repairer, channel_a_spans | 104 | 23 | 21.7% | 69.6% | 0.0% | 0.0% | 85.7% |
| rule repairer, rule_spans | 104 | 23 | 43.5% | 39.1% | 0.0% | 0.0% | 100.0% |
| trained repairer, channel_a_spans | 104 | 23 | 39.1% | 34.8% | 1.3% | 0.0% | 60.0% |
| trained repairer, rule_spans | 104 | 23 | 34.8% | 47.8% | 0.0% | 0.0% | 30.6% |
