"""Regression guards for T2.2: full-page screenshots + 40KB DOM snippet cap.

Background: before T2.2 the persona harness captured only the default
viewport (desktop 1280x800, mobile 375x812) and sent a 10KB DOM slice to
the LLM. Personas routinely marked already-implemented features as missing
because those features rendered below the fold or lived deeper in the HTML
than the 10KB slice reached. Raising the DOM cap to 40KB and defaulting
screenshots to ``fullPage: True`` gives the LLM the whole page to score.
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CRITIQUE_PATH = REPO_ROOT / "scripts" / "persona_critique.py"


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


pc = _load("persona_critique_fullpage", CRITIQUE_PATH)


def _make_fake_launcher(*, html: str = "<html><body>ok</body></html>"):
    page = MagicMock()
    page.setViewport = AsyncMock()
    page.goto = AsyncMock()
    page.waitForSelector = AsyncMock()
    page.click = AsyncMock()
    page.evaluate = AsyncMock(return_value=True)
    page.screenshot = AsyncMock(return_value=b"PNGDATA")
    page.content = AsyncMock(return_value=html)
    browser = MagicMock()
    browser.newPage = AsyncMock(return_value=page)
    browser.close = AsyncMock()
    launcher = AsyncMock(return_value=browser)
    return launcher, browser, page


# --- DOM snippet cap raised to 40KB -------------------------------------


def test_dom_snippet_max_bytes_is_forty_thousand():
    """The module-level cap is the default applied everywhere the persona
    harness truncates HTML for the LLM. 40KB is the post-T2.2 value."""
    assert pc.DOM_SNIPPET_MAX_BYTES == 40_000


def test_dom_snippet_cap_exceeds_ten_thousand_marker():
    """Explicit regression guard: the old 10KB cap consistently truncated
    the DOM before personas could see below-the-fold landmarks."""
    assert pc.DOM_SNIPPET_MAX_BYTES > 10_000


def test_shared_page_capture_default_dom_limit_honors_forty_kb(tmp_path):
    """When callers don't pass ``dom_max_bytes`` explicitly, the shared-page
    wrapper truncates to the 40KB default, not the old 10KB slice."""
    long_html = "<html>" + ("x" * 60_000) + "</html>"
    launcher, _, _ = _make_fake_launcher(html=long_html)
    _, _, _, _, _, dom = pc.run_shared_page_capture(
        {"url": "about:blank", "asserts": []},
        launch=launcher,
    )
    # Default cap is 40_000; the 60KB source is truncated to exactly that.
    assert len(dom) == 40_000


def test_shared_page_capture_accepts_full_html_when_under_cap():
    """DOMs that fit under 40KB are passed through untruncated."""
    body = "<html>" + ("y" * 5_000) + "</html>"
    launcher, _, _ = _make_fake_launcher(html=body)
    _, _, _, _, _, dom = pc.run_shared_page_capture(
        {"url": "about:blank", "asserts": []},
        launch=launcher,
    )
    assert dom == body


# --- Shared-page screenshot defaults to fullPage=True -------------------


def test_shared_page_capture_defaults_to_full_page_screenshot():
    """T2.2 rationale: personas need to see below-the-fold content. The
    shared-page wrapper must default ``fullPage=True`` so the LLM sees the
    whole rendered page, not just the initial viewport."""
    launcher, _, page = _make_fake_launcher()
    pc.run_shared_page_capture(
        {"url": "about:blank", "asserts": []},
        launch=launcher,
    )
    args = page.screenshot.call_args.args[0]
    assert args["fullPage"] is True


def test_shared_page_capture_honors_explicit_full_page_override():
    """Callers can still opt out of full-page capture for a narrower shot."""
    launcher, _, page = _make_fake_launcher()
    pc.run_shared_page_capture(
        {"url": "about:blank", "asserts": []},
        launch=launcher,
        full_page=False,
    )
    args = page.screenshot.call_args.args[0]
    assert args["fullPage"] is False


# --- Legacy fresh-page capture path also uses fullPage=True -------------


def test_async_capture_uses_full_page_screenshot():
    """``_async_capture`` is the legacy fresh-session capture path (still
    called by ``bench_personas.py``). T2.2 raises it to ``fullPage: True``
    so the benchmark's screenshots match what the shared-page flow sees."""
    launcher, _, page = _make_fake_launcher()
    asyncio.run(pc._async_capture({"url": "about:blank"}, launch=launcher))
    args = page.screenshot.call_args.args[0]
    assert args["fullPage"] is True


def test_capture_screenshot_and_dom_sync_wrapper_passes_full_page(tmp_path):
    """The sync wrapper that ``bench_personas.py`` consumes must also carry
    the full-page default through to the underlying pyppeteer call."""
    launcher, _, page = _make_fake_launcher(
        html="<html><body>" + ("z" * 1000) + "</body></html>"
    )
    pc.capture_screenshot_and_dom({"url": "about:blank"}, launch=launcher)
    args = page.screenshot.call_args.args[0]
    assert args["fullPage"] is True
