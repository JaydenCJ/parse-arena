"""Static leaderboard site generator (results JSON -> self-contained HTML).

The generated site is a single index.html with inline CSS/JS (no CDN, no
external requests) plus a copy of the results JSON for auditability. Track
switching is client-side; the reproduce command is embedded verbatim.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

_METRIC_LABELS = {
    "cer": "CER",
    "wer": "WER",
    "teds": "TEDS",
    "reading_order_tau": "Order tau",
    "vertical_order_acc": "Vertical acc",
    "field_recall": "Field recall",
}

_CSS = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body {
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  margin: 0 auto; max-width: 980px; padding: 2rem 1rem; line-height: 1.5;
}
h1 { margin: 0 0 0.25rem; font-size: 1.6rem; }
.sub { color: gray; margin-bottom: 1.5rem; font-size: 0.9rem; }
.tabs { display: flex; flex-wrap: wrap; gap: 0.5rem; margin: 1rem 0; }
.tabs button {
  padding: 0.4rem 1rem; border: 1px solid gray; border-radius: 999px;
  background: transparent; cursor: pointer; font-size: 0.95rem; color: inherit;
}
.tabs button.active { background: #2563eb; border-color: #2563eb; color: white; }
.track-panel { display: none; }
.track-panel.active { display: block; }
table.board { border-collapse: collapse; width: 100%; margin: 0.5rem 0 1.5rem; }
table.board th, table.board td {
  border: 1px solid rgba(128,128,128,0.4); padding: 0.45rem 0.6rem;
  text-align: left; font-size: 0.92rem;
}
table.board th { background: rgba(128,128,128,0.15); }
td.num { text-align: right; font-variant-numeric: tabular-nums; }
.badge {
  display: inline-block; padding: 0 0.5rem; border-radius: 999px;
  font-size: 0.75rem; border: 1px solid gray;
}
.badge.mock { border-color: #d97706; color: #d97706; }
pre.cmd {
  background: rgba(128,128,128,0.12); padding: 0.75rem 1rem;
  border-radius: 8px; overflow-x: auto; font-size: 0.88rem;
}
.skips { font-size: 0.88rem; color: gray; }
footer { margin-top: 2rem; font-size: 0.85rem; color: gray; }
a { color: #2563eb; }
"""

_JS = """
function showTrack(track) {
  var panels = document.querySelectorAll('.track-panel');
  for (var i = 0; i < panels.length; i++) {
    panels[i].classList.toggle('active', panels[i].dataset.track === track);
  }
  var buttons = document.querySelectorAll('.tabs button');
  for (var j = 0; j < buttons.length; j++) {
    buttons[j].classList.toggle('active', buttons[j].dataset.track === track);
  }
}
document.addEventListener('DOMContentLoaded', function () {
  var buttons = document.querySelectorAll('.tabs button');
  for (var i = 0; i < buttons.length; i++) {
    buttons[i].addEventListener('click', function (event) {
      showTrack(event.currentTarget.dataset.track);
    });
  }
  if (buttons.length > 0) { showTrack(buttons[0].dataset.track); }
});
"""


def _esc(value: Any) -> str:
    return html.escape(str(value))


def _fmt(value: float) -> str:
    return f"{value:.3f}"


def _render_track_table(track: str, rows: list[dict[str, Any]], first: bool) -> str:
    metric_names: list[str] = []
    for row in rows:
        for name in row["metrics"]:
            if name not in metric_names:
                metric_names.append(name)
    head_cells = "".join(
        f"<th>{_esc(_METRIC_LABELS.get(m, m))}</th>" for m in metric_names
    )
    body_rows = []
    for rank, row in enumerate(rows, start=1):
        badge = (
            ' <span class="badge mock">mock</span>'
            if row["kind"] == "mock"
            else (' <span class="badge">optional</span>' if row["kind"] == "optional" else "")
        )
        metric_cells = "".join(
            f'<td class="num">{_fmt(row["metrics"][m]) if m in row["metrics"] else "&mdash;"}</td>'
            for m in metric_names
        )
        body_rows.append(
            "<tr>"
            f'<td class="num">{rank}</td>'
            f"<td>{_esc(row['parser'])}{badge}</td>"
            f'<td class="num"><strong>{_fmt(row["score"])}</strong></td>'
            f'<td class="num">{_fmt(row["coverage"])}</td>'
            f"{metric_cells}"
            "</tr>"
        )
    active = " active" if first else ""
    table_id = "leaderboard" if first else f"leaderboard-{track}"
    return (
        f'<section class="track-panel{active}" data-track="{_esc(track)}">\n'
        f"<h2>Track: {_esc(track)}</h2>\n"
        f'<table class="board" id="{_esc(table_id)}">\n'
        f'<thead><tr><th>#</th><th>Parser</th><th>Score</th><th>Coverage</th>{head_cells}</tr></thead>\n'
        f"<tbody>{''.join(body_rows)}</tbody>\n"
        "</table>\n"
        "</section>"
    )


def render_index_html(results: dict[str, Any]) -> str:
    """Render the whole leaderboard page as a self-contained HTML string."""
    manifest = results.get("manifest", {})
    leaderboard: dict[str, list[dict[str, Any]]] = results.get("leaderboard", {})
    tracks = [t for t in manifest.get("tracks", []) if t in leaderboard] or list(
        leaderboard
    )
    tabs = "".join(
        f'<button type="button" data-track="{_esc(track)}">{_esc(track)}</button>'
        for track in tracks
    )
    panels = "\n".join(
        _render_track_table(track, leaderboard.get(track, []), first=(i == 0))
        for i, track in enumerate(tracks)
    )
    command = results.get("command") or "parse-arena run --parsers all --out results.json"
    skipped = results.get("skipped_parsers", [])
    skipped_html = ""
    if skipped:
        items = "".join(
            f"<li><code>{_esc(s['name'])}</code> &mdash; {_esc(s['reason'])}</li>"
            for s in skipped
        )
        skipped_html = (
            '<details class="skips"><summary>Skipped parsers '
            f"({len(skipped)})</summary><ul>{items}</ul></details>"
        )
    tool = results.get("tool", {})
    generated_at = results.get("generated_at", "")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>parse-arena leaderboard &mdash; {_esc(manifest.get("name", ""))}</title>
<style>{_CSS}</style>
</head>
<body>
<h1>parse-arena leaderboard</h1>
<p class="sub">dataset: <strong>{_esc(manifest.get("name", ""))}</strong>
 &middot; documents: {_esc(manifest.get("documents", 0))}
 &middot; generated: {_esc(generated_at)}
 &middot; {_esc(tool.get("name", "parse-arena"))} {_esc(tool.get("version", ""))}</p>
<p>Reproduce this leaderboard:</p>
<pre class="cmd"><code>{_esc(command)}</code></pre>
<div class="tabs" role="tablist">{tabs}</div>
{panels}
{skipped_html}
<footer>
Raw data: <a href="results.json">results.json</a> &middot;
Scores are the mean of normalized metrics per document (see the
<a href="https://github.com/JaydenCJ/parse-arena">parse-arena README</a>
for metric definitions). Mock parsers are calibration baselines, not real parsers.
</footer>
<script>{_JS}</script>
</body>
</html>
"""


def generate_site(results: dict[str, Any], out_dir: str | Path) -> Path:
    """Write index.html + results.json into out_dir; returns the index path."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    index_path = out / "index.html"
    index_path.write_text(render_index_html(results), encoding="utf-8")
    (out / "results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return index_path
