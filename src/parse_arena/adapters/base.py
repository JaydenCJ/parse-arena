"""Parser adapter abstraction and registry.

Every parser is wrapped in a small adapter that turns its native output into
a normalized ParseResult. Heavyweight parsers import their dependency lazily
and report themselves as unavailable (with a reason) when it is missing, so
the harness degrades gracefully instead of crashing.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from parse_arena.metrics.table import Cell


class AdapterError(RuntimeError):
    """Raised by adapters when parsing a document fails."""


@dataclass(frozen=True)
class ParseResult:
    """Normalized parser output.

    Attributes:
        text: full plain text in the parser's reading order.
        blocks: text blocks (paragraph-level) in reading order.
        tables: extracted tables as rows of cells. A cell is either a plain
            string or a parse_arena.metrics.Cell carrying colspan/rowspan;
            the table metric span-expands both forms onto the same logical
            grid, so adapters may also report a merged cell by repeating its
            text across the covered grid positions.
    """

    text: str = ""
    blocks: tuple[str, ...] = ()
    tables: tuple[tuple[tuple["str | Cell", ...], ...], ...] = ()


@dataclass(frozen=True)
class Availability:
    """Whether an adapter can run in this environment, and why not."""

    available: bool
    reason: str = ""


class ParserAdapter(ABC):
    """Base class for all parser adapters.

    Subclasses set the class attributes and implement parse(). kind is one of
    'real' (works out of the box), 'optional' (needs an extra dependency) or
    'mock' (calibration baseline, excluded from router output by default).
    """

    name: str = ""
    kind: str = "real"
    extensions: tuple[str, ...] = ()
    description: str = ""

    def availability(self) -> Availability:
        """Adapters with lazy imports override this to report missing deps."""
        return Availability(True)

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() in self.extensions

    @abstractmethod
    def parse(self, path: Path) -> ParseResult:
        """Parse one document. Raise AdapterError on failure."""

    def version(self) -> str:
        """Version of the underlying parser library, when known."""
        return ""


_REGISTRY: dict[str, type[ParserAdapter]] = {}


def register(cls: type[ParserAdapter]) -> type[ParserAdapter]:
    """Class decorator that adds an adapter to the global registry."""
    if not cls.name:
        raise ValueError(f"adapter class {cls.__name__} must define a name")
    if cls.name in _REGISTRY:
        raise ValueError(f"duplicate adapter name: '{cls.name}'")
    _REGISTRY[cls.name] = cls
    return cls


def adapter_names() -> tuple[str, ...]:
    return tuple(sorted(_REGISTRY))


def get_adapter(name: str) -> ParserAdapter:
    """Instantiate a registered adapter by name; KeyError lists known names."""
    if name not in _REGISTRY:
        known = ", ".join(sorted(_REGISTRY))
        raise KeyError(f"unknown parser '{name}' (known parsers: {known})")
    return _REGISTRY[name]()


def all_adapters() -> list[ParserAdapter]:
    return [cls() for _, cls in sorted(_REGISTRY.items())]
