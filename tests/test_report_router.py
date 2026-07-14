"""Tests for the static site generator and the router config generator."""

import importlib.util
import json

import pytest
import yaml

from parse_arena.manifest import builtin_manifest_path, load_manifest
from parse_arena.report import generate_site, render_index_html
from parse_arena.router import RouterError, generate_router_config, render_router_yaml
from parse_arena.runner import run_evaluation


@pytest.fixture(scope="module")
def results():
    manifest = load_manifest(builtin_manifest_path())
    return run_evaluation(
        manifest,
        parsers_spec="all",
        command="parse-arena run --parsers all --out results.json",
    )


class TestReport:
    def test_site_files_written(self, results, tmp_path):
        index = generate_site(results, tmp_path / "site")
        assert index.is_file()
        assert (tmp_path / "site" / "results.json").is_file()
        # the copied JSON round-trips
        copied = json.loads((tmp_path / "site" / "results.json").read_text("utf-8"))
        assert copied["manifest"]["name"] == "parse-arena-builtin"

    def test_html_contains_leaderboard_table(self, results):
        html = render_index_html(results)
        assert '<table class="board" id="leaderboard">' in html

    def test_html_contains_all_tracks(self, results):
        html = render_index_html(results)
        for track in ("en-text", "en-table", "en-form", "ja-vertical", "ja-receipt"):
            assert f'data-track="{track}"' in html

    def test_html_contains_reproduce_command(self, results):
        html = render_index_html(results)
        assert "parse-arena run --parsers all --out results.json" in html

    def test_html_marks_mock_parsers(self, results):
        html = render_index_html(results)
        assert "mock-oracle" in html
        assert 'class="badge mock"' in html

    def test_html_is_self_contained(self, results):
        # no external scripts, stylesheets or images: the site works offline
        html = render_index_html(results)
        assert "<script src=" not in html
        assert "<link" not in html
        assert "<img" not in html


class TestRouter:
    def test_config_structure(self, results):
        config = generate_router_config(results)
        assert config["version"] == 1
        assert config["default_parser"]
        tracks = {rule["track"] for rule in config["rules"]}
        assert tracks == {"en-text", "en-table", "en-form", "ja-vertical", "ja-receipt"}

    def test_mock_excluded_by_default(self, results):
        config = generate_router_config(results)
        assert all(rule["parser"] != "mock-oracle" for rule in config["rules"])
        assert config["default_parser"] != "mock-oracle"

    def test_include_mock_flag(self, results):
        config = generate_router_config(results, include_mock=True)
        parsers = {rule["parser"] for rule in config["rules"]}
        assert "mock-oracle" in parsers

    def test_vertical_track_routes_to_html_stdlib(self, results):
        config = generate_router_config(results)
        rule = next(r for r in config["rules"] if r["track"] == "ja-vertical")
        assert rule["parser"] == "html-stdlib"
        assert rule["extensions"] == [".html"]

    @pytest.mark.skipif(
        importlib.util.find_spec("pypdf") is None,
        reason="pypdf is not installed (pip install -e '.[dev]' or '.[pdf]')",
    )
    def test_extension_level_routing(self, results):
        # en-text mixes .txt and .pdf: each extension routes to the parser
        # that actually handles it.
        config = generate_router_config(results)
        en_text = {
            ext: rule["parser"]
            for rule in config["rules"]
            if rule["track"] == "en-text"
            for ext in rule["extensions"]
        }
        assert en_text[".txt"] == "plaintext"
        assert en_text[".pdf"] == "pypdf"

    def test_yaml_round_trip(self, results):
        config = generate_router_config(results)
        text = render_router_yaml(config)
        assert yaml.safe_load(text) == config

    def test_no_leaderboard_raises(self):
        with pytest.raises(RouterError, match="leaderboard"):
            generate_router_config({"results": []})

    def test_only_mock_results_raise_without_flag(self, results):
        manifest = load_manifest(builtin_manifest_path())
        mock_only = run_evaluation(manifest, parsers_spec="mock-oracle")
        with pytest.raises(RouterError, match="no eligible parser"):
            generate_router_config(mock_only)
        config = generate_router_config(mock_only, include_mock=True)
        assert config["default_parser"] == "mock-oracle"
