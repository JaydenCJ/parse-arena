"""CLI tests: exit codes, error messages, and the full run/report/router chain.

The chain test mirrors the README quickstart commands verbatim (same
subcommands and flags), so the documentation is covered by tests.
"""

import http.client
import json
import threading

import pytest
import yaml

from parse_arena import __version__
from parse_arena.cli import main
from parse_arena.serve import make_server


class TestBasics:
    def test_version_flag(self, capsys):
        with pytest.raises(SystemExit) as excinfo:
            main(["--version"])
        assert excinfo.value.code == 0
        assert f"parse-arena {__version__}" in capsys.readouterr().out

    def test_help_flag(self, capsys):
        with pytest.raises(SystemExit) as excinfo:
            main(["--help"])
        assert excinfo.value.code == 0
        out = capsys.readouterr().out
        for sub in ("run", "report", "serve", "router", "parsers"):
            assert sub in out

    def test_no_command_is_usage_error(self):
        with pytest.raises(SystemExit) as excinfo:
            main([])
        assert excinfo.value.code == 2

    def test_parsers_subcommand_lists_availability(self, capsys):
        assert main(["parsers"]) == 0
        out = capsys.readouterr().out
        assert "plaintext" in out
        assert "unavailable" in out or "available" in out


class TestErrorHandling:
    def test_run_with_missing_manifest_exits_1(self, capsys):
        assert main(["run", "--manifest", "/nonexistent/manifest.yaml"]) == 1
        err = capsys.readouterr().err
        assert err.startswith("error:")
        assert "not found" in err

    def test_run_with_unknown_parser_exits_1(self, capsys, tmp_path):
        out = tmp_path / "r.json"
        assert main(["run", "--parsers", "bogus", "--out", str(out)]) == 1
        assert "known parsers" in capsys.readouterr().err

    def test_report_with_missing_results_exits_1(self, capsys, tmp_path):
        assert main(["report", str(tmp_path / "missing.json")]) == 1
        assert "not found" in capsys.readouterr().err

    def test_report_with_invalid_json_exits_1(self, capsys, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{broken", encoding="utf-8")
        assert main(["report", str(bad)]) == 1
        assert "not valid JSON" in capsys.readouterr().err

    def test_report_with_wrong_schema_exits_1(self, capsys, tmp_path):
        bad = tmp_path / "other.json"
        bad.write_text('{"something": "else"}', encoding="utf-8")
        assert main(["report", str(bad)]) == 1
        assert "leaderboard" in capsys.readouterr().err

    def test_serve_with_missing_dir_exits_1(self, capsys, tmp_path):
        assert main(["serve", str(tmp_path / "nope")]) == 1
        assert "not found" in capsys.readouterr().err

    def test_serve_without_index_exits_1(self, capsys, tmp_path):
        assert main(["serve", str(tmp_path)]) == 1
        assert "index.html" in capsys.readouterr().err


class TestFullChain:
    """run -> report -> router, exactly as documented in the README."""

    def test_run_report_router(self, tmp_path, capsys):
        results_path = tmp_path / "results.json"
        site_dir = tmp_path / "site"
        router_path = tmp_path / "router.yaml"

        assert main(["run", "--parsers", "all", "--out", str(results_path)]) == 0
        results = json.loads(results_path.read_text("utf-8"))
        assert results["schema_version"] == 1
        assert results["leaderboard"]

        assert main(["report", str(results_path), "--out", str(site_dir)]) == 0
        index_html = (site_dir / "index.html").read_text("utf-8")
        assert 'id="leaderboard"' in index_html
        assert "ja-vertical" in index_html

        assert main(["router", str(results_path), "--out", str(router_path)]) == 0
        config = yaml.safe_load(router_path.read_text("utf-8"))
        assert config["version"] == 1
        assert config["rules"]
        out = capsys.readouterr().out
        assert "router config written" in out


class TestServe:
    def test_server_binds_loopback_and_serves_site(self, tmp_path):
        (tmp_path / "index.html").write_text(
            "<html><body><table id=\"leaderboard\"></table></body></html>",
            encoding="utf-8",
        )
        httpd = make_server(tmp_path, host="127.0.0.1", port=0)
        assert httpd.server_address[0] == "127.0.0.1"
        port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            conn.request("GET", "/index.html")
            response = conn.getresponse()
            body = response.read().decode("utf-8")
            assert response.status == 200
            assert 'id="leaderboard"' in body
        finally:
            httpd.shutdown()
            httpd.server_close()
