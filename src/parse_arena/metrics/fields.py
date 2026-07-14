"""Field extraction recall for the receipt track."""

from __future__ import annotations

import unicodedata


def _normalize(value: str) -> str:
    """NFKC-fold, drop whitespace and common numeric separators.

    Receipts mix full-width and half-width digits and currency punctuation;
    a parser should not be penalized for those representation differences.
    """
    folded = unicodedata.normalize("NFKC", value)
    separators = {",", "¥", "円"}  # comma, yen sign, kanji "en"
    return "".join(ch for ch in folded if not ch.isspace() and ch not in separators)


def field_recall(text: str, fields: dict[str, str]) -> float:
    """Fraction of ground-truth field values present in the parsed text.

    Values and the text are normalized (NFKC, whitespace and separator
    stripped) before substring matching. Empty field set -> 1.0 (nothing to
    find). This is a recall-style proxy for structured extraction quality:
    if the parser lost or garbled the total amount, it cannot match.
    """
    if not fields:
        return 1.0
    haystack = _normalize(text)
    hit = sum(1 for value in fields.values() if _normalize(value) in haystack)
    return hit / len(fields)
