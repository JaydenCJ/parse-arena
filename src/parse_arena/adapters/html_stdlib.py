"""HTML parser adapter built on the Python stdlib html.parser.

Extracts paragraph blocks and tables (span-expanded grids of cell strings:
colspan/rowspan cells fill every grid position they cover), and reconstructs
Japanese vertical-writing reading order: inside a writing-mode vertical-rl
container, column children carrying explicit geometry (an inline CSS left
offset in px/pt/em/rem, or a data-left attribute — the shape emitted by
OCR-to-HTML and PDF-to-HTML converters) are reordered right-to-left by
descending offset. Without geometry the DOM order is kept, which is already
the reading order for hand-authored vertical-rl HTML.
"""

from __future__ import annotations

import platform
import re
from html.parser import HTMLParser
from pathlib import Path

from parse_arena.adapters.base import AdapterError, ParseResult, ParserAdapter, register

_VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "source", "track", "wbr",
}
_SKIP_TAGS = {"script", "style", "head"}
_BLOCK_TAGS = {
    "p", "h1", "h2", "h3", "h4", "h5", "h6",
    "li", "blockquote", "pre", "figcaption", "dt", "dd",
}
_LEFT_RE = re.compile(
    r"(?:^|;)\s*left\s*:\s*(-?\d+(?:\.\d+)?)\s*(px|pt|em|rem)\b", re.IGNORECASE
)


class _Node:
    """Minimal DOM node: element children and raw text pieces."""

    __slots__ = ("tag", "attrs", "children")

    def __init__(self, tag: str, attrs: dict[str, str]):
        self.tag = tag
        self.attrs = attrs
        self.children: list["_Node | str"] = []


