"""Scoring metrics for parser evaluation.

Every metric is exposed both in raw form and as a normalized value in
[0, 1] where higher is better, so track scores can be aggregated uniformly.
"""

from parse_arena.metrics.text import cer, wer, levenshtein, normalized_similarity
from parse_arena.metrics.table import Cell, expand_grid, teds
from parse_arena.metrics.order import (
    kendall_tau,
    match_blocks,
    reading_order_tau,
    vertical_order_accuracy,
)
from parse_arena.metrics.fields import field_recall

__all__ = [
    "cer",
    "wer",
    "levenshtein",
    "normalized_similarity",
    "Cell",
    "expand_grid",
    "teds",
    "kendall_tau",
    "match_blocks",
    "reading_order_tau",
    "vertical_order_accuracy",
    "field_recall",
]
