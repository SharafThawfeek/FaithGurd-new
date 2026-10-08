"""Evaluation: scoring against gold, policy metrics and the flip matrix. Reads the gold store."""

from faithguard.evaluate.metrics import flip_matrix, policy_metrics
from faithguard.evaluate.score import score_text

__all__ = ["flip_matrix", "policy_metrics", "score_text"]
