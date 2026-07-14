"""parse-arena command line interface.

Exit codes: 0 success, 1 runtime failure (bad input file, invalid manifest,
router impossible), 2 usage error (argparse). All errors go to stderr.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from parse_arena import __version__
from parse_arena.adapters import all_adapters
from parse_arena.manifest import ManifestError, builtin_manifest_path, load_manifest
from parse_arena.report import generate_site
from parse_arena.router import RouterError, generate_router_config, render_router_yaml
from parse_arena.runner import run_evaluation
from parse_arena.serve import DEFAULT_HOST, DEFAULT_PORT, serve_forever


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="parse-arena",
        description=(
            "Neutral benchmark harness for document parsers: run evaluations, "
            "build a static leaderboard site, and generate parser-router configs."
        ),
    )
    parser.add_argument(
        "--version", action="version", version=f"parse-arena {__version__}"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="evaluate parsers against a dataset manifest")
    p_run.add_argument(
        "--manifest",
        default=None,
        help="dataset manifest YAML (default: built-in fixture dataset)",
    )
    p_run.add_argument(
        "--parsers",
        default="all",
        help="'all' or comma-separated adapter names (default: all)",
    )
    p_run.add_argument(
        "--out", default="results.json", help="output results JSON path"
    )

    p_report = sub.add_parser(
        "report", help="render a results JSON into a static leaderboard site"
    )
    p_report.add_argument("results", help="results JSON produced by 'parse-arena run'")
    p_report.add_argument("--out", default="site", help="output site directory")

    p_serve = sub.add_parser("serve", help="preview a generated site locally")
    p_serve.add_argument("site", help="site directory produced by 'parse-arena report'")
    p_serve.add_argument("--host", default=DEFAULT_HOST, help="bind address (default: 127.0.0.1)")
    p_serve.add_argument("--port", type=int, default=DEFAULT_PORT, help="port (default: 8000)")

    p_router = sub.add_parser(
        "router", help="generate a parser-router config YAML from results"
    )
    p_router.add_argument("results", help="results JSON produced by 'parse-arena run'")
    p_router.add_argument("--out", default="router.yaml", help="output YAML path")
    p_router.add_argument(
        "--include-mock",
        action="store_true",
        help="allow mock baseline parsers in the routing rules",
    )

    sub.add_parser("parsers", help="list registered parser adapters and availability")
    return parser


def _load_results(path_str: str) -> dict:
    path = Path(path_str)
    if not path.is_file():
        raise FileNotFoundError(f"results file not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"results file is not valid JSON: {exc}") from exc
    if not isinstance(data, dict) or "leaderboard" not in data:
        raise ValueError(
            f"{path} does not look like parse-arena results (missing 'leaderboard')"
        )
    return data


def _cmd_run(args: argparse.Namespace) -> int:
    manifest_path = args.manifest or builtin_manifest_path()
    manifest = load_manifest(manifest_path)
    command = f"parse-arena run --parsers {args.parsers} --out {args.out}"
    if args.manifest:
        command += f" --manifest {args.manifest}"
    results = run_evaluation(manifest, parsers_spec=args.parsers, command=command)
    out_path = Path(args.out)
    if out_path.parent and not out_path.parent.exists():
        out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    n_results = len(results["results"])
    n_parsers = len(results["parsers"])
    print(
        f"evaluated {n_parsers} parser(s) on {results['manifest']['documents']} "
        f"document(s): {n_results} result rows -> {out_path}"
    )
    for skip in results["skipped_parsers"]:
        print(f"skipped {skip['name']}: {skip['reason']}", file=sys.stderr)
    for track, rows in results["leaderboard"].items():
        if rows:
            top = rows[0]
            print(f"  [{track}] best: {top['parser']} (score {top['score']:.3f})")
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    results = _load_results(args.results)
    index_path = generate_site(results, args.out)
    print(f"leaderboard site written to {index_path}")
    print(f"preview: parse-arena serve {args.out}")
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    site = Path(args.site)
    if not site.is_dir():
        raise FileNotFoundError(f"site directory not found: {site}")
    if not (site / "index.html").is_file():
        raise FileNotFoundError(
            f"{site} has no index.html; generate it with 'parse-arena report'"
        )
    serve_forever(site, args.host, args.port)
    return 0


def _cmd_router(args: argparse.Namespace) -> int:
    results = _load_results(args.results)
    config = generate_router_config(results, include_mock=args.include_mock)
    yaml_text = render_router_yaml(config)
    out_path = Path(args.out)
    out_path.write_text(yaml_text, encoding="utf-8")
    print(f"router config written to {out_path}")
    print(f"default parser: {config['default_parser']}")
    for rule in config["rules"]:
        print(f"  [{rule['track']}] -> {rule['parser']} (score {rule['score']:.3f})")
    return 0


def _cmd_parsers(_: argparse.Namespace) -> int:
    for adapter in all_adapters():
        avail = adapter.availability()
        status = "available" if avail.available else f"unavailable ({avail.reason})"
        exts = ",".join(adapter.extensions)
        print(f"{adapter.name:<14} kind={adapter.kind:<8} ext={exts:<20} {status}")
    return 0


_HANDLERS = {
    "run": _cmd_run,
    "report": _cmd_report,
    "serve": _cmd_serve,
    "router": _cmd_router,
    "parsers": _cmd_parsers,
}


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return _HANDLERS[args.command](args)
    except (ManifestError, RouterError, FileNotFoundError, ValueError, KeyError) as exc:
        message = exc.args[0] if exc.args else str(exc)
        print(f"error: {message}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
