# Contributing to parse-arena

Thanks for considering a contribution. This project aims to stay a small,
auditable benchmark harness — neutrality and reproducibility beat feature
count.

## Development setup

```bash
git clone https://github.com/JaydenCJ/parse-arena.git
cd parse-arena
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest
bash scripts/smoke.sh
```

The `dev` extra already includes the `pdf` extra's dependency
(pypdf), so `pip install -e ".[dev]"` alone runs the full test suite — in an
environment without pypdf the pdf-dependent tests are skipped automatically.

Requirements: Python 3.10+. No network access is needed to run the tests or
the smoke script once dependencies are installed.

## What contributions are welcome

- **New parser adapters.** Subclass `ParserAdapter` in
  `src/parse_arena/adapters/`, register it with `@register`, and keep heavy
  dependencies behind a lazy import with a helpful `availability()` reason.
  Add tests that run without the heavy dependency installed.
- **New dataset documents.** Fixtures must be synthetic or public-domain,
  small (well under 1 MB), and come with a ground-truth JSON. Generated
  binaries (like the PDF fixtures) need a deterministic generator script in
  `scripts/`.
- **Metric improvements.** Metrics are documented formulas; any change must
  update the README definition, the docstring and the tests together.

## Ground rules

- Code and comments are written in English.
- Every behavior change needs a test; `pytest` and `bash scripts/smoke.sh`
  must pass before review.
- No telemetry, no network calls at import or run time, and servers bind
  `127.0.0.1` by default.
- Benchmarks must stay vendor-neutral: adapters are configured the way the
  parser's own documentation recommends, and scoring code must not special-
  case any parser.

## Reporting issues

Please include the parse-arena version (`parse-arena --version`), the exact
command you ran, and — for scoring disputes — the results JSON, which contains
everything needed to reproduce the number.
