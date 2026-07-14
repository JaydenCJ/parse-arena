"""Generate the README demo chart (SVG) from a real results JSON.

Usage:
    parse-arena run --parsers all --out results.json
    python scripts/gen_demo_chart.py results.json docs/assets/demo.svg

The chart is a per-track horizontal bar chart of leaderboard scores, so the
README visual is itself reproducible benchmark output, not an illustration.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BAR_COLORS = {"real": "#2563eb", "mock": "#d97706", "optional": "#6b7280"}
ROW_H = 26
TRACK_GAP = 18
LEFT = 190
BAR_MAX = 470
WIDTH = 860


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render(results: dict) -> str:
    leaderboard: dict = results["leaderboard"]
    tracks = [t for t in results["manifest"]["tracks"] if leaderboard.get(t)]
    parts: list[str] = []
    y = 56
    for track in tracks:
        parts.append(
            f'<text x="24" y="{y}" font-size="15" font-weight="700" '
            f'fill="#111827">{_esc(track)}</text>'
        )
        y += 10
        for row in leaderboard[track]:
            bar_w = max(2, round(row["score"] * BAR_MAX))
            color = BAR_COLORS.get(row["kind"], "#6b7280")
            label = row["parser"] + (" (mock)" if row["kind"] == "mock" else "")
            parts.append(
                f'<text x="{LEFT - 10}" y="{y + 15}" font-size="13" '
                f'text-anchor="end" fill="#374151">{_esc(label)}</text>'
            )
            parts.append(
                f'<rect x="{LEFT}" y="{y + 3}" width="{bar_w}" height="15" '
                f'rx="3" fill="{color}" fill-opacity="0.9"/>'
            )
            coverage = ""
            if row["coverage"] < 1.0:
                coverage = f' &#183; coverage {row["coverage"]:.0%}'
            parts.append(
                f'<text x="{LEFT + bar_w + 8}" y="{y + 15}" font-size="12" '
                f'fill="#6b7280">{row["score"]:.3f}{coverage}</text>'
            )
            y += ROW_H
        y += TRACK_GAP
    height = y + 16
    tool = results.get("tool", {})
    subtitle = (
        f"dataset {results['manifest']['name']} &#183; "
        f"{results['manifest']['documents']} documents &#183; "
        f"{tool.get('name', 'parse-arena')} {tool.get('version', '')}"
    )
    body = "\n".join(parts)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" viewBox="0 0 {WIDTH} {height}" role="img" aria-label="parse-arena leaderboard chart">
<rect width="{WIDTH}" height="{height}" fill="#ffffff"/>
<text x="24" y="30" font-size="18" font-weight="700" fill="#111827" font-family="system-ui, sans-serif">parse-arena &#8212; per-track leaderboard</text>
<text x="24" y="47" font-size="12" fill="#6b7280" font-family="system-ui, sans-serif">{subtitle}</text>
<g font-family="system-ui, sans-serif">
{body}
</g>
</svg>
"""


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: gen_demo_chart.py <results.json> <output.svg>", file=sys.stderr)
        return 2
    results = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    out = Path(sys.argv[2])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(results), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
