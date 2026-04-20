"""Unit tests for ``scripts/capture_screenshots.py``.

Pyppeteer is fully mocked — tests inject an ``AsyncMock`` launcher
through the ``launch`` parameter so no real browser is spawned.

A separate integration-style test verifies the local ``http.server``
helper serves files from the provided directory and that ``--help``
exits cleanly without needing a browser.
"""
from __future__ import annotations

import asyncio
import importlib.util
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "capture_screenshots.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("capture_screenshots", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["capture_screenshots"] = module
    spec.loader.exec_module(module)
    return module


cls = _load_module()


def _make_fake_launcher():
    """Build an AsyncMock launcher with a mocked browser + page.

    Returns (launcher, browser, page) so tests can assert on the
    recorded calls (viewport, goto, screenshot path).
    """
    page = MagicMock()
    page.setViewport = AsyncMock()
    page.goto = AsyncMock()
    page.screenshot = AsyncMock()
    browser = MagicMock()
    browser.newPage = AsyncMock(return_value=page)
    browser.close = AsyncMock()
    launcher = AsyncMock(return_value=browser)
    return launcher, browser, page


# --- CLI surface ----------------------------------------------------------


def test_cli_help_exits_zero():
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "--offline" in result.stdout
    assert "--out-dir" in result.stdout


def test_cli_offline_errors_when_docs_dir_missing(tmp_path, capsys):
    missing = tmp_path / "nope"
    rc = cls.run(["--offline", "--docs", str(missing), "--out-dir", str(tmp_path / "preview")])
    assert rc == 2
    captured = capsys.readouterr()
    assert "docs dir not found" in captured.err


# --- URL resolution -------------------------------------------------------


def test_resolve_url_adds_slash_when_missing():
    url = cls.resolve_url("http://127.0.0.1:8080", "weekly/2026-W17.html")
    assert url == "http://127.0.0.1:8080/weekly/2026-W17.html"


def test_resolve_url_preserves_trailing_slash():
    url = cls.resolve_url("http://127.0.0.1:8080/", "index.html")
    assert url == "http://127.0.0.1:8080/index.html"


def test_resolve_url_strips_leading_slash_of_path():
    url = cls.resolve_url("http://127.0.0.1:8080", "/weekly/x.html")
    assert url == "http://127.0.0.1:8080/weekly/x.html"


# --- capture_one ----------------------------------------------------------


def test_capture_one_writes_to_dest(tmp_path):
    launcher, browser, page = _make_fake_launcher()
    dest = tmp_path / "preview" / "index-desktop.png"
    result = asyncio.run(
        cls.capture_one(
            "http://127.0.0.1/",
            dest,
            wait_ms=0,
            launch=launcher,
        )
    )
    assert result == dest
    # parent dir auto-created
    assert dest.parent.is_dir()
    # screenshot called with path=dest
    screenshot_opts = page.screenshot.call_args.args[0]
    assert screenshot_opts["path"] == str(dest)
    assert screenshot_opts["fullPage"] is False
    browser.close.assert_awaited()


def test_capture_one_full_page_option_propagates(tmp_path):
    launcher, _, page = _make_fake_launcher()
    dest = tmp_path / "out.png"
    asyncio.run(
        cls.capture_one(
            "http://127.0.0.1/",
            dest,
            wait_ms=0,
            full_page=True,
            launch=launcher,
        )
    )
    opts = page.screenshot.call_args.args[0]
    assert opts["fullPage"] is True


def test_capture_one_mobile_viewport(tmp_path):
    launcher, _, page = _make_fake_launcher()
    asyncio.run(
        cls.capture_one(
            "http://127.0.0.1/",
            tmp_path / "m.png",
            mobile=True,
            wait_ms=0,
            launch=launcher,
        )
    )
    viewport = page.setViewport.call_args.args[0]
    assert viewport["width"] == 375
    assert viewport["height"] == 812
    assert viewport["isMobile"] is True


def test_capture_one_desktop_viewport_is_default(tmp_path):
    launcher, _, page = _make_fake_launcher()
    asyncio.run(
        cls.capture_one(
            "http://127.0.0.1/",
            tmp_path / "d.png",
            wait_ms=0,
            launch=launcher,
        )
    )
    viewport = page.setViewport.call_args.args[0]
    assert viewport["width"] >= 1024
    assert not viewport.get("isMobile", False)


def test_capture_one_closes_browser_on_goto_failure(tmp_path):
    launcher, browser, page = _make_fake_launcher()
    page.goto = AsyncMock(side_effect=RuntimeError("nav-fail"))
    with pytest.raises(RuntimeError, match="nav-fail"):
        asyncio.run(
            cls.capture_one(
                "http://127.0.0.1/",
                tmp_path / "x.png",
                wait_ms=0,
                launch=launcher,
            )
        )
    browser.close.assert_awaited()


