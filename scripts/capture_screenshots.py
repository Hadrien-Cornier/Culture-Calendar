#!/usr/bin/env python3
"""Screenshot harness for Culture Calendar preview images.

Loads a handful of key pages in a headless Chrome via pyppeteer and
writes PNGs to ``docs/preview/`` so the site has visual previews for
social cards, docs, and human review after each long run.

Two modes:

* ``--offline`` (default off) serves the local ``docs/`` tree over a
  background ``http.server`` on a free port so screenshots reflect the
  working-tree state rather than the deployed site. The runner uses
  this mode because it does not push.
* Otherwise, screenshots come from ``--base-url`` (defaults to the
  GitHub Pages URL).

Design constraints mirror ``scripts/check_live_site.py``: no new
dependencies, system Chrome is preferred over the bundled Chromium,
and every side-effectful entry point takes a ``launch`` hook so the
tests can inject an ``AsyncMock`` instead of spawning a real browser.
"""

from __future__ import annotations

import argparse
import asyncio
import http.server
import logging
import socket
import socketserver
import sys
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable, Iterator, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = REPO_ROOT / "docs"
OUT_DIR = DOCS_DIR / "preview"

DEFAULT_BASE_URL = "https://hadrien-cornier.github.io/Culture-Calendar/"
NAV_TIMEOUT_MS = 30_000
DEFAULT_WAIT_MS = 800

DESKTOP_VIEWPORT: dict[str, Any] = {"width": 1280, "height": 800}
MOBILE_VIEWPORT: dict[str, Any] = {
    "width": 375,
    "height": 812,
    "isMobile": True,
    "hasTouch": True,
    "deviceScaleFactor": 2,
}

LOG = logging.getLogger("capture_screenshots")

_CANDIDATE_BROWSER_PATHS: tuple[str, ...] = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium-browser",
    "/usr/bin/chromium",
)


@dataclass(frozen=True)
class ShotSpec:
    """One screenshot to capture."""

    path: str
    filename: str
    mobile: bool = False
    wait_ms: int = DEFAULT_WAIT_MS
    full_page: bool = False


DEFAULT_SHOTS: tuple[ShotSpec, ...] = (
    ShotSpec(path="", filename="index-desktop.png"),
    ShotSpec(path="", filename="index-mobile.png", mobile=True),
    ShotSpec(path="how-it-works.html", filename="how-it-works-desktop.png"),
)


def _resolve_browser_executable() -> str | None:
    """Return a browser executablePath for pyppeteer, or ``None``.

    Mirrors the resolver in ``check_live_site.py`` so both tools share
    the same Chrome location heuristics.
    """
    import os

    env = os.environ.get("PYPPETEER_EXECUTABLE_PATH")
    if env and os.path.exists(env):
        return env
    for candidate in _CANDIDATE_BROWSER_PATHS:
        if os.path.exists(candidate):
            return candidate
    return None


