"""Adapter for PDF text extraction via pypdf (optional extra: pdf)."""

from __future__ import annotations

from pathlib import Path

from parse_arena.adapters.base import (
    AdapterError,
    Availability,
    ParseResult,
    ParserAdapter,
    register,
)

try:
    import pypdf

    _IMPORT_ERROR = ""
except ImportError as exc:  # pragma: no cover - depends on environment
    pypdf = None
    _IMPORT_ERROR = str(exc)


@register
class PypdfAdapter(ParserAdapter):
    """Extracts text per page with pypdf; each non-empty line is a block."""

    name = "pypdf"
    kind = "real"
    extensions = (".pdf",)
    description = "pypdf text extraction (pure-Python, no native deps)."

    def availability(self) -> Availability:
        if pypdf is None:
            return Availability(
                False,
                f"pypdf is not installed (pip install 'parse-arena[pdf]'): {_IMPORT_ERROR}",
            )
        return Availability(True)

    def parse(self, path: Path) -> ParseResult:
        if pypdf is None:
            raise AdapterError("pypdf is not installed; install 'parse-arena[pdf]'")
        try:
            reader = pypdf.PdfReader(str(path))
            pages = [page.extract_text() or "" for page in reader.pages]
        except Exception as exc:  # pypdf raises many exception types
            raise AdapterError(f"pypdf failed on {path}: {exc}") from exc
        text = "\n".join(pages).strip()
        blocks = tuple(line.strip() for line in text.splitlines() if line.strip())
        return ParseResult(text=text, blocks=blocks, tables=())

    def version(self) -> str:
        return f"pypdf-{pypdf.__version__}" if pypdf is not None else ""
