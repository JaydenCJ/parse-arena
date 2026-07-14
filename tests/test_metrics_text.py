"""Tests for CER/WER and the underlying edit distance."""

from parse_arena.metrics import cer, levenshtein, normalized_similarity, wer


class TestLevenshtein:
    def test_identical(self):
        assert levenshtein("kitten", "kitten") == 0

    def test_classic_example(self):
        assert levenshtein("kitten", "sitting") == 3

    def test_empty_vs_nonempty(self):
        assert levenshtein("", "abc") == 3
        assert levenshtein("abc", "") == 3

    def test_both_empty(self):
        assert levenshtein("", "") == 0

    def test_works_on_word_lists(self):
        assert levenshtein(["a", "b", "c"], ["a", "x", "c"]) == 1


class TestCer:
    def test_perfect_match(self):
        assert cer("hello world", "hello world") == 0.0

    def test_known_value(self):
        # 1 substitution over 5 reference characters
        assert cer("abcde", "abxde") == 0.2

    def test_whitespace_normalized(self):
        assert cer("hello   world", "hello\nworld") == 0.0

    def test_empty_reference_empty_hypothesis(self):
        assert cer("", "") == 0.0

    def test_empty_reference_nonempty_hypothesis(self):
        assert cer("", "noise") == 1.0

    def test_clipped_at_one(self):
        assert cer("a", "completely different and much longer") == 1.0


class TestWer:
    def test_perfect_match(self):
        assert wer("the quick brown fox", "the quick brown fox") == 0.0

    def test_known_value(self):
        # 1 substituted word over 4 reference words
        assert wer("the quick brown fox", "the quick brown dog") == 0.25

    def test_empty_reference(self):
        assert wer("", "") == 0.0
        assert wer("", "word") == 1.0

    def test_insertion_counts(self):
        assert wer("a b", "a b c") == 0.5


class TestNormalizedSimilarity:
    def test_identical(self):
        assert normalized_similarity("abc", "abc") == 1.0

    def test_both_empty(self):
        assert normalized_similarity("", "") == 1.0

    def test_disjoint(self):
        assert normalized_similarity("aaa", "bbb") == 0.0

    def test_partial(self):
        assert abs(normalized_similarity("abcd", "abcx") - 0.75) < 1e-9
