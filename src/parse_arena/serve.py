"""Local preview server for the generated static site (binds 127.0.0.1)."""

from __future__ import annotations

import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000


class _QuietHandler(SimpleHTTPRequestHandler):
    """Request handler with one-line access logs (no client noise)."""

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        print(f"[serve] {self.address_string()} {format % args}")


def make_server(
    site_dir: str | Path, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT
) -> ThreadingHTTPServer:
    """Create (but do not start) an HTTP server rooted at site_dir.

    The default bind address is loopback only; exposing the site to a network
    is an explicit user decision via --host.
    """
    directory = str(Path(site_dir).resolve())
    handler = functools.partial(_QuietHandler, directory=directory)
    return ThreadingHTTPServer((host, port), handler)


def serve_forever(site_dir: str | Path, host: str, port: int) -> None:
    httpd = make_server(site_dir, host, port)
    actual_port = httpd.server_address[1]
    print(f"[serve] serving {Path(site_dir).resolve()} at http://{host}:{actual_port}/")
    print("[serve] press Ctrl-C to stop")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[serve] stopped")
    finally:
        httpd.server_close()
