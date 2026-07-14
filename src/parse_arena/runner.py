"""Evaluation runner: parsers x documents -> scored results dict.

The output dict is the single source of truth consumed by the report and
router generators; its layout is versioned via schema_version.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from parse_arena import __version__
from parse_arena.adapters import ParserAdapter, all_adapters, get_adapter
from parse_arena.adapters.base import AdapterError, ParseResult
from parse_arena.manifest import Document, Manifest
from parse_arena.metrics import (
    cer,
    field_recall,
    reading_order_tau,
    teds,
    vertical_order_accuracy,
    wer,
)

SCHEMA_VERSION = 1


def compute_metrics(result: ParseResult, doc: Document) -> dict[str, float]:
    """All metrics applicable to this document's ground truth.

    Which metrics apply is driven purely by what the ground truth provides:
    text -> cer/wer, blocks -> reading-order tau, vertical blocks ->
    vertical-order accuracy, tables -> teds, fields -> field recall.
    """
    gt = doc.ground_truth
    metrics: dict[str, float] = {}
    if gt.text:
        metrics["cer"] = round(cer(gt.text, result.text), 4)
        metrics["wer"] = round(wer(gt.text, result.text), 4)
    if gt.blocks:
        metrics["reading_order_tau"] = round(
            reading_order_tau(result.blocks, gt.blocks), 4
        )
        if gt.vertical:
            metrics["vertical_order_acc"] = round(
                vertical_order_accuracy(result.blocks, gt.blocks), 4
            )
    if gt.tables:
        metrics["teds"] = round(teds(result.tables, gt.tables), 4)
    if gt.fields:
        metrics["field_recall"] = round(field_recall(result.text, gt.fields), 4)
    return metrics


def normalize_metric(name: str, value: float) -> float:
    """Map a raw metric value onto [0, 1] where higher is better."""
    if name in ("cer", "wer"):
        return max(0.0, 1.0 - value)
    if name == "reading_order_tau":
        return (value + 1.0) / 2.0
    return max(0.0, min(1.0, value))


def score_from_metrics(metrics: dict[str, float]) -> float:
    """Document score: mean of the normalized metric values."""
    if not metrics:
        return 0.0
    values = [normalize_metric(name, value) for name, value in metrics.items()]
    return round(sum(values) / len(values), 4)


def resolve_parsers(spec: str) -> tuple[list[ParserAdapter], list[dict[str, str]]]:
    """Resolve a --parsers spec into (usable adapters, skipped records).

    spec is 'all' or a comma-separated list of adapter names. Unavailable
    adapters (missing optional dependency) are skipped with a reason instead
    of failing the run. Unknown names raise KeyError.
    """
    if spec.strip() == "all":
        candidates = all_adapters()
    else:
        names = [n.strip() for n in spec.split(",") if n.strip()]
        if not names:
            raise KeyError("no parser names given")
        candidates = [get_adapter(name) for name in names]
    usable: list[ParserAdapter] = []
    skipped: list[dict[str, str]] = []
    for adapter in candidates:
        avail = adapter.availability()
        if avail.available:
            usable.append(adapter)
        else:
            skipped.append({"name": adapter.name, "reason": avail.reason})
    return usable, skipped


def run_evaluation(
    manifest: Manifest, parsers_spec: str = "all", command: str = ""
) -> dict[str, Any]:
    """Evaluate the selected parsers on every manifest document."""
    adapters, skipped = resolve_parsers(parsers_spec)
    results: list[dict[str, Any]] = []
    for adapter in adapters:
        for doc in manifest.documents:
            if not adapter.supports(doc.path):
                continue
            entry: dict[str, Any] = {
                "parser": adapter.name,
                "doc_id": doc.doc_id,
                "track": doc.track,
                "extension": doc.extension,
            }
            started = time.perf_counter()
            try:
                parsed = adapter.parse(doc.path)
            except AdapterError as exc:
                entry.update(
                    {"error": str(exc), "metrics": {}, "score": 0.0, "duration_ms": 0.0}
                )
                results.append(entry)
                continue
            duration_ms = (time.perf_counter() - started) * 1000.0
            metrics = compute_metrics(parsed, doc)
            entry.update(
                {
                    "metrics": metrics,
                    "score": score_from_metrics(metrics),
                    "duration_ms": round(duration_ms, 2),
                }
            )
            results.append(entry)

    leaderboard = build_leaderboard(manifest, adapters, results)
    return {
        "schema_version": SCHEMA_VERSION,
        "tool": {"name": "parse-arena", "version": __version__},
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "command": command,
        "manifest": {
            "name": manifest.name,
            "path": str(manifest.path),
            "documents": len(manifest.documents),
            "tracks": list(manifest.tracks),
        },
        "parsers": [
            {
                "name": a.name,
                "kind": a.kind,
                "version": a.version(),
                "description": a.description,
            }
            for a in adapters
        ],
        "skipped_parsers": skipped,
        "results": results,
        "leaderboard": leaderboard,
    }


def build_leaderboard(
    manifest: Manifest,
    adapters: list[ParserAdapter],
    results: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Per-track ranking: mean score over the documents a parser attempted.

    coverage = attempted documents / documents in the track, reported so a
    parser that only handles a subset is visibly flagged. Ranking sorts by
    score desc, then coverage desc, then name for determinism.
    """
    leaderboard: dict[str, list[dict[str, Any]]] = {}
    for track in manifest.tracks:
        track_docs = manifest.by_track(track)
        rows: list[dict[str, Any]] = []
        for adapter in adapters:
            entries = [
                r for r in results if r["parser"] == adapter.name and r["track"] == track
            ]
            if not entries:
                continue
            mean_score = sum(e["score"] for e in entries) / len(entries)
            metric_sums: dict[str, list[float]] = {}
            for e in entries:
                for name, value in e["metrics"].items():
                    metric_sums.setdefault(name, []).append(value)
            rows.append(
                {
                    "parser": adapter.name,
                    "kind": adapter.kind,
                    "score": round(mean_score, 4),
                    "coverage": round(len(entries) / len(track_docs), 4),
                    "documents": len(entries),
                    "errors": sum(1 for e in entries if "error" in e),
                    "metrics": {
                        name: round(sum(vals) / len(vals), 4)
                        for name, vals in sorted(metric_sums.items())
                    },
                }
            )
        rows.sort(key=lambda r: (-r["score"], -r["coverage"], r["parser"]))
        leaderboard[track] = rows
    return leaderboard
