"""Unit tests for scripts/capture_live_site_context.py.

The structural capture (``check_live_site.run_spec_capture_and_ground_truth``)
is mocked — no browser launches, no network beyond the in-process localhost
server. Mirrors the AsyncMock-launcher style of test_check_live_site.py and
test_persona_ground_truth.py.

These tests assert that the produced context file carries, per persona:
a structural verdict (which asserts passed/failed) and the ground-truth
selector JSON block. They also exercise the graceful-degradation path when
the browser cannot launch.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "capture_live_site_context.py"


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "capture_live_site_context", SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["capture_live_site_context"] = mod
    spec.loader.exec_module(mod)
    return mod


cap = _load_module()


# --- helpers --------------------------------------------------------------


def _make_docs_dir(tmp_path: Path) -> Path:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "index.html").write_text(
        "<html><body><h1>Culture Calendar</h1>"
        "<div class='event-card'>An event</div></body></html>",
        encoding="utf-8",
    )
    (docs / "data.json").write_text(json.dumps([{"title": "x"}]), encoding="utf-8")
    return docs


def _make_spec_file(
    specs_dir: Path,
    name: str,
    *,
    selector: str = ".event-card",
    extra: dict[str, Any] | None = None,
) -> Path:
    payload: dict[str, Any] = {
        "persona": name,
        "description": f"{name} persona",
        "url": "https://hadrien-cornier.github.io/Culture-Calendar/",
        "wait_ms": 0,
        "asserts": [
            {"type": "selector_exists", "selector": selector},
            {"type": "body_contains", "text": "Culture Calendar"},
        ],
    }
    if extra:
        payload.update(extra)
    path = specs_dir / f"{name}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class _FakeFailure:
    """Mimics check_live_site.AssertionFailure (index/reason carrying)."""

    def __init__(self, index: int, assert_type: str, reason: str) -> None:
        self.index = index
        self.assert_type = assert_type
        self.reason = reason


def _make_launcher(*, eval_fn=None, html: str = "<html><body>ok</body></html>"):
    """AsyncMock launcher whose page satisfies run_spec_capture_and_ground_truth."""
    page = MagicMock()
    page.setViewport = AsyncMock()
    page.goto = AsyncMock()
    page.waitForSelector = AsyncMock()
    page.click = AsyncMock()
    page.type = AsyncMock()
    page.evaluate = (
        AsyncMock(side_effect=eval_fn) if eval_fn else AsyncMock(return_value=1)
    )
    page.screenshot = AsyncMock(return_value=b"PNGDATA")
    page.content = AsyncMock(return_value=html)
    browser = MagicMock()
    browser.newPage = AsyncMock(return_value=page)
    browser.close = AsyncMock()
    return AsyncMock(return_value=browser)


# --- rewrite_url ----------------------------------------------------------


def test_rewrite_url_swaps_live_host():
    assert (
        cap.rewrite_url(
            "https://hadrien-cornier.github.io/Culture-Calendar/", "http://127.0.0.1:9/"
        )
        == "http://127.0.0.1:9/"
    )


def test_rewrite_url_swaps_subpath():
    assert (
        cap.rewrite_url(
            "https://hadrien-cornier.github.io/Culture-Calendar/data.json",
            "http://127.0.0.1:9/",
        )
        == "http://127.0.0.1:9/data.json"
    )


def test_rewrite_url_leaves_other_hosts_alone():
    assert cap.rewrite_url("https://other.example/", "http://127.0.0.1:9/") == (
        "https://other.example/"
    )


# --- build_context with mocked capture -----------------------------------


def test_build_context_emits_verdict_and_ground_truth(tmp_path):
    specs = tmp_path / "specs"
    specs.mkdir()
    _make_spec_file(specs, "alpha", selector=".event-card")

    def fake_capture(spec):
        # Mirror the real return shape: a passing + a failing assert.
        return {
            "failures": [_FakeFailure(1, "body_contains", "body did not contain X")],
            "ground_truth": {".event-card": {"exists": True, "count": 12}},
            "dom": "<html><body><div class='event-card'>e</div></body></html>",
            "dynamic": True,
            "note": "",
        }

    md = cap.build_context(specs, "http://127.0.0.1:9/", capture_fn=fake_capture)

    assert "## alpha" in md
    assert "Structural verdict: FAIL (1/2 asserts passed)" in md
    assert "PASS assert[0] (selector_exists)" in md
    assert "FAIL assert[1] (body_contains)" in md
    # Ground-truth JSON block present with the selector + count.
    assert "Ground truth selectors" in md
    assert "event-card" in md
    assert '"count": 12' in md
    # DOM snippet present.
    assert "DOM snippet" in md


def test_build_context_all_pass_verdict(tmp_path):
    specs = tmp_path / "specs"
    specs.mkdir()
    _make_spec_file(specs, "beta")

    def fake_capture(spec):
        return {
            "failures": [],
            "ground_truth": {".event-card": {"exists": True, "count": 3}},
            "dom": "<html/>",
            "dynamic": True,
            "note": "",
        }

    md = cap.build_context(specs, "http://127.0.0.1:9/", capture_fn=fake_capture)
    assert "Structural verdict: PASS (2/2 asserts passed)" in md


def test_build_context_rewrites_url_before_capture(tmp_path):
    specs = tmp_path / "specs"
    specs.mkdir()
    _make_spec_file(specs, "gamma")
    seen: dict[str, Any] = {}

    def fake_capture(spec):
        seen["url"] = spec["url"]
        return {
            "failures": [],
            "ground_truth": {},
            "dom": "<html/>",
            "dynamic": True,
            "note": "",
        }

    cap.build_context(specs, "http://127.0.0.1:5555/", capture_fn=fake_capture)
    assert seen["url"] == "http://127.0.0.1:5555/"


def test_build_context_trims_large_dom(tmp_path):
    specs = tmp_path / "specs"
    specs.mkdir()
    _make_spec_file(specs, "delta")
    big = "x" * (cap.PER_PERSONA_SNIPPET_CAP + 5000)

    def fake_capture(spec):
        return {
            "failures": [],
            "ground_truth": {},
            "dom": big,
            "dynamic": True,
            "note": "",
        }

    md = cap.build_context(specs, "http://127.0.0.1:9/", capture_fn=fake_capture)
    assert "trimmed to" in md
    # The emitted snippet must not contain the full oversized DOM.
    assert big not in md


# --- capture_spec graceful degradation -----------------------------------


def test_capture_spec_dynamic_path_with_mock_launcher():
    # querySelectorAll returns counts; non-query evaluate (asserts) returns truthy.
    def fake_eval(code, arg=None):
        if "querySelectorAll" in str(code):
            return 4
        return True

    launcher = _make_launcher(eval_fn=fake_eval, html="<html><body>page</body></html>")
    spec = {
        "url": "http://127.0.0.1:9/",
        "wait_ms": 0,
        "asserts": [{"type": "selector_exists", "selector": ".event-card"}],
    }
    out = cap.capture_spec(spec, launch=launcher)
    assert out["dynamic"] is True
    assert out["failures"] == []
    assert out["ground_truth"][".event-card"]["count"] == 4
    assert "page" in out["dom"]


def test_capture_spec_degrades_when_browser_unavailable(monkeypatch):
    def boom(*_a, **_kw):
        raise RuntimeError("Chromium failed to launch")

    monkeypatch.setattr(cap.check_live_site, "run_spec_capture_and_ground_truth", boom)
    monkeypatch.setattr(
        cap, "_fetch_static", lambda url: "<html>static fallback</html>"
    )
    out = cap.capture_spec({"url": "http://127.0.0.1:9/", "asserts": []})
    assert out["dynamic"] is False
    assert out["failures"] == []
    assert out["ground_truth"] == {}
    assert "static fallback" in out["dom"]
    assert "Dynamic capture skipped" in out["note"]


def test_render_section_marks_skipped_when_degraded(tmp_path):
    spec = {
        "persona": "x",
        "url": "http://127.0.0.1:9/",
        "asserts": [{"type": "selector_exists", "selector": ".x"}],
    }
    captured = {
        "failures": [],
        "ground_truth": {},
        "dom": "<html>static</html>",
        "dynamic": False,
        "note": "Dynamic capture skipped (browser unavailable: X)",
    }
    section = cap.render_section("x", tmp_path / "x.json", spec, captured)
    assert "SKIPPED" in section
    assert "static" in section
    assert "Ground truth selectors" in section


# --- end-to-end run() with the in-process localhost server ----------------


def test_run_writes_context_file_with_real_server(tmp_path):
    """Full run(): real localhost http.server, mocked capture, file written."""
    docs = _make_docs_dir(tmp_path)
    specs = tmp_path / "specs"
    specs.mkdir()
    _make_spec_file(specs, "search-user", selector=".event-card")
    out = tmp_path / "out" / "live-site-context.md"

    captured_urls: list[str] = []

    def fake_capture(spec):
        captured_urls.append(spec["url"])
        return {
            "failures": [],
            "ground_truth": {".event-card": {"exists": True, "count": 1}},
            "dom": "<html><body>served</body></html>",
            "dynamic": True,
            "note": "",
        }

    rc = cap.run(
        specs_dir=specs,
        docs_dir=docs,
        out_path=out,
        capture_fn=fake_capture,
    )
    assert rc == 0
    assert out.is_file()
    text = out.read_text(encoding="utf-8")
    assert "## search-user" in text
    assert "Structural verdict: PASS" in text
    assert "Ground truth selectors" in text
    assert "event-card" in text
    # URL was rewritten to the local server (port-bearing localhost).
    assert captured_urls
    assert captured_urls[0].startswith("http://127.0.0.1:")


def test_run_with_base_url_skips_server(tmp_path):
    """When --base-url is supplied no server is started; capture still runs."""
    specs = tmp_path / "specs"
    specs.mkdir()
    _make_spec_file(specs, "p1")
    out = tmp_path / "ctx.md"

    def fake_capture(spec):
        return {
            "failures": [],
            "ground_truth": {".event-card": {"exists": True, "count": 2}},
            "dom": "<html/>",
            "dynamic": True,
            "note": "",
        }

    rc = cap.run(
        specs_dir=specs,
        docs_dir=tmp_path / "nonexistent-docs",  # ignored when base_url given
        out_path=out,
        base_url="http://127.0.0.1:8123/",
        capture_fn=fake_capture,
    )
    assert rc == 0
    assert out.is_file()
    assert "## p1" in out.read_text(encoding="utf-8")


def test_run_missing_specs_dir_writes_empty_and_exits_zero(tmp_path):
    out = tmp_path / "ctx.md"
    rc = cap.run(
        specs_dir=tmp_path / "absent",
        docs_dir=tmp_path,
        out_path=out,
    )
    assert rc == 0
    assert out.is_file()
    assert "No specs found" in out.read_text(encoding="utf-8")


def test_run_creates_parent_dir(tmp_path):
    docs = _make_docs_dir(tmp_path)
    specs = tmp_path / "specs"
    specs.mkdir()
    _make_spec_file(specs, "p1")
    out = tmp_path / "deep" / "nested" / "ctx.md"

    def fake_capture(spec):
        return {
            "failures": [],
            "ground_truth": {},
            "dom": "<html/>",
            "dynamic": True,
            "note": "",
        }

    rc = cap.run(specs_dir=specs, docs_dir=docs, out_path=out, capture_fn=fake_capture)
    assert rc == 0
    assert out.is_file()


def test_parse_args_defaults():
    ns = cap.parse_args([])
    assert ns.specs_dir == cap.DEFAULT_SPECS_DIR
    assert ns.docs_dir == cap.DEFAULT_DOCS_DIR
    assert ns.out == cap.DEFAULT_OUT
    assert ns.base_url is None