class _TreeBuilder(HTMLParser):
    """Builds a lightweight tree; tolerant of unclosed tags."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("#root", {})
        self._stack = [self.root]
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        node = _Node(tag, {k: (v or "") for k, v in attrs})
        self._stack[-1].children.append(node)
        if tag not in _VOID_TAGS:
            self._stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._skip_depth or tag in _SKIP_TAGS:
            return
        self._stack[-1].children.append(_Node(tag, {k: (v or "") for k, v in attrs}))

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return
        for i in range(len(self._stack) - 1, 0, -1):
            if self._stack[i].tag == tag:
                del self._stack[i:]
                break

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if data.strip():
            self._stack[-1].children.append(data)


def _text_content(node: _Node) -> str:
    parts: list[str] = []
    for child in node.children:
        if isinstance(child, str):
            parts.append(child)
        elif child.tag == "br":
            parts.append("\n")
        else:
            parts.append(_text_content(child))
    return "".join(parts)


def _collapse(text: str) -> str:
    return " ".join(text.split())


def _span(cell: _Node, attr: str) -> int:
    """colspan/rowspan attribute as an int >= 1 (malformed values -> 1)."""
    try:
        return max(1, int(cell.attrs.get(attr, "1")))
    except ValueError:
        return 1


def _extract_table(node: _Node) -> tuple[tuple[str, ...], ...]:
    """Extract a table as a span-expanded logical grid.

    Merged cells (colspan/rowspan) fill every grid position they cover, so
    the output matches the grid convention the TEDS metric compares on.
    """
    source_rows: list[list[_Node]] = []

    def walk(current: _Node) -> None:
        for child in current.children:
            if isinstance(child, str):
                continue
            if child.tag == "tr":
                cells = [
                    cell
                    for cell in child.children
                    if isinstance(cell, _Node) and cell.tag in ("td", "th")
                ]
                if cells:
                    source_rows.append(cells)
            else:
                walk(child)

    walk(node)
    rows: list[tuple[str, ...]] = []
    # pending rowspan carry-overs: (column, remaining_rows, text)
    carry: list[tuple[int, int, str]] = []
    for cells in source_rows:
        current: dict[int, str] = {}
        next_carry: list[tuple[int, int, str]] = []
        for col, remaining, text in carry:
            current[col] = text
            if remaining > 1:
                next_carry.append((col, remaining - 1, text))
        col = 0
        for cell in cells:
            text = _collapse(_text_content(cell))
            colspan = _span(cell, "colspan")
            rowspan = _span(cell, "rowspan")
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
            rows.append(tuple(current.get(i, "") for i in range(width)))
    return tuple(rows)


def _is_vertical(node: _Node) -> bool:
    style = node.attrs.get("style", "")
    if "vertical-rl" in style.replace(" ", ""):
        return True
    return node.attrs.get("data-writing-mode", "") == "vertical-rl"


def _left_offset(node: _Node) -> tuple[str, float] | None:
    """Explicit horizontal geometry of a column, as (unit, value).

    Sources, in priority order: an inline CSS 'left' declaration (px, pt, em
    or rem — the units OCR-to-HTML and PDF-to-HTML converters emit), then a
    'data-left' attribute. Returns None when the column carries no geometry.
    """
    match = _LEFT_RE.search(node.attrs.get("style", ""))
    if match:
        return (match.group(2).lower(), float(match.group(1)))
    if "data-left" in node.attrs:
        try:
            return ("data-left", float(node.attrs["data-left"]))
        except ValueError:
            return None
    return None


class _Extractor:
    def __init__(self) -> None:
        self.blocks: list[str] = []
        self.tables: list[tuple[tuple[str, ...], ...]] = []

    def walk(self, node: _Node) -> None:
        for child in node.children:
            if isinstance(child, str):
                text = _collapse(child)
                if text:
                    self.blocks.append(text)
                continue
            if child.tag == "table":
                rows = _extract_table(child)
                if rows:
                    self.tables.append(rows)
                    self.blocks.append("\n".join(" ".join(row) for row in rows))
                continue
            if _is_vertical(child):
                self._walk_vertical(child)
                continue
            if child.tag in _BLOCK_TAGS:
                text = _collapse(_text_content(child))
                if text:
                    self.blocks.append(text)
                continue
            self.walk(child)

    def _walk_vertical(self, container: _Node) -> None:
        """Vertical-rl layout: columns are read right-to-left.

        When every child carries explicit geometry (_left_offset) in one
        consistent unit, the columns are sorted by descending offset — the
        rightmost column comes first, which is how vertical Japanese is read.
        This recovers the reading order of geometric extractor output (OCR /
        PDF converters emit scan order plus coordinates). Children without
        offsets, or with mixed units, keep document order — for hand-authored
        vertical-rl HTML the DOM order already is the reading order.
        """
        columns = [c for c in container.children if isinstance(c, _Node)]
        offsets = [_left_offset(c) for c in columns]
        if (
            columns
            and all(o is not None for o in offsets)
            and len({o[0] for o in offsets}) == 1
        ):
            ordered = [
                c for _, c in sorted(zip(offsets, columns), key=lambda p: -p[0][1])
            ]
        else:
            ordered = columns
        for column in ordered:
            text = _collapse(_text_content(column))
            if text:
                self.blocks.append(text)


@register
class HtmlStdlibAdapter(ParserAdapter):
    """Layout-aware HTML extraction with zero third-party dependencies."""

    name = "html-stdlib"
    kind = "real"
    extensions = (".html", ".htm")
    description = (
        "Python stdlib html.parser; extracts blocks, tables (incl. "
        "colspan/rowspan merged cells) and vertical-rl Japanese column layout."
    )

    def parse(self, path: Path) -> ParseResult:
        try:
            raw = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise AdapterError(f"cannot read HTML file {path}: {exc}") from exc
        builder = _TreeBuilder()
        builder.feed(raw)
        builder.close()
        extractor = _Extractor()
        extractor.walk(builder.root)
        return ParseResult(
            text="\n\n".join(extractor.blocks),
            blocks=tuple(extractor.blocks),
            tables=tuple(extractor.tables),
        )

    def version(self) -> str:
        return f"python-{platform.python_version()}"
