"""Simplified TEDS: table structure + cell-content similarity.

The original TEDS (Tree-Edit-Distance-based Similarity, Zhong et al. 2020)
computes a tree edit distance over the full HTML table tree. parse-arena
compares tables as logical grids instead, in two steps:

Step 0 (span expansion): cells may carry colspan/rowspan (merged cells).
Both sides are first expanded into a full logical grid where a spanning
cell's text occupies every grid position it covers — the same convention
grid-based table benchmarks (e.g. PubTabNet's grid evaluation) use. A parser
that reports the merge (or equivalently repeats the value across the covered
positions) gets full credit; one that collapses or drops the spanned
positions loses exactly the affected cells.

Steps 1-3 (grid similarity):

1. cell similarity   = 1 - levenshtein(pred, gt) / max(len)          (leaf level)
2. row similarity    = sequence alignment of cells, substitution cost
                       1 - cell_similarity, insert/delete cost 1
3. table similarity  = sequence alignment of rows, substitution cost
                       1 - row_similarity, insert/delete cost 1,
                       normalized by max(row counts)

This preserves what TEDS rewards (correct row/column structure AND correct
cell content, with partial credit for near-miss cells) without requiring an
HTML tree. The formula is documented in the README so results are auditable.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Sequence

from parse_arena.metrics.text import normalized_similarity


@dataclass(frozen=True)
class Cell:
    """One table cell with optional row/column spans (merged cells)."""

    text: str
    colspan: int = 1
    rowspan: int = 1


# A table is rows of cells; a cell is either a plain string (span 1x1) or a
# Cell carrying explicit colspan/rowspan.
Table = Sequence[Sequence["str | Cell"]]


def expand_grid(table: Table) -> list[list[str]]:
    """Expand span-carrying cells into a full logical grid of strings.

    A cell with colspan=c and rowspan=r contributes its text to all c*r grid
    positions it covers; later cells in the same source row are shifted right
    past positions already claimed by earlier row spans. Plain string grids
    pass through unchanged (modulo str() coercion).
    """
    grid: list[list[str]] = []
    # pending rowspan carry-overs: (column, remaining_rows, text)
    carry: list[tuple[int, int, str]] = []
    for row in table:
        current: dict[int, str] = {}
        next_carry: list[tuple[int, int, str]] = []
        for col, remaining, text in carry:
            current[col] = text
            if remaining > 1:
                next_carry.append((col, remaining - 1, text))
        col = 0
        for cell in row:
            if isinstance(cell, Cell):
                text, colspan, rowspan = cell.text, cell.colspan, cell.rowspan
            else:
                text, colspan, rowspan = str(cell), 1, 1
            while col in current:
                col += 1
            for offset in range(colspan):
                current[col + offset] = text
                if rowspan > 1:
                    next_carry.append((col + offset, rowspan - 1, text))
            col += colspan
        carry = sorted(next_carry)
        if current:
            width = max(current) + 1
            grid.append([current.get(i, "") for i in range(width)])
        else:
            grid.append([])
    return grid


def _seq_edit_cost(a: Sequence, b: Sequence, sub_cost) -> float:
    """Generic edit distance with custom substitution cost in [0, 1]."""
    if not a:
        return float(len(b))
    if not b:
        return float(len(a))
    previous = [float(j) for j in range(len(b) + 1)]
    for i, item_a in enumerate(a, start=1):
        current = [float(i)]
        for j, item_b in enumerate(b, start=1):
            current.append(
                min(
                    previous[j] + 1.0,
                    current[j - 1] + 1.0,
                    previous[j - 1] + sub_cost(item_a, item_b),
                )
            )
        previous = current
    return previous[-1]


def _cell_cost(a: str, b: str) -> float:
    return 1.0 - normalized_similarity(_norm_cell(a), _norm_cell(b))


def _row_similarity(pred_row: Sequence[str], gt_row: Sequence[str]) -> float:
    if not pred_row and not gt_row:
        return 1.0
    width = max(len(pred_row), len(gt_row))
    cost = _seq_edit_cost(list(pred_row), list(gt_row), _cell_cost)
    return max(0.0, 1.0 - cost / width)


def _row_cost(pred_row: Sequence[str], gt_row: Sequence[str]) -> float:
    return 1.0 - _row_similarity(pred_row, gt_row)


def _norm_cell(cell: str) -> str:
    return " ".join(str(cell).split())


def teds_single(pred: Table, gt: Table) -> float:
    """Similarity in [0, 1] between one predicted and one ground-truth table.

    Both tables are span-expanded first (see expand_grid), so merged cells
    are compared on the logical grid. Edge cases: both empty -> 1.0; exactly
    one empty -> 0.0.
    """
    pred_rows = expand_grid(pred)
    gt_rows = expand_grid(gt)
    if not pred_rows and not gt_rows:
        return 1.0
    if not pred_rows or not gt_rows:
        return 0.0
    height = max(len(pred_rows), len(gt_rows))
    cost = _seq_edit_cost(pred_rows, gt_rows, _row_cost)
    return max(0.0, 1.0 - cost / height)


def teds(pred_tables: Sequence[Table], gt_tables: Sequence[Table]) -> float:
    """Document-level TEDS across multiple tables.

    Each ground-truth table is greedily matched to its best remaining
    predicted table; the sum of matched similarities is normalized by
    max(#gt, #pred) so both missing and hallucinated tables are penalized.
    Both sides empty -> 1.0.
    """
    if not pred_tables and not gt_tables:
        return 1.0
    if not pred_tables or not gt_tables:
        return 0.0
    remaining = list(range(len(pred_tables)))
    total = 0.0
    for gt_table in gt_tables:
        if not remaining:
            break
        best_idx, best_sim = remaining[0], -1.0
        for idx in remaining:
            sim = teds_single(pred_tables[idx], gt_table)
            if sim > best_sim:
                best_idx, best_sim = idx, sim
        remaining.remove(best_idx)
        total += best_sim
    return total / max(len(pred_tables), len(gt_tables))
