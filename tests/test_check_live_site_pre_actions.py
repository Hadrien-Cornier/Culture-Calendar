"""Unit tests for ``pre_screenshot_actions`` in ``scripts/check_live_site.py``.

Personas often need the page in a specific visual state before the LLM sees
the screenshot — scrolled below the fold, a disclosure panel opened, a
search input filled. ``pre_screenshot_actions`` is a sequence of scroll /
click / type directives replayed on the shared pyppeteer page after asserts
run but before :py:meth:`page.screenshot`.

Pyppeteer is fully mocked — no browser launches.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_live_site.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_live_site", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_live_site"] = mod
    spec.loader.exec_module(mod)
    return mod


cls = _load_module()


def _make_page() -> MagicMock:
    page = MagicMock()
    page.setViewport = AsyncMock()
    page.goto = AsyncMock()
    page.waitForSelector = AsyncMock()
    page.click = AsyncMock()
    page.type = AsyncMock()
    page.evaluate = AsyncMock(return_value=None)
    page.screenshot = AsyncMock(return_value=b"PNGDATA")
    page.content = AsyncMock(return_value="<html></html>")
    return page


def _make_launcher(page: MagicMock):
    browser = MagicMock()
    browser.newPage = AsyncMock(return_value=page)
    browser.close = AsyncMock()
    launcher = AsyncMock(return_value=browser)
    return launcher, browser


# --- load_spec schema tolerance ------------------------------------------


def test_load_spec_accepts_pre_screenshot_actions(tmp_path):
    p = tmp_path / "spec.json"
    p.write_text(
        json.dumps(
            {
                "url": "https://x",
                "pre_screenshot_actions": [{"type": "scroll", "y": 500}],
                "asserts": [],
            }
        )
    )
    spec = cls.load_spec(p)
    assert spec["pre_screenshot_actions"] == [{"type": "scroll", "y": 500}]


def test_load_spec_rejects_non_list_pre_screenshot_actions(tmp_path):
    p = tmp_path / "spec.json"
    p.write_text(
        json.dumps(
            {
                "url": "https://x",
                "pre_screenshot_actions": {"oops": True},
                "asserts": [],
            }
        )
    )
    with pytest.raises(ValueError):
        cls.load_spec(p)


# --- individual action types ---------------------------------------------


def test_scroll_action_calls_evaluate_with_coords():
    page = _make_page()
    launcher, _ = _make_launcher(page)
    spec = {
        "url": "about:blank",
        "pre_screenshot_actions": [{"type": "scroll", "y": 800}],
        "asserts": [],
    }
    asyncio.run(cls.run_spec_and_capture(spec, launch=launcher))
    scroll_calls = [
        c
        for c in page.evaluate.call_args_list
        if c.args and "scroll" in str(c.args[0]).lower()
    ]
    assert scroll_calls, "expected a scrollTo evaluate call"
    coords = scroll_calls[0].args[1]
    assert coords.get("y") == 800
    assert coords.get("x") == 0


def test_scroll_action_respects_x_coord():
    page = _make_page()
    launcher, _ = _make_launcher(page)
    spec = {
        "url": "about:blank",
        "pre_screenshot_actions": [{"type": "scroll", "x": 100, "y": 200}],
        "asserts": [],
    }
    asyncio.run(cls.run_spec_and_capture(spec, launch=launcher))
    scroll_calls = [
        c
        for c in page.evaluate.call_args_list
        if c.args and "scroll" in str(c.args[0]).lower()
    ]
    assert scroll_calls
    coords = scroll_calls[0].args[1]
    assert coords == {"x": 100, "y": 200}


def test_click_action_invokes_page_click():
    page = _make_page()
    launcher, _ = _make_launcher(page)
    spec = {
        "url": "about:blank",
        "pre_screenshot_actions": [{"type": "click", "selector": ".open"}],
        "asserts": [],
    }
    asyncio.run(cls.run_spec_and_capture(spec, launch=launcher))
    clicks = [c.args[0] for c in page.click.call_args_list]
    assert ".open" in clicks


def test_click_action_waits_for_selector():
    page = _make_page()
    launcher, _ = _make_launcher(page)
    spec = {
        "url": "about:blank",
        "pre_screenshot_actions": [{"type": "click", "selector": ".lazy"}],
        "asserts": [],
    }
    asyncio.run(cls.run_spec_and_capture(spec, launch=launcher))
    waited = [c.args[0] for c in page.waitForSelector.call_args_list]
    assert ".lazy" in waited


def test_type_action_invokes_page_type():
    page = _make_page()
    launcher, _ = _make_launcher(page)
    spec = {
        "url": "about:blank",
        "pre_screenshot_actions": [
            {"type": "type", "selector": "#q", "text": "hello"}
        ],
        "asserts": [],
    }
    asyncio.run(cls.run_spec_and_capture(spec, launch=launcher))
    type_calls = page.type.call_args_list
    assert type_calls, "expected a page.type call"
    assert type_calls[0].args[0] == "#q"
    assert type_calls[0].args[1] == "hello"


def test_type_action_waits_for_selector():
    page = _make_page()
    launcher, _ = _make_launcher(page)
    spec = {
        "url": "about:blank",
        "pre_screenshot_actions": [
            {"type": "type", "selector": "input[name=q]", "text": "x"}
        ],
        "asserts": [],
    }
    asyncio.run(cls.run_spec_and_capture(spec, launch=launcher))
    waited = [c.args[0] for c in page.waitForSelector.call_args_list]
    assert "input[name=q]" in waited


# --- ordering and sequencing ---------------------------------------------


def test_pre_actions_run_in_declared_order():
    page = _make_page()
    launcher, _ = _make_launcher(page)
    spec = {
        "url": "about:blank",
        "pre_screenshot_actions": [
            {"type": "click", "selector": ".a"},
            {"type": "click", "selector": ".b"},
            {"type": "click", "selector": ".c"},
        ],
        "asserts": [],
    }
    asyncio.run(cls.run_spec_and_capture(spec, launch=launcher))
    clicks = [c.args[0] for c in page.click.call_args_list]
    # pre_screenshot_actions must not run before click_before_assert —
    # but here click_before_assert is absent, so only our three clicks should fire.
    assert clicks == [".a", ".b", ".c"]


def test_pre_actions_run_before_screenshot():
    page = _make_page()
    call_order: list[str] = []

    async def record_click(sel, *a, **kw):
        call_order.append(f"click:{sel}")

    async def record_screenshot(*a, **kw):
        call_order.append("screenshot")
        return b"PNGDATA"

    page.click.side_effect = record_click
    page.screenshot.side_effect = record_screenshot

    launcher, _ = _make_launcher(page)
    spec = {
        "url": "about:blank",
        "pre_screenshot_actions": [{"type": "click", "selector": ".open"}],
        "asserts": [],
    }
    asyncio.run(cls.run_spec_and_capture(spec, launch=launcher))
    assert "click:.open" in call_order
    assert "screenshot" in call_order
    assert call_order.index("click:.open") < call_order.index("screenshot")


def test_pre_actions_run_after_asserts():
    page = _make_page()
    call_order: list[str] = []

    async def track_evaluate(expr, *a, **kw):
        call_order.append(f"evaluate:{str(expr)[:20]}")
        return True

    async def track_click(sel, *a, **kw):
        call_order.append(f"click:{sel}")

    page.evaluate.side_effect = track_evaluate
    page.click.side_effect = track_click

    launcher, _ = _make_launcher(page)
    spec = {
        "url": "about:blank",
        "asserts": [{"type": "body_contains", "text": "hi"}],
        "pre_screenshot_actions": [{"type": "click", "selector": ".post-assert"}],
    }
    asyncio.run(cls.run_spec_and_capture(spec, launch=launcher))
    # The assert's body_contains evaluate must happen before the post-assert click.
    assert_idx = next(
        i for i, x in enumerate(call_order) if x.startswith("evaluate:")
    )
    click_idx = call_order.index("click:.post-assert")
    assert assert_idx < click_idx


# --- edge cases ----------------------------------------------------------


def test_no_pre_actions_means_no_clicks_or_typing():
    page = _make_page()
    launcher, _ = _make_launcher(page)
    spec = {"url": "about:blank", "asserts": []}
    asyncio.run(cls.run_spec_and_capture(spec, launch=launcher))
    assert page.click.call_args_list == []
    assert page.type.call_args_list == []


def test_empty_pre_actions_list_is_noop():
    page = _make_page()
    launcher, _ = _make_launcher(page)
    spec = {
        "url": "about:blank",
        "pre_screenshot_actions": [],
        "asserts": [],
    }
    asyncio.run(cls.run_spec_and_capture(spec, launch=launcher))
    assert page.click.call_args_list == []
    assert page.type.call_args_list == []


def test_unknown_action_type_raises_value_error():
    page = _make_page()
    launcher, _ = _make_launcher(page)
    spec = {
        "url": "about:blank",
        "pre_screenshot_actions": [{"type": "mystery"}],
        "asserts": [],
    }
    with pytest.raises(ValueError):
        asyncio.run(cls.run_spec_and_capture(spec, launch=launcher))


def test_mixed_action_sequence():
    page = _make_page()
    launcher, _ = _make_launcher(page)
    spec = {
        "url": "about:blank",
        "pre_screenshot_actions": [
            {"type": "click", "selector": ".open"},
            {"type": "type", "selector": "#q", "text": "austin"},
            {"type": "scroll", "y": 400},
        ],
        "asserts": [],
    }
    asyncio.run(cls.run_spec_and_capture(spec, launch=launcher))
    clicks = [c.args[0] for c in page.click.call_args_list]
    types_ = [(c.args[0], c.args[1]) for c in page.type.call_args_list]
    scroll_calls = [
        c
        for c in page.evaluate.call_args_list
        if c.args and "scroll" in str(c.args[0]).lower()
    ]
    assert clicks == [".open"]
    assert types_ == [("#q", "austin")]
    assert scroll_calls
