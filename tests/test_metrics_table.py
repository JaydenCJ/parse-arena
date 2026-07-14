"""Tests for the simplified TEDS table similarity."""

from parse_arena.metrics.table import Cell, expand_grid, teds, teds_single

GT = [
    ["Service", "Track", "Score"],
    ["Alpha", "en-text", "0.91"],
    ["Beta", "ja-vertical", "0.84"],
]


class TestTedsSingle:
    def test_identical_tables(self):
        assert teds_single(GT, GT) == 1.0

    def test_both_empty(self):
        assert teds_single([], []) == 1.0

    def test_one_empty(self):
        assert teds_single([], GT) == 0.0
        assert teds_single(GT, []) == 0.0

    def test_missing_row_penalized(self):
        pred = GT[:2]
        score = teds_single(pred, GT)
        assert 0.0 < score < 1.0
        # two of three rows survive perfectly
        assert abs(score - 2 / 3) < 1e-9

    def test_extra_row_penalized(self):
        pred = GT + [["Hallucinated", "row", "1.00"]]
        assert teds_single(pred, GT) < 1.0

    def test_cell_typo_partial_credit(self):
        pred = [row[:] for row in GT]
        pred[1][0] = "Alphx"  # one character off
        score = teds_single(pred, GT)
        assert 0.9 < score < 1.0

    def test_completely_different_content(self):
        pred = [["x", "y", "z"], ["1", "2", "3"], ["4", "5", "6"]]
        assert teds_single(pred, GT) < 0.4

    def test_column_shift_detected(self):
        # Same cells but shifted one column: classic column-drift failure.
        pred = [["", "Service", "Track"], ["", "Alpha", "en-text"], ["", "Beta", "ja-vertical"]]
        assert teds_single(pred, GT) < teds_single(GT, GT)

    def test_whitespace_in_cells_normalized(self):
        pred = [[" Service ", "Track", "Score"], GT[1], GT[2]]
        assert teds_single(pred, GT) == 1.0


MERGED = [
    [Cell("Team", rowspan=2), Cell("2026 H1", colspan=2), Cell("2026 H2", colspan=2)],
    ["Q1", "Q2", "Q3", "Q4"],
    ["Alpha", "10", "12", "14", "16"],
]

MERGED_EXPANDED = [
    ["Team", "2026 H1", "2026 H1", "2026 H2", "2026 H2"],
    ["Team", "Q1", "Q2", "Q3", "Q4"],
    ["Alpha", "10", "12", "14", "16"],
]


class TestSpanExpansion:
    def test_plain_grid_passes_through(self):
        assert expand_grid(GT) == [list(r) for r in GT]

    def test_colspan_and_rowspan_expand_onto_grid(self):
        assert expand_grid(MERGED) == MERGED_EXPANDED

    def test_rowspan_in_data_rows(self):
        table = [
            ["Room", "Slot"],
            [Cell("Aoi", rowspan=2), "Standup"],
            ["Review"],
        ]
        assert expand_grid(table) == [
            ["Room", "Slot"],
            ["Aoi", "Standup"],
            ["Aoi", "Review"],
        ]

    def test_merged_gt_matches_span_aware_prediction(self):
        assert teds_single(MERGED, MERGED) == 1.0

    def test_expanded_grid_prediction_gets_full_credit(self):
        # A parser without a span representation may repeat the merged text
        # across the covered grid positions; that is the same logical grid.
        assert teds_single(MERGED_EXPANDED, MERGED) == 1.0

    def test_collapsed_merge_is_penalized(self):
        # Classic failure: the parser flattens the merged header, losing the
        # column alignment of the spanned cells.
        collapsed = [
            ["Team", "2026 H1", "2026 H2"],
            ["Q1", "Q2", "Q3", "Q4"],
            ["Alpha", "10", "12", "14", "16"],
        ]
        assert teds_single(collapsed, MERGED) < 1.0

    def test_empty_row_expands_to_empty(self):
        assert expand_grid([[]]) == [[]]


class TestTedsMultiTable:
    def test_both_empty(self):
        assert teds([], []) == 1.0

    def test_missing_all_tables(self):
        assert teds([], [GT]) == 0.0

    def test_hallucinated_table_penalized(self):
        assert teds([GT, [["extra"]]], [GT]) == 0.5

    def test_best_match_pairing(self):
        other = [["totally", "different"], ["rows", "here"]]
        # order of predicted tables must not matter
        assert teds([other, GT], [GT, other]) == 1.0
