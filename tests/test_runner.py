"""End-to-end evaluation tests on the built-in fixture dataset."""

import importlib.util

import pytest

from parse_arena.manifest import builtin_manifest_path, load_manifest
from parse_arena.runner import (
    normalize_metric,
    resolve_parsers,
    run_evaluation,
    score_from_metrics,
)

requires_pypdf = pytest.mark.skipif(
    importlib.util.find_spec("pypdf") is None,
    reason="pypdf is not installed (pip install -e '.[dev]' or '.[pdf]')",
)


@pytest.fixture(scope="module")
def results():
    manifest = load_manifest(builtin_manifest_path())
    return run_evaluation(manifest, parsers_spec="all", command="pytest run")


class TestRunEvaluation:
    def test_schema_top_level(self, results):
        assert results["schema_version"] == 1
        assert results["tool"]["name"] == "parse-arena"
        assert results["manifest"]["name"] == "parse-arena-builtin"
        assert results["command"] == "pytest run"

    def test_mock_oracle_scores_perfect_everywhere(self, results):
        oracle_rows = [r for r in results["results"] if r["parser"] == "mock-oracle"]
        assert len(oracle_rows) == 11  # every builtin document
        assert all(r["score"] == 1.0 for r in oracle_rows)

    @requires_pypdf
    def test_heavy_parsers_skipped_not_failed(self, results):
        skipped = {s["name"] for s in results["skipped_parsers"]}
        # In the reference environment the heavy extras are not installed.
        if skipped:
            assert skipped <= {"unstructured", "markitdown"}
            for s in results["skipped_parsers"]:
                assert s["reason"]

    def test_every_result_has_metrics_and_score(self, results):
        for row in results["results"]:
            assert "score" in row
            assert isinstance(row["metrics"], dict)
            if "error" not in row:
                assert row["metrics"], f"no metrics for {row}"

    @requires_pypdf
    def test_pypdf_penalized_on_table_track(self, results):
        row = next(
            r
            for r in results["results"]
            if r["parser"] == "pypdf" and r["doc_id"] == "en-pricing"
        )
        # pypdf recovers the text but not the table grid -> teds is 0.
        assert row["metrics"]["teds"] == 0.0
        assert row["score"] < 1.0

    def test_html_stdlib_recovers_merged_cell_table(self, results):
        row = next(
            r
            for r in results["results"]
            if r["parser"] == "html-stdlib" and r["doc_id"] == "en-schedule"
        )
        assert row["metrics"]["teds"] == 1.0

    @requires_pypdf
    def test_text_only_parser_penalized_on_merged_cell_pdf(self, results):
        row = next(
            r
            for r in results["results"]
            if r["parser"] == "pypdf" and r["doc_id"] == "en-tickets"
        )
        # pypdf keeps the text (cer == 0) but emits no table structure, so
        # the merged-cell table scores 0 — the honest failure mode.
        assert row["metrics"]["teds"] == 0.0
        assert row["metrics"]["cer"] == 0.0

    def test_form_track_scores_field_recall(self, results):
        row = next(
            r
            for r in results["results"]
            if r["parser"] == "html-stdlib" and r["doc_id"] == "en-form-application"
        )
        assert row["metrics"]["field_recall"] == 1.0

    def test_html_stdlib_wins_vertical_track(self, results):
        rows = results["leaderboard"]["ja-vertical"]
        real_rows = [r for r in rows if r["kind"] == "real"]
        assert real_rows[0]["parser"] == "html-stdlib"
        assert real_rows[0]["metrics"]["vertical_order_acc"] == 1.0

    def test_leaderboard_sorted_by_score(self, results):
        for rows in results["leaderboard"].values():
            scores = [(r["score"], r["coverage"]) for r in rows]
            assert scores == sorted(scores, reverse=True) or all(
                scores[i][0] >= scores[i + 1][0] for i in range(len(scores) - 1)
            )

    def test_coverage_reflects_unsupported_documents(self, results):
        en_text = results["leaderboard"]["en-text"]
        plaintext_row = next(r for r in en_text if r["parser"] == "plaintext")
        assert plaintext_row["coverage"] == 0.5  # txt yes, pdf no


class TestParserSelection:
    def test_explicit_parser_list(self):
        manifest = load_manifest(builtin_manifest_path())
        results = run_evaluation(manifest, parsers_spec="plaintext,mock-oracle")
        assert {p["name"] for p in results["parsers"]} == {"plaintext", "mock-oracle"}

    def test_unknown_parser_name_raises(self):
        with pytest.raises(KeyError, match="known parsers"):
            resolve_parsers("plaintext,bogus")

    def test_empty_spec_raises(self):
        with pytest.raises(KeyError):
            resolve_parsers(" , ")


class TestScoring:
    def test_normalize_error_rates_inverted(self):
        assert normalize_metric("cer", 0.0) == 1.0
        assert normalize_metric("cer", 1.0) == 0.0
        assert normalize_metric("wer", 0.25) == 0.75

    def test_normalize_tau_shifted(self):
        assert normalize_metric("reading_order_tau", 1.0) == 1.0
        assert normalize_metric("reading_order_tau", -1.0) == 0.0

    def test_score_is_mean_of_normalized(self):
        metrics = {"cer": 0.0, "teds": 0.5}
        assert score_from_metrics(metrics) == 0.75

    def test_score_empty_metrics_is_zero(self):
        assert score_from_metrics({}) == 0.0
