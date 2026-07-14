"""Adapter for plain-text documents (baseline for .txt inputs)."""

from __future__ import annotations

import platform
from pathlib import Path

from parse_arena.adapters.base import AdapterError, ParseResult, ParserAdapter, register


@register
class PlainTextAdapter(ParserAdapter):
    """Reads UTF-8 text files; blocks are blank-line separated paragraphs."""

    name = "plaintext"
    kind = "real"
    extensions = (".txt",)
    description = "Python stdlib text reader; paragraph blocks split on blank lines."

    def parse(self, path: Path) -> ParseResult:
        try:
            raw = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise AdapterError(f"cannot read text file {path}: {exc}") from exc
        blocks = tuple(
            " ".join(chunk.split())
            for chunk in raw.split("\n\n")
            if chunk.strip()
        )
        return ParseResult(text=raw.strip(), blocks=blocks, tables=())

    def version(self) -> str:
        return f"python-{platform.python_version()}"