def pick_free_port() -> int:
    """Return an ephemeral TCP port bound to localhost.

    The socket is closed before returning; there is an inherent race
    with anything else grabbing the port. For the single-threaded
    harness that's acceptable.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class _SilentHandler(http.server.SimpleHTTPRequestHandler):
    """SimpleHTTPRequestHandler that suppresses access logging."""

    def log_message(self, fmt: str, *args: object) -> None:  # noqa: A003
        return


def _build_handler(directory: Path) -> type[http.server.SimpleHTTPRequestHandler]:
    root = str(directory.resolve())

    class _Handler(_SilentHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=root, **kwargs)

    return _Handler


@contextmanager
def serve_directory(
    directory: Path, port: int | None = None
) -> Iterator[tuple[int, str]]:
    """Serve ``directory`` on a background thread.

    Yields ``(port, base_url)`` where ``base_url`` ends with a slash so
    callers can safely ``base_url + path.lstrip('/')``.
    """
    bind_port = pick_free_port() if port is None else port
    handler_cls = _build_handler(directory)
    httpd = socketserver.TCPServer(("127.0.0.1", bind_port), handler_cls)
    bound_port = int(httpd.server_address[1])
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield bound_port, f"http://127.0.0.1:{bound_port}/"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


def resolve_url(base_url: str, path: str) -> str:
    """Join ``base_url`` and ``path`` without collapsing the scheme slash."""
    base = base_url if base_url.endswith("/") else base_url + "/"
    return base + path.lstrip("/")


async def capture_one(
    url: str,
    dest: Path,
    *,
    mobile: bool = False,
    wait_ms: int = DEFAULT_WAIT_MS,
    full_page: bool = False,
    launch: Callable[..., Awaitable[Any]] | None = None,
) -> Path:
    """Open ``url`` in headless Chrome and save a PNG at ``dest``.

    The ``launch`` hook lets unit tests inject an ``AsyncMock`` so they
    never touch a real browser.
    """
    if launch is None:
        from pyppeteer import launch as _launch  # imported lazily for tests

        launch = _launch
    launch_kwargs: dict[str, Any] = {
        "headless": True,
        "args": ["--no-sandbox"],
    }
    exe = _resolve_browser_executable()
    if exe:
        launch_kwargs["executablePath"] = exe
    browser = await launch(**launch_kwargs)
    try:
        page = await browser.newPage()
        viewport = MOBILE_VIEWPORT if mobile else DESKTOP_VIEWPORT
        await page.setViewport(viewport)
        await page.goto(url, waitUntil="networkidle2", timeout=NAV_TIMEOUT_MS)
        if wait_ms:
            await asyncio.sleep(wait_ms / 1000.0)
        dest.parent.mkdir(parents=True, exist_ok=True)
        await page.screenshot(
            {"path": str(dest), "fullPage": bool(full_page)}
        )
        return dest
    finally:
        await browser.close()


def capture_all(
    base_url: str,
    shots: Iterable[ShotSpec],
    out_dir: Path,
    *,
    launch: Callable[..., Awaitable[Any]] | None = None,
    run: Callable[[Awaitable[Any]], Any] = asyncio.run,
) -> list[Path]:
    """Capture every shot sequentially. Returns the list of PNG paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for shot in shots:
        url = resolve_url(base_url, shot.path)
        dest = out_dir / shot.filename
        run(
            capture_one(
                url,
                dest,
                mobile=shot.mobile,
                wait_ms=shot.wait_ms,
                full_page=shot.full_page,
                launch=launch,
            )
        )
        written.append(dest)
    return written


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="capture_screenshots.py",
        description=(
            "Capture preview PNGs of key Culture Calendar pages via "
            "pyppeteer. Use --offline to serve docs/ locally."
        ),
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help=(
            "Serve the local docs/ tree over an ephemeral http.server "
            "and screenshot that instead of the deployed site."
        ),
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=(
            "Base URL to screenshot when --offline is not set "
            "(default: %(default)s)."
        ),
    )
    parser.add_argument(
        "--docs",
        type=Path,
        default=DOCS_DIR,
        help="Docs directory to serve when --offline (default: %(default)s).",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=OUT_DIR,
        help="Output directory for preview PNGs (default: %(default)s).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress the summary line on stdout.",
    )
    return parser.parse_args(argv)


def run(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    shots = DEFAULT_SHOTS
    out_dir: Path = args.out_dir

    if args.offline:
        if not args.docs.is_dir():
            print(f"error: docs dir not found: {args.docs}", file=sys.stderr)
            return 2
        with serve_directory(args.docs) as (_, base_url):
            paths = capture_all(base_url, shots, out_dir)
    else:
        paths = capture_all(args.base_url, shots, out_dir)

    if not args.quiet:
        print(f"Wrote {len(paths)} screenshots to {out_dir}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return run(argv)


if __name__ == "__main__":
    sys.exit(main())
