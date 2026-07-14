"""Parser-router config generation: benchmark results -> routing YAML.

The router config answers the practical question behind the benchmark:
"which parser should my pipeline send this document to?". Each track gets
the best-scoring real parser (mock baselines are excluded unless explicitly
included); file-extension hints are derived from the documents actually
evaluated in that track.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import yaml

from parse_arena import __version__


class RouterError(ValueError):
    """Raised when results cannot be turned into a router config."""


def generate_router_config(
    results: dict[str, Any], include_mock: bool = False
) -> dict[str, Any]:
    """Build the router config dict from a results document.

    Routing granularity is (track, file extension): for every extension seen
    in a track, the best-scoring eligible parser on those documents wins.
    Rules with the same winner inside a track are merged. Raises RouterError
    when the results contain no eligible parser at all.
    """
    leaderboard = results.get("leaderboard")
    if not isinstance(leaderboard, dict) or not leaderboard:
        raise RouterError("results contain no leaderboard; run 'parse-arena run' first")

    kinds = {p["name"]: p.get("kind", "real") for p in results.get("parsers", [])}

    # (track, extension, parser) -> scores of attempted documents
    cell_scores: dict[tuple[str, str, str], list[float]] = {}
    for entry in results.get("results", []):
        ext = entry.get("extension")
        parser = entry.get("parser")
        if not ext or not parser:
            continue
        if not include_mock and kinds.get(parser) == "mock":
            continue
        cell_scores.setdefault((entry["track"], ext, parser), []).append(
            float(entry.get("score", 0.0))
        )

    # best parser per (track, extension), deterministic tie-break by name
    best_cell: dict[tuple[str, str], tuple[str, float]] = {}
    for (track, ext, parser), scores in sorted(cell_scores.items()):
        mean = round(sum(scores) / len(scores), 4)
        current = best_cell.get((track, ext))
        # higher mean wins; on ties the lexicographically smaller name stays
        if current is None or mean > current[1]:
            best_cell[(track, ext)] = (parser, mean)

    rules: list[dict[str, Any]] = []
    unrouted: list[str] = []
    mean_by_parser: dict[str, list[float]] = {}
    for track in leaderboard:
        track_cells = {
            ext: winner for (t, ext), winner in best_cell.items() if t == track
        }
        if not track_cells:
            unrouted.append(track)
            continue
        # merge extensions that route to the same parser within the track
        by_parser: dict[str, dict[str, Any]] = {}
        for ext in sorted(track_cells):
            parser, score = track_cells[ext]
            slot = by_parser.setdefault(
                parser, {"track": track, "parser": parser, "extensions": [], "score": score}
            )
            slot["extensions"].append(ext)
            slot["score"] = round(min(slot["score"], score), 4)
            mean_by_parser.setdefault(parser, []).append(score)
        rules.extend(by_parser[p] for p in sorted(by_parser))

    if not rules:
        raise RouterError(
            "no eligible parser in any track (mock baselines are excluded; "
            "pass include_mock=True / --include-mock to allow them)"
        )

    default_parser = max(
        mean_by_parser.items(),
        key=lambda kv: (sum(kv[1]) / len(kv[1]), len(kv[1]), kv[0]),
    )[0]
    return {
        "version": 1,
        "generated_by": f"parse-arena {__version__}",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {
            "manifest": results.get("manifest", {}).get("name", ""),
            "generated_at": results.get("generated_at", ""),
        },
        "default_parser": default_parser,
        "rules": rules,
        "unrouted_tracks": unrouted,
    }


def render_router_yaml(config: dict[str, Any]) -> str:
    """Serialize the router config to YAML with stable key order."""
    return yaml.safe_dump(config, sort_keys=False, allow_unicode=True)
