"""Mock adapter used as a calibration baseline and in tests.

The oracle returns the ground truth when it can locate it via the fixture
directory convention (docs/x.ext <-> ground_truth/x.json). It exists to
verify the metric pipeline end to end (a perfect parser must score 1.0) and
is excluded from router output by default because it is not a real parser.
"""

from __future__ import annotations

import json
from pathlib import Path

from parse_arena import __version__
from parse_arena.adapters.base import ParseResult, ParserAdapter, register
from parse_arena.metrics.table import Cell


def _cell(raw: object) -> str | Cell:
    """Ground-truth JSON cell -> string or span-carrying Cell."""
    if isinstance(raw, dict):
        return Cell(
            text=str(raw.get("text", "")),
            colspan=int(raw.get("colspan", 1)),
            rowspan=int(raw.get("rowspan", 1)),
        )
    return str(raw)


@register
class MockOracleAdapter(ParserAdapter):
    """Returns ground truth via the docs/ <-> ground_truth/ convention."""

    name = "mock-oracle"
    kind = "mock"
    extensions = (".txt", ".html", ".htm", ".pdf")
    description = (
        "Calibration baseline: replays the ground truth when found, "
        "otherwise echoes the raw file bytes as text."
    )

    def parse(self, path: Path) -> ParseResult:
        gt_path = path.parent.parent / "ground_truth" / f"{path.stem}.json"
        if gt_path.is_file():
            raw = json.loads(gt_path.read_text(encoding="utf-8"))
            blocks = tuple(raw.get("blocks", []))
            text = raw.get("text", "") or "\n\n".join(blocks)
            tables = tuple(
                tuple(tuple(_cell(cell) for cell in row) for row in table)
                for table in raw.get("tables", [])
            )
            return ParseResult(text=text, blocks=blocks, tables=tables)
        # No ground truth found: echo the file content (deterministic).
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            text = ""
        blocks = tuple(c.strip() for c in text.split("\n\n") if c.strip())
        return ParseResult(text=text.strip(), blocks=blocks, tables=())

    def version(self) -> str:
        return f"parse-arena-{__version__}"
