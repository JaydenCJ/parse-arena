"""Dataset manifest loading and validation.

A manifest is a YAML file that declares documents, their ground-truth files
and track labels. All paths inside a manifest are resolved relative to the
manifest file itself, so datasets are relocatable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from parse_arena.metrics.table import Cell

# Track identifiers shipped with the built-in dataset. Custom manifests may
# define additional tracks; these constants only document the built-ins.
TRACK_EN_TEXT = "en-text"
TRACK_EN_TABLE = "en-table"
TRACK_EN_FORM = "en-form"
TRACK_JA_VERTICAL = "ja-vertical"
TRACK_JA_RECEIPT = "ja-receipt"

_ALLOWED_DOC_KEYS = {"id", "file", "ground_truth", "track", "description"}
_ALLOWED_GT_KEYS = {"text", "blocks", "tables", "fields", "vertical"}
_ALLOWED_CELL_KEYS = {"text", "colspan", "rowspan"}


class ManifestError(ValueError):
    """Raised when a manifest or a ground-truth file is invalid."""


@dataclass(frozen=True)
class GroundTruth:
    """Parsed ground truth for one document.

    Attributes:
        text: expected plain text (reading order, blocks joined by blank line).
        blocks: expected text blocks in correct reading order.
        tables: expected tables, each a list of rows of cells; a cell is a
            plain string or a Cell with colspan/rowspan for merged cells.
        fields: expected key/value fields (receipt and form tracks).
        vertical: True when the document is vertical Japanese text and the
            vertical-order accuracy metric applies.
    """

    text: str = ""
    blocks: tuple[str, ...] = ()
    tables: tuple[tuple[tuple["str | Cell", ...], ...], ...] = ()
    fields: dict[str, str] = field(default_factory=dict)
    vertical: bool = False


@dataclass(frozen=True)
class Document:
    """One benchmark document: input file + ground truth + track label."""

    doc_id: str
    path: Path
    track: str
    ground_truth: GroundTruth
    ground_truth_path: Path
    description: str = ""

    @property
    def extension(self) -> str:
        return self.path.suffix.lower()


@dataclass(frozen=True)
class Manifest:
    """A validated dataset manifest."""

    name: str
    path: Path
    documents: tuple[Document, ...]

    @property
    def tracks(self) -> tuple[str, ...]:
        seen: list[str] = []
        for doc in self.documents:
            if doc.track not in seen:
                seen.append(doc.track)
        return tuple(seen)

    def by_track(self, track: str) -> tuple[Document, ...]:
        return tuple(d for d in self.documents if d.track == track)


def builtin_manifest_path() -> Path:
    """Path of the manifest bundled with the package."""
    return Path(__file__).parent / "fixtures" / "manifest.yaml"


def _load_cell(cell: object, doc_id: str, table_index: int) -> str | Cell:
    """Validate one ground-truth table cell.

    A cell is a scalar (coerced to str) or an object with a required 'text'
    plus optional integer 'colspan'/'rowspan' >= 1 for merged cells.
    """
    if isinstance(cell, dict):
        unknown = set(cell) - _ALLOWED_CELL_KEYS
        if unknown:
            raise ManifestError(
                f"document '{doc_id}': table {table_index} cell has unknown "
                f"keys: {sorted(unknown)}"
            )
        if not isinstance(cell.get("text"), str):
            raise ManifestError(
                f"document '{doc_id}': table {table_index} cell object "
                "requires a 'text' string"
            )
        spans = {}
        for key in ("colspan", "rowspan"):
            value = cell.get(key, 1)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ManifestError(
                    f"document '{doc_id}': table {table_index} cell "
                    f"'{key}' must be an integer >= 1"
                )
            spans[key] = value
        return Cell(text=cell["text"], colspan=spans["colspan"], rowspan=spans["rowspan"])
    if isinstance(cell, (list, tuple)):
        raise ManifestError(
            f"document '{doc_id}': table {table_index} cell must be a string "
            "or an object, not a list"
        )
    return str(cell)


def _load_ground_truth(path: Path, doc_id: str) -> GroundTruth:
    if not path.is_file():
        raise ManifestError(f"document '{doc_id}': ground truth file not found: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ManifestError(f"document '{doc_id}': ground truth is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise ManifestError(f"document '{doc_id}': ground truth must be a JSON object")
    unknown = set(raw) - _ALLOWED_GT_KEYS
    if unknown:
        raise ManifestError(
            f"document '{doc_id}': unknown ground truth keys: {sorted(unknown)}"
        )
    blocks = raw.get("blocks", [])
    if not isinstance(blocks, list) or not all(isinstance(b, str) for b in blocks):
        raise ManifestError(f"document '{doc_id}': 'blocks' must be a list of strings")
    text = raw.get("text", "")
    if not isinstance(text, str):
        raise ManifestError(f"document '{doc_id}': 'text' must be a string")
    if not text and blocks:
        text = "\n\n".join(blocks)
    tables_raw = raw.get("tables", [])
    tables: list[tuple[tuple[str | Cell, ...], ...]] = []
    if not isinstance(tables_raw, list):
        raise ManifestError(f"document '{doc_id}': 'tables' must be a list")
    for ti, table in enumerate(tables_raw):
        if not isinstance(table, list) or not all(isinstance(row, list) for row in table):
            raise ManifestError(f"document '{doc_id}': table {ti} must be a list of rows")
        tables.append(
            tuple(
                tuple(_load_cell(cell, doc_id, ti) for cell in row) for row in table
            )
        )
    fields_raw = raw.get("fields", {})
    if not isinstance(fields_raw, dict):
        raise ManifestError(f"document '{doc_id}': 'fields' must be an object")
    fields = {str(k): str(v) for k, v in fields_raw.items()}
    vertical = bool(raw.get("vertical", False))
    return GroundTruth(
        text=text,
        blocks=tuple(blocks),
        tables=tuple(tables),
        fields=fields,
        vertical=vertical,
    )


def load_manifest(path: str | Path) -> Manifest:
    """Load and validate a dataset manifest.

    Raises ManifestError with a human-readable message on any problem.
    """
    manifest_path = Path(path).resolve()
    if not manifest_path.is_file():
        raise ManifestError(f"manifest file not found: {manifest_path}")
    try:
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ManifestError(f"manifest is not valid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise ManifestError("manifest root must be a mapping")
    name = raw.get("name")
    if not isinstance(name, str) or not name:
        raise ManifestError("manifest requires a non-empty 'name' string")
    docs_raw = raw.get("documents")
    if not isinstance(docs_raw, list) or not docs_raw:
        raise ManifestError("manifest requires a non-empty 'documents' list")

    base = manifest_path.parent
    documents: list[Document] = []
    seen_ids: set[str] = set()
    for i, entry in enumerate(docs_raw):
        if not isinstance(entry, dict):
            raise ManifestError(f"documents[{i}] must be a mapping")
        unknown = set(entry) - _ALLOWED_DOC_KEYS
        if unknown:
            raise ManifestError(f"documents[{i}]: unknown keys: {sorted(unknown)}")
        for key in ("id", "file", "ground_truth", "track"):
            if not isinstance(entry.get(key), str) or not entry.get(key):
                raise ManifestError(f"documents[{i}]: '{key}' is required and must be a string")
        doc_id = entry["id"]
        if doc_id in seen_ids:
            raise ManifestError(f"duplicate document id: '{doc_id}'")
        seen_ids.add(doc_id)
        doc_path = (base / entry["file"]).resolve()
        if not doc_path.is_file():
            raise ManifestError(f"document '{doc_id}': input file not found: {doc_path}")
        gt_path = (base / entry["ground_truth"]).resolve()
        ground_truth = _load_ground_truth(gt_path, doc_id)
        documents.append(
            Document(
                doc_id=doc_id,
                path=doc_path,
                track=entry["track"],
                ground_truth=ground_truth,
                ground_truth_path=gt_path,
                description=str(entry.get("description", "")),
            )
        )
    return Manifest(name=name, path=manifest_path, documents=tuple(documents))
