"""Optional adapters for heavyweight parsers (graceful skip when missing).

These libraries are large (hundreds of MB with their model dependencies), so
they are NOT part of the default install. Each adapter imports its dependency
lazily; when it is absent the adapter reports itself unavailable with an
actionable reason and the harness records it in the results as skipped.
"""

from __future__ import annotations

from pathlib import Path

from parse_arena.adapters.base import (
    AdapterError,
    Availability,
    ParseResult,
    ParserAdapter,
    register,
)


def _blocks_from_text(text: str) -> tuple[str, ...]:
    return tuple(" ".join(c.split()) for c in text.split("\n\n") if c.strip())


@register
class UnstructuredAdapter(ParserAdapter):
    """unstructured.io partitioning (PDF/HTML/TXT and more)."""

    name = "unstructured"
    kind = "optional"
    extensions = (".pdf", ".html", ".htm", ".txt")
    description = "unstructured.io auto partitioning (optional heavy dependency)."

    def availability(self) -> Availability:
        try:
            import unstructured  # noqa: F401
        except ImportError as exc:
            return Availability(
                False, f"unstructured is not installed (pip install unstructured): {exc}"
            )
        return Availability(True)

    def parse(self, path: Path) -> ParseResult:
        try:
            from unstructured.partition.auto import partition
        except ImportError as exc:
            raise AdapterError(f"unstructured is not installed: {exc}") from exc
        try:
            elements = partition(filename=str(path))
        except Exception as exc:
            raise AdapterError(f"unstructured failed on {path}: {exc}") from exc
        blocks: list[str] = []
        tables: list[tuple[tuple[str, ...], ...]] = []
        for element in elements:
            text = " ".join(str(element).split())
            if not text:
                continue
            blocks.append(text)
            if type(element).__name__ == "Table":
                html = getattr(getattr(element, "metadata", None), "text_as_html", None)
                if html:
                    tables.extend(_tables_from_html(html))
        return ParseResult(
            text="\n\n".join(blocks), blocks=tuple(blocks), tables=tuple(tables)
        )

    def version(self) -> str:
        try:
            import unstructured

            # In recent releases unstructured.__version__ is a *module*
            # exposing its own __version__ string; older releases exposed
            # the string directly. Handle both.
            raw = getattr(unstructured, "__version__", "unknown")
            if not isinstance(raw, str):
                raw = getattr(raw, "__version__", "unknown")
            return f"unstructured-{raw}"
        except ImportError:
            return ""


@register
class MarkItDownAdapter(ParserAdapter):
    """Microsoft MarkItDown conversion to Markdown text."""

    name = "markitdown"
    kind = "optional"
    extensions = (".pdf", ".html", ".htm", ".txt")
    description = "MarkItDown document-to-Markdown conversion (optional dependency)."

    def availability(self) -> Availability:
        try:
            import markitdown  # noqa: F401
        except ImportError as exc:
            return Availability(
                False, f"markitdown is not installed (pip install markitdown): {exc}"
            )
        return Availability(True)

    def parse(self, path: Path) -> ParseResult:
        try:
            from markitdown import MarkItDown
        except ImportError as exc:
            raise AdapterError(f"markitdown is not installed: {exc}") from exc
        try:
            result = MarkItDown().convert(str(path))
            text = (result.text_content or "").strip()
        except Exception as exc:
            raise AdapterError(f"markitdown failed on {path}: {exc}") from exc
        # Markdown pipe tables are recovered into grids for the table metric.
        return ParseResult(
            text=text,
            blocks=_blocks_from_text(text),
            tables=_tables_from_markdown(text),
        )

    def version(self) -> str:
        try:
            import markitdown

            return f"markitdown-{getattr(markitdown, '__version__', 'unknown')}"
        except ImportError:
            return ""


def _tables_from_html(html: str) -> list[tuple[tuple[str, ...], ...]]:
    """Reuse the stdlib HTML table extractor for embedded table markup."""
    from parse_arena.adapters.html_stdlib import _extract_table, _TreeBuilder

    builder = _TreeBuilder()
    builder.feed(html)
    builder.close()
    rows = _extract_table(builder.root)
    return [rows] if rows else []


def _tables_from_markdown(text: str) -> tuple[tuple[tuple[str, ...], ...], ...]:
    """Recover Markdown pipe tables as cell grids (separator rows dropped)."""
    tables: list[tuple[tuple[str, ...], ...]] = []
    current: list[tuple[str, ...]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|") and len(stripped) > 1:
            cells = tuple(c.strip() for c in stripped.strip("|").split("|"))
            if all(set(c) <= {"-", ":", " "} and c for c in cells):
                continue  # header separator row
            current.append(cells)
        elif current:
            tables.append(tuple(current))
            current = []
    if current:
        tables.append(tuple(current))
    return tuple(tables)
