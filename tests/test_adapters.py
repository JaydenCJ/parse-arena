"""Tests for the adapter registry and the built-in adapters."""

import importlib.util

import pytest

from parse_arena.adapters import (
    AdapterError,
    ParserAdapter,
    adapter_names,
    all_adapters,
    get_adapter,
)
from parse_arena.manifest import builtin_manifest_path


requires_pypdf = pytest.mark.skipif(
    importlib.util.find_spec("pypdf") is None,
    reason="pypdf is not installed (pip install -e '.[dev]' or '.[pdf]')",
)


def fixture_doc(name: str):
    return builtin_manifest_path().parent / "docs" / name


class TestRegistry:
    def test_builtin_adapters_registered(self):
        names = adapter_names()
        for expected in ("plaintext", "html-stdlib", "pypdf", "mock-oracle",
                         "unstructured", "markitdown"):
            assert expected in names

    def test_get_adapter_unknown_name(self):
        with pytest.raises(KeyError, match="known parsers"):
            get_adapter("does-not-exist")

    def test_all_adapters_instantiates(self):
        adapters = all_adapters()
        assert all(isinstance(a, ParserAdapter) for a in adapters)

    def test_at_least_two_real_adapters_available(self):
        real_available = [
            a for a in all_adapters()
            if a.kind == "real" and a.availability().available
        ]
        assert len(real_available) >= 2


class TestPlainTextAdapter:
    def test_parses_paragraph_blocks(self, tmp_path):
        doc = tmp_path / "sample.txt"
        doc.write_text("First para line one.\nline two.\n\nSecond para.", encoding="utf-8")
        result = get_adapter("plaintext").parse(doc)
        assert result.blocks == ("First para line one. line two.", "Second para.")
        assert "Second para." in result.text
        assert result.tables == ()

    def test_missing_file_raises_adapter_error(self, tmp_path):
        with pytest.raises(AdapterError, match="cannot read"):
            get_adapter("plaintext").parse(tmp_path / "missing.txt")

    def test_supports_only_txt(self, tmp_path):
        adapter = get_adapter("plaintext")
        assert adapter.supports(tmp_path / "a.txt")
        assert not adapter.supports(tmp_path / "a.pdf")


class TestHtmlStdlibAdapter:
    def test_extracts_blocks_and_table(self):
        result = get_adapter("html-stdlib").parse(fixture_doc("en_report.html"))
        assert result.blocks[0] == "Quarterly Parser Evaluation"
        assert len(result.tables) == 1
        assert result.tables[0][0] == ("Service", "Primary track", "Mean score")
        assert result.tables[0][1] == ("Alpha", "en-text", "0.91")

    def test_vertical_columns_read_right_to_left(self):
        result = get_adapter("html-stdlib").parse(fixture_doc("ja_vertical_poem.html"))
        assert result.blocks == (
            "雨ニモマケズ",
            "風ニモマケズ",
            "雪ニモ夏ノ暑サニモマケヌ",
            "丈夫ナカラダヲモチ",
        )

    def test_extracts_merged_cells_onto_logical_grid(self):
        result = get_adapter("html-stdlib").parse(fixture_doc("en_schedule.html"))
        assert result.tables[0] == (
            ("Room", "Morning", "Morning", "Afternoon"),
            ("Room", "09:00", "11:00", "Afternoon"),
            ("Aoi", "Standup", "Design review", "Workshop"),
            ("Kiku", "Interview", "Hiring sync", "Workshop"),
        )

    def test_colspan_rowspan_inline_html(self, tmp_path):
        doc = tmp_path / "m.html"
        doc.write_text(
            "<table>"
            '<tr><td colspan="2">head</td></tr>'
            '<tr><td rowspan="2">a</td><td>b</td></tr>'
            "<tr><td>c</td></tr>"
            "</table>",
            encoding="utf-8",
        )
        result = get_adapter("html-stdlib").parse(doc)
        assert result.tables[0] == (
            ("head", "head"),
            ("a", "b"),
            ("a", "c"),
        )

    def test_malformed_span_attribute_treated_as_one(self, tmp_path):
        doc = tmp_path / "bad-span.html"
        doc.write_text(
            '<table><tr><td colspan="wide">a</td><td>b</td></tr></table>',
            encoding="utf-8",
        )
        result = get_adapter("html-stdlib").parse(doc)
        assert result.tables[0] == (("a", "b"),)

    def test_vertical_without_offsets_keeps_document_order(self, tmp_path):
        # Hand-authored vertical-rl HTML has no geometry; its DOM order is
        # already the reading order and must be preserved.
        doc = tmp_path / "v.html"
        doc.write_text(
            '<div data-writing-mode="vertical-rl"><div>甲</div><div>乙</div></div>',
            encoding="utf-8",
        )
        result = get_adapter("html-stdlib").parse(doc)
        assert result.blocks == ("甲", "乙")

    def test_vertical_offsets_in_pt_units_sorted(self, tmp_path):
        doc = tmp_path / "vpt.html"
        doc.write_text(
            '<div style="writing-mode: vertical-rl;">'
            '<div style="position: absolute; left: 10.5pt;">乙</div>'
            '<div style="position: absolute; left: 90pt;">甲</div>'
            "</div>",
            encoding="utf-8",
        )
        result = get_adapter("html-stdlib").parse(doc)
        assert result.blocks == ("甲", "乙")

    def test_vertical_mixed_units_fall_back_to_document_order(self, tmp_path):
        doc = tmp_path / "vmix.html"
        doc.write_text(
            '<div style="writing-mode: vertical-rl;">'
            '<div style="left: 2em;">甲</div>'
            '<div style="left: 90px;">乙</div>'
            "</div>",
            encoding="utf-8",
        )
        result = get_adapter("html-stdlib").parse(doc)
        assert result.blocks == ("甲", "乙")

    def test_margin_left_is_not_mistaken_for_geometry(self, tmp_path):
        doc = tmp_path / "vmargin.html"
        doc.write_text(
            '<div style="writing-mode: vertical-rl;">'
            '<div style="margin-left: 10px;">甲</div>'
            '<div style="margin-left: 90px;">乙</div>'
            "</div>",
            encoding="utf-8",
        )
        result = get_adapter("html-stdlib").parse(doc)
        assert result.blocks == ("甲", "乙")

    def test_script_and_style_ignored(self, tmp_path):
        doc = tmp_path / "s.html"
        doc.write_text(
            "<html><head><style>p em { color: red; }</style></head>"
            "<body><script>var x = 1;</script><p>visible</p></body></html>",
            encoding="utf-8",
        )
        result = get_adapter("html-stdlib").parse(doc)
        assert result.blocks == ("visible",)

    def test_malformed_html_does_not_crash(self, tmp_path):
        doc = tmp_path / "bad.html"
        doc.write_text("<p>open paragraph<table><tr><td>cell", encoding="utf-8")
        result = get_adapter("html-stdlib").parse(doc)
        assert "cell" in result.text


