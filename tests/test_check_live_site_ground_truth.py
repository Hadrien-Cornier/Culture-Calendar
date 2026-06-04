"""Tests for the check_live_site ground-truth engine.

``check_live_site`` captures per-selector ``{exists, count}`` observations
against the same pyppeteer page that feeds the screenshot, so a downstream
LLM consumer can be shown observed DOM fact instead of guessing whether a
feature is present. These tests cover the engine that produces that payload:
``derive_ground_truth_selectors`` and
``run_spec_capture_and_ground_truth`` (plus the back-compat
``run_spec_and_capture`` three-tuple wrapper).

Pyppeteer is mocked everywhere — no browser launches.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

REPO_ROOT = Path(__file__).resolve().parents[1]
CHECK_PATH = REPO_ROOT / "scripts" / "check_live_site.py"


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


cls = _load("check_live_site_gt", CHECK_PATH)


# --- derive_ground_truth_selectors ---------------------------------------


def test_derive_selectors_respects_explicit_opt_in():
    spec = {
        "url": "x",
        "ground_truth_selectors": [".explicit", "#one"],
        "asserts": [{"type": "selector_exists", "selector": ".ignored"}],
    }
    assert cls.derive_ground_truth_selectors(spec) == [".explicit", "#one"]


def test_derive_selectors_unions_asserts_clicks_and_pre_actions():
    spec = {
        "url": "x",
        "asserts": [
            {"type": "selector_exists", "selector": ".event-card"},
            {"type": "selector_min_count", "selector": ".event-when", "min": 1},
            {"type": "body_contains", "text": "hello"},
        ],
        "click_before_assert": [".open-disclosure"],
        "pre_screenshot_actions": [
            {"type": "click", "selector": ".below-fold"},
            {"type": "scroll", "y": 500},
            {"type": "type", "selector": "#search", "text": "q"},
        ],
    }
    sels = cls.derive_ground_truth_selectors(spec)
    assert ".event-card" in sels
    assert ".event-when" in sels
    assert ".open-disclosure" in sels
    assert ".below-fold" in sels
    assert "#search" in sels


def test_derive_selectors_deduplicates_preserving_order():
    spec = {
        "url": "x",
        "asserts": [
            {"type": "selector_exists", "selector": ".a"},
            {"type": "selector_exists", "selector": ".b"},
            {"type": "selector_exists", "selector": ".a"},
        ],
        "click_before_assert": [".b", ".c"],
    }
    assert cls.derive_ground_truth_selectors(spec) == [".a", ".b", ".c"]


def test_derive_selectors_returns_empty_for_plain_body_asserts():
    spec = {
        "url": "x",
        "asserts": [{"type": "body_contains", "text": "hi"}],
    }
    assert cls.derive_ground_truth_selectors(spec) == []


# --- run_spec_capture_and_ground_truth: live DOM probe -------------------


def _make_page(
    eval_fn=None,
    *,
    screenshot_bytes: bytes = b"PNGDATA",
    html: str = "<html><body>ok</body></html>",
) -> MagicMock:
    page = MagicMock()
    page.setViewport = AsyncMock()
    page.goto = AsyncMock()
    page.waitForSelector = AsyncMock()
    page.click = AsyncMock()
    page.type = AsyncMock()
    page.evaluate = (
        AsyncMock(side_effect=eval_fn) if eval_fn else AsyncMock(return_value=0)
    )
    page.screenshot = AsyncMock(return_value=screenshot_bytes)
    page.content = AsyncMock(return_value=html)
    return page


def _make_launcher(page: MagicMock):
    browser = MagicMock()
    browser.newPage = AsyncMock(return_value=page)
    browser.close = AsyncMock()
    return AsyncMock(return_value=browser), browser


def test_run_spec_capture_and_ground_truth_probes_each_selector():
    """The fourth tuple element must map each derived selector to a dict
    with ``exists`` and ``count`` keys, captured from the same page."""

    # page.evaluate is called for asserts AND for ground-truth probes.
    # We stub counts: ".x" -> 3 elements; ".y" -> 0 elements.
    returns: list[Any] = [3, 0]

    async def fake_eval(code, arg=None):
        if "querySelectorAll" not in str(code):
            return True  # asserts path
        return returns.pop(0)

    page = _make_page(eval_fn=fake_eval)
    launcher, _ = _make_launcher(page)
    spec = {
        "url": "about:blank",
        "asserts": [
            {"type": "selector_exists", "selector": ".x"},
            {"type": "selector_exists", "selector": ".y"},
        ],
    }
    # The first two evaluate calls are the asserts. We need the ground-truth
    # probe to drive its own counts — expand returns accordingly.
    returns = [3, 0, 3, 0]
    _, _, _, gt = asyncio.run(
        cls.run_spec_capture_and_ground_truth(spec, launch=launcher)
    )
    assert gt[".x"]["exists"] is True
    assert gt[".x"]["count"] == 3
    assert gt[".y"]["exists"] is False
    assert gt[".y"]["count"] == 0


def test_run_spec_capture_and_ground_truth_returns_four_tuple():
    page = _make_page()
    launcher, _ = _make_launcher(page)
    out = asyncio.run(
        cls.run_spec_capture_and_ground_truth(
            {"url": "about:blank", "asserts": []}, launch=launcher
        )
    )
    assert len(out) == 4
    failures, b64, html, gt = out
    assert failures == []
    assert b64
    assert html
    assert gt == {}  # no selectors to probe


def test_run_spec_capture_and_ground_truth_collects_errors():
    async def boom(_code, _arg=None):
        raise RuntimeError("eval failed")

    page = _make_page()
    page.evaluate = AsyncMock(side_effect=boom)
    launcher, _ = _make_launcher(page)
    spec = {
        "url": "about:blank",
        "ground_truth_selectors": [".broken"],
        "asserts": [],
    }
    _, _, _, gt = asyncio.run(
        cls.run_spec_capture_and_ground_truth(spec, launch=launcher)
    )
    entry = gt[".broken"]
    assert entry["exists"] is False
    assert entry["count"] == 0
    assert "eval failed" in entry["error"]


def test_run_spec_capture_and_ground_truth_opt_out_returns_empty_dict():
    page = _make_page()
    launcher, _ = _make_launcher(page)
    spec = {
        "url": "about:blank",
        "asserts": [{"type": "selector_exists", "selector": ".x"}],
    }
    _, _, _, gt = asyncio.run(
        cls.run_spec_capture_and_ground_truth(
            spec, launch=launcher, collect_ground_truth=False
        )
    )
    assert gt == {}


def test_run_spec_and_capture_backcompat_three_tuple():
    """Legacy wrapper must continue to return a 3-tuple so existing callers
    and tests keep working — the new ground-truth slot lives on the new
    function, not grafted onto the legacy one."""
    page = _make_page()
    launcher, _ = _make_launcher(page)
    out = asyncio.run(
        cls.run_spec_and_capture({"url": "about:blank", "asserts": []}, launch=launcher)
    )
    assert len(out) == 3
