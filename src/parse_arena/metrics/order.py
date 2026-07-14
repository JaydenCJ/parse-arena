"""Reading-order metrics: Kendall tau and vertical-order accuracy."""

from __future__ import annotations

from collections.abc import Sequence

from parse_arena.metrics.text import normalized_similarity

# A predicted block must be at least this similar to a ground-truth block to
# count as a match; below this the block is treated as missing.
MATCH_THRESHOLD = 0.5


def kendall_tau(ranks: Sequence[int]) -> float:
    """Kendall tau over a permutation given as predicted ranks of the
    ground-truth sequence (position i holds the predicted position of ground
    truth item i).

    Returns a value in [-1, 1]: 1.0 for identical order, -1.0 for fully
    reversed order. Sequences with fewer than two items are trivially ordered
    and return 1.0 (documented edge case).
    """
    n = len(ranks)
    if n < 2:
        return 1.0
    concordant = 0
    discordant = 0
    for i in range(n):
        for j in range(i + 1, n):
            if ranks[i] < ranks[j]:
                concordant += 1
            elif ranks[i] > ranks[j]:
                discordant += 1
            # equal ranks (ties) count for neither side
    total = n * (n - 1) / 2
    return (concordant - discordant) / total


def match_blocks(pred_blocks: Sequence[str], gt_blocks: Sequence[str]) -> list[int | None]:
    """Greedy one-to-one matching of ground-truth blocks to predicted blocks.

    For each ground-truth block (in order) the most similar unused predicted
    block is selected; matches under MATCH_THRESHOLD are discarded. Returns,
    for each ground-truth block, the index of the matched predicted block or
    None when the block is missing from the prediction.
    """
    used: set[int] = set()
    assignment: list[int | None] = []
    for gt_block in gt_blocks:
        best_idx: int | None = None
        best_sim = MATCH_THRESHOLD
        for idx, pred_block in enumerate(pred_blocks):
            if idx in used:
                continue
            sim = normalized_similarity(_norm(pred_block), _norm(gt_block))
            if sim > best_sim:
                best_idx, best_sim = idx, sim
        if best_idx is not None:
            used.add(best_idx)
        assignment.append(best_idx)
    return assignment


def reading_order_tau(pred_blocks: Sequence[str], gt_blocks: Sequence[str]) -> float:
    """Kendall tau of the predicted reading order against the ground truth.

    Ground-truth blocks are matched to predicted blocks first (greedy,
    similarity-based); tau is computed over the matched subset. Unmatched
    ground-truth blocks reduce the score multiplicatively via coverage, so a
    parser cannot game the metric by emitting only one easy block:

        score = tau(matched) * (matched / total_gt_blocks)

    Empty ground truth -> 1.0 when the prediction is also empty, else 0.0.
    """
    if not gt_blocks:
        return 1.0 if not pred_blocks else 0.0
    assignment = match_blocks(pred_blocks, gt_blocks)
    matched = [a for a in assignment if a is not None]
    if len(matched) < 1:
        return -1.0  # nothing recognizable: floor of the tau scale
    coverage = len(matched) / len(gt_blocks)
    return kendall_tau(matched) * coverage


def vertical_order_accuracy(pred_blocks: Sequence[str], gt_blocks: Sequence[str]) -> float:
    """Japanese vertical-text reading-order accuracy in [0, 1].

    Vertical Japanese text is read top-to-bottom, columns right-to-left.
    Parsers that scan left-to-right output the columns in reverse order, so
    this metric checks pairwise order: the fraction of ground-truth block
    pairs (i, j), i < j, whose matched predicted positions preserve the order.
    Missing blocks count every pair they participate in as wrong.

    Edge cases: empty ground truth -> 1.0 for empty prediction, else 0.0;
    a single ground-truth block -> 1.0 when matched, 0.0 when missing.
    """
    if not gt_blocks:
        return 1.0 if not pred_blocks else 0.0
    assignment = match_blocks(pred_blocks, gt_blocks)
    n = len(gt_blocks)
    if n == 1:
        return 1.0 if assignment[0] is not None else 0.0
    total = n * (n - 1) / 2
    correct = 0
    for i in range(n):
        for j in range(i + 1, n):
            a, b = assignment[i], assignment[j]
            if a is not None and b is not None and a < b:
                correct += 1
    return correct / total


def _norm(text: str) -> str:
    return " ".join(text.split())
