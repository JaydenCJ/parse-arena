"""Tests for manifest loading and validation."""

import pytest

from parse_arena.manifest import ManifestError, builtin_manifest_path, load_manifest
from parse_arena.metrics import Cell


def write_dataset(tmp_path, manifest_text, gt_text='{"blocks": ["hello"]}'):
    (tmp_path / "docs").mkdir(exist_ok=True)
    (tmp_path / "ground_truth").mkdir(exist_ok=True)
    (tmp_path / "docs" / "a.txt").write_text("hello", encoding="utf-8")
    (tmp_path / "ground_truth" / "a.json").write_text(gt_text, encoding="utf-8")
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(manifest_text, encoding="utf-8")
    return manifest


VALID = """
name: tiny
documents:
  - id: a
    file: docs/a.txt
    ground_truth: ground_truth/a.json
    track: en-text
"""


class TestBuiltinManifest:
    def test_loads_and_has_expected_tracks(self):
        manifest = load_manifest(builtin_manifest_path())
        assert manifest.name == "parse-arena-builtin"
        assert set(manifest.tracks) == {
            "en-text", "en-table", "en-form", "ja-vertical", "ja-receipt",
        }
        assert len(manifest.documents) == 11

    def test_japanese_tracks_have_expected_ground_truth(self):
        manifest = load_manifest(builtin_manifest_path())
        vertical_docs = manifest.by_track("ja-vertical")
        assert len(vertical_docs) == 2
        assert all(d.ground_truth.vertical for d in vertical_docs)
        receipt_docs = manifest.by_track("ja-receipt")
        assert len(receipt_docs) == 2
        assert all(d.ground_truth.fields for d in receipt_docs)

    def test_merged_cell_documents_carry_span_cells(self):
        manifest = load_manifest(builtin_manifest_path())
        by_id = {d.doc_id: d for d in manifest.documents}
        for doc_id in ("en-schedule", "en-tickets"):
            table = by_id[doc_id].ground_truth.tables[0]
            spans = [
                c for row in table for c in row
                if isinstance(c, Cell) and (c.colspan > 1 or c.rowspan > 1)
            ]
            assert spans, f"{doc_id} should declare merged cells"

    def test_form_track_has_field_ground_truth(self):
        manifest = load_manifest(builtin_manifest_path())
        form_docs = manifest.by_track("en-form")
        assert form_docs
        assert all(d.ground_truth.fields for d in form_docs)


class TestManifestValidation:
    def test_valid_manifest(self, tmp_path):
        manifest = load_manifest(write_dataset(tmp_path, VALID))
        assert manifest.documents[0].doc_id == "a"
        assert manifest.documents[0].ground_truth.blocks == ("hello",)
        assert manifest.documents[0].ground_truth.text == "hello"

    def test_missing_manifest_file(self, tmp_path):
        with pytest.raises(ManifestError, match="not found"):
            load_manifest(tmp_path / "nope.yaml")

    def test_invalid_yaml(self, tmp_path):
        path = write_dataset(tmp_path, "name: [unclosed")
        with pytest.raises(ManifestError, match="not valid YAML"):
            load_manifest(path)

    def test_missing_name(self, tmp_path):
        path = write_dataset(tmp_path, VALID.replace("name: tiny\n", ""))
        with pytest.raises(ManifestError, match="'name'"):
            load_manifest(path)

    def test_missing_document_file(self, tmp_path):
        path = write_dataset(tmp_path, VALID.replace("docs/a.txt", "docs/missing.txt"))
        with pytest.raises(ManifestError, match="input file not found"):
            load_manifest(path)

    def test_duplicate_document_id(self, tmp_path):
        duplicated = VALID + """
  - id: a
    file: docs/a.txt
    ground_truth: ground_truth/a.json
    track: en-text
"""
        path = write_dataset(tmp_path, duplicated)
        with pytest.raises(ManifestError, match="duplicate document id"):
            load_manifest(path)

    def test_unknown_document_key_rejected(self, tmp_path):
        path = write_dataset(tmp_path, VALID + "    surprise: 1\n")
        with pytest.raises(ManifestError, match="unknown keys"):
            load_manifest(path)

    def test_ground_truth_must_be_json(self, tmp_path):
        path = write_dataset(tmp_path, VALID, gt_text="not json at all")
        with pytest.raises(ManifestError, match="not valid JSON"):
            load_manifest(path)

    def test_ground_truth_bad_blocks_type(self, tmp_path):
        path = write_dataset(tmp_path, VALID, gt_text='{"blocks": "oops"}')
        with pytest.raises(ManifestError, match="'blocks'"):
            load_manifest(path)

    def test_ground_truth_span_cells_parsed(self, tmp_path):
        gt = (
            '{"tables": [[[{"text": "Half", "colspan": 2}], ["Q1", "Q2"]]]}'
        )
        path = write_dataset(tmp_path, VALID, gt_text=gt)
        table = load_manifest(path).documents[0].ground_truth.tables[0]
        assert table[0][0] == Cell(text="Half", colspan=2, rowspan=1)
        assert table[1] == ("Q1", "Q2")

    def test_ground_truth_span_cell_requires_text(self, tmp_path):
        path = write_dataset(
            tmp_path, VALID, gt_text='{"tables": [[[{"colspan": 2}]]]}'
        )
        with pytest.raises(ManifestError, match="'text'"):
            load_manifest(path)

    def test_ground_truth_span_cell_bad_span_value(self, tmp_path):
        for bad in ('{"text": "x", "colspan": 0}', '{"text": "x", "rowspan": "2"}'):
            path = write_dataset(
                tmp_path, VALID, gt_text='{"tables": [[[' + bad + ']]]}'
            )
            with pytest.raises(ManifestError, match="integer >= 1"):
                load_manifest(path)

    def test_ground_truth_span_cell_unknown_key(self, tmp_path):
        path = write_dataset(
            tmp_path, VALID,
            gt_text='{"tables": [[[{"text": "x", "span": 2}]]]}',
        )
        with pytest.raises(ManifestError, match="unknown keys"):
            load_manifest(path)

    def test_empty_documents_rejected(self, tmp_path):
        path = write_dataset(tmp_path, "name: tiny\ndocuments: []\n")
        with pytest.raises(ManifestError, match="documents"):
            load_manifest(path)
