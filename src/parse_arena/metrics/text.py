"""Character and word error rates based on Levenshtein edit distance."""

from __future__ import annotations

from collections.abc import Sequence


def levenshtein(a: Sequence, b: Sequence) -> int:
    """Edit distance between two sequences (insert/delete/substitute, cost 1).

    Uses the classic two-row dynamic programming formulation: O(len(a)*len(b))
    time, O(min(len(a), len(b))) memory.
    """
    if len(a) < len(b):
        a, b = b, a
    if not b:
        return len(a)
    previous = list(range(len(b) + 1))
    for i, item_a in enumerate(a, start=1):
        current = [i]
        for j, item_b in enumerate(b, start=1):
            cost = 0 if item_a == item_b else 1
            current.append(
                min(
                    previous[j] + 1,  # deletion
                    current[j - 1] + 1,  # insertion
                    previous[j - 1] + cost,  # substitution
                )
            )
        previous = current
    return previous[-1]


def _error_rate(ref: Sequence, hyp: Sequence) -> float:
    """Edit distance divided by reference length, clipped to [0, 1].

    Edge cases (documented behaviour, covered by tests):
    - empty reference and empty hypothesis -> 0.0 (nothing to get wrong)
    - empty reference, non-empty hypothesis -> 1.0 (pure insertion noise)
    The clip at 1.0 keeps scores aggregatable; raw distances can exceed the
    reference length when the hypothesis is much longer.
    """
    if not ref:
        return 0.0 if not hyp else 1.0
    return min(1.0, levenshtein(ref, hyp) / len(ref))


def cer(reference: str, hypothesis: str) -> float:
    """Character error rate in [0, 1]; whitespace runs are normalized."""
    ref = _normalize_ws(reference)
    hyp = _normalize_ws(hypothesis)
    return _error_rate(ref, hyp)


def wer(reference: str, hypothesis: str) -> float:
    """Word error rate in [0, 1]; tokens are whitespace-separated words."""
    return _error_rate(reference.split(), hypothesis.split())


def normalized_similarity(a: str, b: str) -> float:
    """String similarity in [0, 1]: 1 - distance / max(len).

    Both empty -> 1.0 (identical). Used for cell alignment and block matching.
    """
    if not a and not b:
        return 1.0
    longest = max(len(a), len(b))
    return 1.0 - levenshtein(a, b) / longest


def _normalize_ws(text: str) -> str:
    """Collapse whitespace runs to single spaces and strip the ends.

    CER should measure recognition quality, not incidental line-wrapping
    differences between parsers.
    """
    return " ".join(text.split())