@requires_pypdf
class TestPypdfAdapter:
    def test_available_with_pypdf_installed(self):
        assert get_adapter("pypdf").availability().available

    def test_extracts_invoice_lines(self):
        result = get_adapter("pypdf").parse(fixture_doc("en_invoice.pdf"))
        assert result.blocks[0] == "PARSE ARENA INVOICE 2026-0042"
        assert "Total: 126.00 USD" in result.blocks

    def test_corrupt_pdf_raises_adapter_error(self, tmp_path):
        bad = tmp_path / "bad.pdf"
        bad.write_bytes(b"not a pdf at all")
        with pytest.raises(AdapterError, match="pypdf failed"):
            get_adapter("pypdf").parse(bad)


class TestMockOracleAdapter:
    def test_replays_ground_truth_for_fixture_docs(self):
        result = get_adapter("mock-oracle").parse(fixture_doc("ja_vertical_essay.html"))
        assert result.blocks[0].startswith("春はあけぼの")

    def test_echoes_text_without_ground_truth(self, tmp_path):
        doc = tmp_path / "loose.txt"
        doc.write_text("just text", encoding="utf-8")
        result = get_adapter("mock-oracle").parse(doc)
        assert result.text == "just text"

    def test_kind_is_mock(self):
        assert get_adapter("mock-oracle").kind == "mock"


