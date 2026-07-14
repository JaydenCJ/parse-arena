"""Tests for reading-order metrics (Kendall tau, vertical accuracy)."""

from parse_arena.metrics import (
    field_recall,
    kendall_tau,
    reading_order_tau,
    vertical_order_accuracy,
)

BLOCKS = [
    "First paragraph about benchmarks.",
    "Second paragraph about datasets.",
    "Third paragraph about metrics.",
    "Fourth paragraph about routers.",
]


class TestKendallTau:
    def test_identity_permutation(self):
        assert kendall_tau([0, 1, 2, 3]) == 1.0

    def test_reversed_permutation(self):
        assert kendall_tau([3, 2, 1, 0]) == -1.0

    def test_single_swap(self):
        # 5 concordant, 1 discordant out of 6 pairs
        assert abs(kendall_tau([1, 0, 2, 3]) - (4 / 6)) < 1e-9

    def test_single_item_trivially_ordered(self):
        assert kendall_tau([0]) == 1.0

    def test_empty_trivially_ordered(self):
        assert kendall_tau([]) == 1.0


class TestReadingOrderTau:
    def test_perfect_order(self):
        assert reading_order_tau(BLOCKS, BLOCKS) == 1.0

    def test_reversed_order(self):
        assert reading_order_tau(list(reversed(BLOCKS)), BLOCKS) == -1.0

    def test_missing_block_reduces_coverage(self):
        pred = BLOCKS[:3]
        score = reading_order_tau(pred, BLOCKS)
        assert abs(score - 0.75) < 1e-9  # tau 1.0 * coverage 3/4

    def test_nothing_recognizable(self):
        assert reading_order_tau(["zzz completely unrelated"], BLOCKS) == -1.0

    def test_empty_ground_truth(self):
        assert reading_order_tau([], []) == 1.0
        assert reading_order_tau(["spurious"], []) == 0.0

    def test_near_duplicate_blocks_still_match(self):
        pred = [b.replace("paragraph", "paragrph") for b in BLOCKS]
        assert reading_order_tau(pred, BLOCKS) == 1.0


class TestVerticalOrderAccuracy:
    COLUMNS = ["春はあけぼの。", "夏は夜。月のころはさらなり。", "秋は夕暮れ。", "冬はつとめて。"]

    def test_correct_right_to_left(self):
        assert vertical_order_accuracy(self.COLUMNS, self.COLUMNS) == 1.0

    def test_left_to_right_scan_is_zero(self):
        # A parser scanning columns left-to-right reverses every pair.
        assert vertical_order_accuracy(list(reversed(self.COLUMNS)), self.COLUMNS) == 0.0

    def test_partial_disorder(self):
        pred = [self.COLUMNS[1], self.COLUMNS[0], self.COLUMNS[2], self.COLUMNS[3]]
        assert abs(vertical_order_accuracy(pred, self.COLUMNS) - 5 / 6) < 1e-9

    def test_missing_column_pairs_count_as_wrong(self):
        pred = self.COLUMNS[:2]
        # pairs among the two matched columns are correct: 1 of 6
        assert abs(vertical_order_accuracy(pred, self.COLUMNS) - 1 / 6) < 1e-9

    def test_single_block_edge(self):
        assert vertical_order_accuracy(["一つ"], ["一つ"]) == 1.0
        assert vertical_order_accuracy([], ["一つ"]) == 0.0

    def test_empty_ground_truth(self):
        assert vertical_order_accuracy([], []) == 1.0


class TestFieldRecall:
    FIELDS = {"store": "アリーナマート 神田店", "total": "1,014", "date": "2026年6月28日"}

    def test_all_fields_present(self):
        text = "アリーナマート 神田店\n2026年6月28日 18:42\n合計 1,014円"
        assert field_recall(text, self.FIELDS) == 1.0

    def test_width_and_separator_insensitive(self):
        # full-width digits and missing comma must still match
        text = "アリーナマート神田店 ２０２６年６月２８日 合計 1014"
        assert field_recall(text, self.FIELDS) == 1.0

    def test_partial_recall(self):
        text = "アリーナマート 神田店"
        assert abs(field_recall(text, self.FIELDS) - 1 / 3) < 1e-9

    def test_empty_fields_is_perfect(self):
        assert field_recall("anything", {}) == 1.0

    def test_garbled_total_fails(self):
        text = "アリーナマート 神田店 2026年6月28日 合計 1,914円"
        assert abs(field_recall(text, self.FIELDS) - 2 / 3) < 1e-9
