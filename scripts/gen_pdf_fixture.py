"""Regenerate the built-in PDF fixtures (deterministic, no dependencies).

Writes minimal uncompressed PDFs (Helvetica, one page, one line per text
operation) so the fixtures are reproducible from source and reviewable as
mostly-ASCII bytes. Usage:

    python scripts/gen_pdf_fixture.py [output-directory]
"""

from __future__ import annotations

import sys
from pathlib import Path

FIXTURES: dict[str, list[str]] = {
    "en_invoice.pdf": [
        "PARSE ARENA INVOICE 2026-0042",
        "Date: 2026-06-30",
        "Bill to: Example Research Lab",
        "Item: document parsing benchmark subscription",
        "Quantity: 3",
        "Unit price: 42.00 USD",
        "Total: 126.00 USD",
        "Payment due within 30 days.",
    ],
    "en_pricing.pdf": [
        "Plan Comparison 2026",
        "Plan Monthly price Documents",
        "Basic 9 USD 1000",
        "Pro 29 USD 10000",
        "Enterprise 99 USD unlimited",
        "All plans include the public regression dataset.",
    ],
    # Merged-cell table rendered as text lines: the visual header row spans
    # two quarters per half ("2026 H1" covers Q1+Q2). Ground truth stores the
    # spans explicitly, so table-structure-aware parsers are rewarded and
    # text-only extraction honestly scores TEDS = 0 on this document.
    "en_tickets.pdf": [
        "Ticket Volume by Quarter",
        "Team 2026 H1 2026 H2",
        "Q1 Q2 Q3 Q4",
        "Alpha 10 12 14 16",
        "Bravo 8 9 11 12",
        "Each half-year header cell spans two quarter columns.",
    ],
}


def _content_stream(lines: list[str]) -> bytes:
    ops = ["BT", "/F1 12 Tf", "72 720 Td"]
    for i, line in enumerate(lines):
        if i > 0:
            ops.append("0 -18 Td")
        escaped = line.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
        ops.append(f"({escaped}) Tj")
    ops.append("ET")
    return "\n".join(ops).encode("ascii")


def build_pdf(lines: list[str]) -> bytes:
    content = _content_stream(lines)
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>"
        ),
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for num, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % num
        out += body
        out += b"\nendobj\n"
    xref_pos = len(out)
    out += b"xref\n0 %d\n" % (len(objects) + 1)
    out += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\n" % (len(objects) + 1)
    out += b"startxref\n%d\n%%%%EOF\n" % xref_pos
    return bytes(out)


def main() -> int:
    default_dir = (
        Path(__file__).parent.parent / "src" / "parse_arena" / "fixtures" / "docs"
    )
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else default_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, lines in FIXTURES.items():
        target = out_dir / name
        target.write_bytes(build_pdf(lines))
        print(f"wrote {target} ({target.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