class TestOptionalHeavyAdapters:
    """Heavy parsers are not installed in CI: they must skip gracefully."""

    @pytest.mark.parametrize("name", ["unstructured", "markitdown"])
    def test_unavailable_with_reason(self, name):
        adapter = get_adapter(name)
        availability = adapter.availability()
        if availability.available:
            pytest.skip(f"{name} happens to be installed in this environment")
        assert availability.reason
        assert "pip install" in availability.reason

    @pytest.mark.parametrize("name", ["unstructured", "markitdown"])
    def test_parse_without_dependency_raises(self, name, tmp_path):
        adapter = get_adapter(name)
        if adapter.availability().available:
            pytest.skip(f"{name} happens to be installed in this environment")
        doc = tmp_path / "x.txt"
        doc.write_text("content", encoding="utf-8")
        with pytest.raises(AdapterError, match="not installed"):
            adapter.parse(doc)

    def test_unstructured_field_mapping_with_stub_library(self, monkeypatch, tmp_path):
        """Exercises the real parse() mapping against an API-shaped stub.

        The stub mirrors the unstructured API surface the adapter consumes:
        partition(filename=...) returning elements whose str() is the text,
        with table elements exposing metadata.text_as_html.
        """
        import sys
        import types

        class _Metadata:
            def __init__(self, html):
                self.text_as_html = html

        class Table:  # type(element).__name__ must be "Table"
            def __init__(self, text, html):
                self._text = text
                self.metadata = _Metadata(html)

            def __str__(self):
                return self._text

        class NarrativeText:
            def __init__(self, text):
                self._text = text

            def __str__(self):
                return self._text

        def partition(filename=None):
            assert filename
            return [
                NarrativeText("Intro   paragraph."),
                Table(
                    "Plan Price Basic 9",
                    "<table><tr><td>Plan</td><td>Price</td></tr>"
                    "<tr><td>Basic</td><td>9</td></tr></table>",
                ),
                NarrativeText("   "),  # empty text must be dropped
            ]

        pkg = types.ModuleType("unstructured")
        pkg.__version__ = "0.0-stub"
        sub = types.ModuleType("unstructured.partition")
        auto = types.ModuleType("unstructured.partition.auto")
        auto.partition = partition
        sub.auto = auto
        pkg.partition = sub
        monkeypatch.setitem(sys.modules, "unstructured", pkg)
        monkeypatch.setitem(sys.modules, "unstructured.partition", sub)
        monkeypatch.setitem(sys.modules, "unstructured.partition.auto", auto)

        doc = tmp_path / "doc.txt"
        doc.write_text("content", encoding="utf-8")
        adapter = get_adapter("unstructured")
        assert adapter.availability().available
        result = adapter.parse(doc)
        assert result.blocks == ("Intro paragraph.", "Plan Price Basic 9")
        assert result.tables == ((("Plan", "Price"), ("Basic", "9")),)
        assert adapter.version() == "unstructured-0.0-stub"

    def test_unstructured_partition_failure_becomes_adapter_error(
        self, monkeypatch, tmp_path
    ):
        import sys
        import types

        def partition(filename=None):
            raise RuntimeError("boom")

        pkg = types.ModuleType("unstructured")
        sub = types.ModuleType("unstructured.partition")
        auto = types.ModuleType("unstructured.partition.auto")
        auto.partition = partition
        sub.auto = auto
        pkg.partition = sub
        monkeypatch.setitem(sys.modules, "unstructured", pkg)
        monkeypatch.setitem(sys.modules, "unstructured.partition", sub)
        monkeypatch.setitem(sys.modules, "unstructured.partition.auto", auto)

        doc = tmp_path / "doc.txt"
        doc.write_text("content", encoding="utf-8")
        with pytest.raises(AdapterError, match="unstructured failed"):
            get_adapter("unstructured").parse(doc)

    def test_markitdown_field_mapping_with_stub_library(self, monkeypatch, tmp_path):
        """Exercises the real parse() mapping (convert -> text_content ->
        blocks + recovered pipe tables) against an API-shaped stub."""
        import sys
        import types

        class _Result:
            def __init__(self, text):
                self.text_content = text

        class MarkItDown:
            def convert(self, path):
                assert isinstance(path, str)
                return _Result(
                    "# Title\n\nIntro paragraph.\n\n"
                    "| Plan | Price |\n| --- | --- |\n| Basic | 9 |\n"
                )

        mod = types.ModuleType("markitdown")
        mod.MarkItDown = MarkItDown
        mod.__version__ = "0.0-stub"
        monkeypatch.setitem(sys.modules, "markitdown", mod)

        doc = tmp_path / "doc.html"
        doc.write_text("<p>hi</p>", encoding="utf-8")
        adapter = get_adapter("markitdown")
        assert adapter.availability().available
        result = adapter.parse(doc)
        assert result.blocks[0] == "# Title"
        assert "Intro paragraph." in result.blocks
        assert result.tables == ((("Plan", "Price"), ("Basic", "9")),)
        assert adapter.version() == "markitdown-0.0-stub"

    def test_markdown_table_recovery_helper(self):
        from parse_arena.adapters.heavy import _tables_from_markdown

        text = (
            "intro line\n"
            "| Plan | Price |\n"
            "| --- | --- |\n"
            "| Basic | 9 |\n"
            "| Pro | 29 |\n"
            "outro line\n"
        )
        tables = _tables_from_markdown(text)
        assert tables == ((("Plan", "Price"), ("Basic", "9"), ("Pro", "29")),)

    def test_html_table_recovery_helper(self):
        from parse_arena.adapters.heavy import _tables_from_html

        tables = _tables_from_html("<table><tr><td>a</td><td>b</td></tr></table>")
        assert tables == [(("a", "b"),)]
