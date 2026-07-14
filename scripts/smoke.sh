#!/usr/bin/env bash
# Smoke test: run -> report -> router -> serve, with self-assertions.
# Requirements: bash, python3 (>= 3.10). No network access is needed when the
# project venv (.venv) already exists; the fallback venv installs the package
# offline from the source tree (PyYAML comes from system site-packages).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/parse-arena-smoke.XXXXXX")"
SERVER_PID=""

cleanup() {
  if [ -n "${SERVER_PID}" ] && kill -0 "${SERVER_PID}" 2>/dev/null; then
    kill "${SERVER_PID}" 2>/dev/null || true
    wait "${SERVER_PID}" 2>/dev/null || true
  fi
  rm -rf "${WORK}"
}
trap cleanup EXIT

fail() {
  echo "SMOKE FAIL: $1" >&2
  exit 1
}

# --- locate or build a Python environment with parse_arena importable ------
PYBIN=""
if [ -x "${ROOT}/.venv/bin/python" ] \
   && "${ROOT}/.venv/bin/python" -c 'import parse_arena' 2>/dev/null; then
  PYBIN="${ROOT}/.venv/bin/python"
  echo "[smoke] using existing venv: ${PYBIN}"
else
  echo "[smoke] creating throwaway venv (offline, system site-packages)"
  python3 -m venv --system-site-packages "${WORK}/venv"
  "${WORK}/venv/bin/pip" install --quiet --no-index --no-build-isolation "${ROOT}" \
    || fail "offline install failed (PyYAML and setuptools must be importable)"
  PYBIN="${WORK}/venv/bin/python"
fi

cd "${WORK}"

# --- 1. run: evaluate all available parsers on the builtin dataset ---------
"${PYBIN}" -m parse_arena.cli run --parsers all --out results.json
[ -f results.json ] || fail "results.json was not created"

"${PYBIN}" - <<'PYCHECK'
import json, sys
data = json.load(open("results.json", encoding="utf-8"))
assert data.get("schema_version") == 1, "unexpected schema_version"
assert data.get("results"), "results list is empty"
boards = data.get("leaderboard") or {}
expected = {"en-text", "en-table", "en-form", "ja-vertical", "ja-receipt"}
assert expected <= set(boards), f"missing tracks: {expected - set(boards)}"
for track in expected:
    assert boards[track], f"empty leaderboard for {track}"
print("[smoke] results.json structure OK "
      f"({len(data['results'])} rows, {len(boards)} tracks)")
PYCHECK

# --- 2. report: static leaderboard site ------------------------------------
"${PYBIN}" -m parse_arena.cli report results.json --out site
[ -f site/index.html ] || fail "site/index.html was not created"
grep -q 'id="leaderboard"' site/index.html || fail "leaderboard table missing from HTML"
grep -q 'data-track="ja-vertical"' site/index.html || fail "ja-vertical track missing from HTML"
grep -q 'parse-arena run' site/index.html || fail "reproduce command missing from HTML"
[ -f site/results.json ] || fail "results.json copy missing from site"
echo "[smoke] leaderboard HTML OK"

# --- 3. router: parser routing config --------------------------------------
"${PYBIN}" -m parse_arena.cli router results.json --out router.yaml
[ -f router.yaml ] || fail "router.yaml was not created"
"${PYBIN}" - <<'PYCHECK'
import yaml
config = yaml.safe_load(open("router.yaml", encoding="utf-8"))
assert config["version"] == 1, "router version mismatch"
assert config["rules"], "router has no rules"
tracks = {rule["track"] for rule in config["rules"]}
assert "ja-vertical" in tracks, "ja-vertical track not routed"
assert all(rule["parser"] != "mock-oracle" for rule in config["rules"]), \
    "mock parser leaked into router rules"
print(f"[smoke] router.yaml OK ({len(config['rules'])} rules, "
      f"default={config['default_parser']})")
PYCHECK

# --- 4. serve: local preview answers on 127.0.0.1 ---------------------------
PORT=8321
"${PYBIN}" -m parse_arena.cli serve site --port "${PORT}" >server.log 2>&1 &
SERVER_PID=$!
for _ in $(seq 1 20); do
  if "${PYBIN}" - "${PORT}" <<'PYCHECK' 2>/dev/null
import sys, urllib.request
port = sys.argv[1]
body = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2).read().decode()
assert 'id="leaderboard"' in body
PYCHECK
  then
    echo "[smoke] GET http://127.0.0.1:${PORT}/ -> 200 with leaderboard table"
    break
  fi
  kill -0 "${SERVER_PID}" 2>/dev/null || fail "serve process died (see server.log)"
  sleep 0.5
done
"${PYBIN}" - "${PORT}" <<'PYCHECK' || fail "served page assertion failed"
import sys, urllib.request
port = sys.argv[1]
body = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2).read().decode()
assert 'id="leaderboard"' in body
PYCHECK

echo "SMOKE OK"