# --- capture_all ----------------------------------------------------------


def test_capture_all_writes_one_file_per_shot(tmp_path):
    launcher, _, page = _make_fake_launcher()
    shots = [
        cls.ShotSpec(path="", filename="home.png", wait_ms=0),
        cls.ShotSpec(path="how-it-works.html", filename="hiw.png", wait_ms=0),
    ]
    out_dir = tmp_path / "preview"
    paths = cls.capture_all(
        "http://127.0.0.1:8080/",
        shots,
        out_dir,
        launch=launcher,
    )
    assert [p.name for p in paths] == ["home.png", "hiw.png"]
    assert page.screenshot.await_count == 2
    assert out_dir.is_dir()


def test_capture_all_resolves_urls_via_base(tmp_path):
    launcher, _, page = _make_fake_launcher()
    seen_urls: list[str] = []

    async def _spy_goto(url: str, *args: object, **kwargs: object) -> None:
        seen_urls.append(url)

    page.goto = AsyncMock(side_effect=_spy_goto)
    shots = [
        cls.ShotSpec(path="", filename="a.png", wait_ms=0),
        cls.ShotSpec(path="weekly/x.html", filename="b.png", wait_ms=0),
    ]
    cls.capture_all(
        "http://127.0.0.1:5555/",
        shots,
        tmp_path / "out",
        launch=launcher,
    )
    assert seen_urls == [
        "http://127.0.0.1:5555/",
        "http://127.0.0.1:5555/weekly/x.html",
    ]


# --- pick_free_port + serve_directory ------------------------------------


def test_pick_free_port_returns_listenable_port():
    port = cls.pick_free_port()
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", port))


def test_serve_directory_returns_working_url(tmp_path):
    # Create a small docs tree.
    (tmp_path / "index.html").write_text("<html><body>hello</body></html>", encoding="utf-8")
    (tmp_path / "data.json").write_text('{"ok": true}', encoding="utf-8")

    with cls.serve_directory(tmp_path) as (port, base_url):
        assert base_url.endswith("/")
        assert base_url.startswith("http://127.0.0.1:")
        # Fetch index.html
        with urllib.request.urlopen(base_url + "index.html", timeout=3) as resp:
            body = resp.read().decode("utf-8")
        assert "hello" in body
        # Fetch data.json
        with urllib.request.urlopen(base_url + "data.json", timeout=3) as resp:
            payload = resp.read().decode("utf-8")
        assert "ok" in payload


def test_serve_directory_shuts_down_cleanly(tmp_path):
    (tmp_path / "index.html").write_text("x", encoding="utf-8")
    with cls.serve_directory(tmp_path) as (port, base_url):
        url = base_url + "index.html"
        with urllib.request.urlopen(url, timeout=3) as resp:
            assert resp.status == 200
    # After exit: server thread is joined; port is released.
    # Give the OS a beat to fully release, then confirm a new bind succeeds.
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", port))


# --- DEFAULT_SHOTS sanity -------------------------------------------------


def test_default_shots_cover_desktop_and_mobile_home():
    filenames = {shot.filename for shot in cls.DEFAULT_SHOTS}
    assert "index-desktop.png" in filenames
    assert "index-mobile.png" in filenames
    mobile_shots = [s for s in cls.DEFAULT_SHOTS if s.mobile]
    assert mobile_shots, "expected at least one mobile shot"


# --- run() end-to-end with fake launcher ---------------------------------


def test_run_offline_populates_out_dir(tmp_path, monkeypatch, capsys):
    # Set up a tiny fake docs tree the served page can hit.
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "index.html").write_text("<html>ok</html>", encoding="utf-8")
    (docs_dir / "how-it-works.html").write_text("<html>hiw</html>", encoding="utf-8")
    out_dir = tmp_path / "preview"

    launcher, _, page = _make_fake_launcher()

    async def _write_file(opts: dict) -> None:
        Path(opts["path"]).write_bytes(b"\x89PNG\r\n\x1a\nfake")

    page.screenshot = AsyncMock(side_effect=_write_file)

    def _fake_capture_all(base_url, shots, target_dir, *, launch=None):
        target_dir.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        for shot in shots:
            dest = target_dir / shot.filename
            dest.write_bytes(b"\x89PNG\r\n\x1a\nfake")
            written.append(dest)
        return written

    monkeypatch.setattr(cls, "capture_all", _fake_capture_all)

    rc = cls.run([
        "--offline",
        "--docs",
        str(docs_dir),
        "--out-dir",
        str(out_dir),
    ])
    assert rc == 0
    files = sorted(p.name for p in out_dir.iterdir())
    assert "index-desktop.png" in files
    assert "index-mobile.png" in files
    captured = capsys.readouterr()
    assert "Wrote" in captured.out
