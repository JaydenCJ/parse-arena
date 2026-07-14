"""Parser adapters: importing this package registers all built-in adapters."""

from parse_arena.adapters.base import (
    AdapterError,
    Availability,
    ParseResult,
    ParserAdapter,
    adapter_names,
    all_adapters,
    get_adapter,
    register,
)

# Import order defines nothing semantically; registry is sorted by name.
from parse_arena.adapters import plaintext  # noqa: F401
from parse_arena.adapters import html_stdlib  # noqa: F401
from parse_arena.adapters import pypdf_adapter  # noqa: F401
from parse_arena.adapters import mock  # noqa: F401
from parse_arena.adapters import heavy  # noqa: F401

__all__ = [
    "AdapterError",
    "Availability",
    "ParseResult",
    "ParserAdapter",
    "adapter_names",
    "all_adapters",
    "get_adapter",
    "register",
]
