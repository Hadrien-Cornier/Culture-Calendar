"""Unit tests for scripts/check_live_site.py.

Pyppeteer is fully mocked: no real browser launches here. The module's
`launch` parameter is injected, so the ``pyppeteer`` import is never
touched during tests. One subprocess-based test verifies ``--help``
still exits 0 without any spec file.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import subprocess
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


def _make_fake_launcher(evaluate_returns):
    """Build an AsyncMock launcher whose page.evaluate returns each value in sequence.

    Returns the launcher along with the underlying browser and page mocks so
    tests can inspect call args (viewport, clicks, selectors).
    """
    page = MagicMock()
    page.setViewport = AsyncMock()
    page.goto = AsyncMock()
    page.waitForSelector = AsyncMock()
    page.click = AsyncMock()
    page.evaluate = AsyncMock(side_effect=list(evaluate_returns))
    browser = MagicMock()
    browser.newPage = AsyncMock(return_value=page)
    browser.close = AsyncMock()
    launcher = AsyncMock(return_value=browser)
    return launcher, browser, page


# --- CLI-level tests ------------------------------------------------------


def test_cli_help_exits_zero():
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "--spec" in result.stdout
    assert "--retry" in result.stdout


def test_cli_missing_spec_exits_nonzero(tmp_path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--spec", str(tmp_path / "nope.json")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "spec file not found" in result.stderr


# --- Spec loader ----------------------------------------------------------


def test_load_spec_parses_valid(tmp_path):
    p = tmp_path / "spec.json"
    p.write_text(json.dumps({"url": "https://example.invalid", "asserts": []}))
    spec = cls.load_spec(p)
    assert spec["url"] == "https://example.invalid"


def test_load_spec_rejects_missing_url(tmp_path):
    p = tmp_path / "spec.json"
    p.write_text(json.dumps({"asserts": []}))
    with pytest.raises(ValueError):
        cls.load_spec(p)


def test_load_spec_rejects_non_object(tmp_path):
    p = tmp_path / "spec.json"
    p.write_text(json.dumps(["not", "an", "object"]))
    with pytest.raises(ValueError):
        cls.load_spec(p)


def test_load_spec_rejects_non_list_asserts(tmp_path):
    p = tmp_path / "spec.json"
    p.write_text(json.dumps({"url": "https://x", "asserts": {"not": "list"}}))
    with pytest.raises(ValueError):
        cls.load_spec(p)


# --- Expression wrapper ---------------------------------------------------


def test_wrap_expr_expression_mode():
    wrapped = cls._wrap_expr("1+1")
    assert "=> (1+1)" in wrapped


def test_wrap_expr_statement_mode_with_semicolons():
    wrapped = cls._wrap_expr("var x = 1; return x")
    assert wrapped.startswith("() => {")
    assert "return x" in wrapped


def test_wrap_expr_statement_mode_with_return():
    wrapped = cls._wrap_expr("return true")
    assert wrapped.startswith("() => {")


# --- Assertion types ------------------------------------------------------


def _run_spec(spec, evaluate_returns):
    launcher, browser, page = _make_fake_launcher(evaluate_returns)
    failures = asyncio.run(cls.run_spec(spec, launch=launcher))
    return failures, page


def test_body_contains_pass():
    spec = {"url": "about:blank", "asserts": [{"type": "body_contains", "text": "hi"}]}
    failures, _ = _run_spec(spec, [True])
    assert failures == []


def test_body_contains_fail():
    spec = {"url": "about:blank", "asserts": [{"type": "body_contains", "text": "nope"}]}
    failures, _ = _run_spec(spec, [False])
    assert len(failures) == 1
    assert "nope" in failures[0].reason
    assert failures[0].assert_type == "body_contains"


def test_body_not_contains_pass():
    spec = {"url": "about:blank", "asserts": [{"type": "body_not_contains", "text": "bad"}]}
    failures, _ = _run_spec(spec, [False])
    assert failures == []


def test_body_not_contains_fail():
    spec = {"url": "about:blank", "asserts": [{"type": "body_not_contains", "text": "bad"}]}
    failures, _ = _run_spec(spec, [True])
    assert len(failures) == 1
    assert "bad" in failures[0].reason


def test_selector_exists_pass():
    spec = {"url": "about:blank", "asserts": [{"type": "selector_exists", "selector": ".x"}]}
    failures, _ = _run_spec(spec, [3])
    assert failures == []


def test_selector_exists_fail_on_zero():
    spec = {"url": "about:blank", "asserts": [{"type": "selector_exists", "selector": ".x"}]}
    failures, _ = _run_spec(spec, [0])
    assert len(failures) == 1
    assert ".x" in failures[0].reason


def test_selector_min_count_pass_and_fail():
    spec = {
        "url": "about:blank",
        "asserts": [{"type": "selector_min_count", "selector": ".c", "min": 3}],
    }
    ok, _ = _run_spec(spec, [5])
    assert ok == []
    bad, _ = _run_spec(spec, [1])
    assert len(bad) == 1
    assert "1" in bad[0].reason


def test_selector_max_count_pass_and_fail():
    spec = {
        "url": "about:blank",
        "asserts": [{"type": "selector_max_count", "selector": ".c", "max": 10}],
    }
    ok, _ = _run_spec(spec, [5])
    assert ok == []
    bad, _ = _run_spec(spec, [20])
    assert len(bad) == 1
    assert "20" in bad[0].reason


def test_js_truthy_pass():
    spec = {
        "url": "about:blank",
        "asserts": [{"type": "js_truthy", "expression": "1+1===2"}],
    }
    failures, _ = _run_spec(spec, [True])
    assert failures == []


def test_js_truthy_fail_reports_expression():
    spec = {
        "url": "about:blank",
        "asserts": [{"type": "js_truthy", "expression": "false"}],
    }
    failures, _ = _run_spec(spec, [False])
    assert len(failures) == 1
    assert "falsy" in failures[0].reason


def test_js_truthy_catches_runtime_error():
    spec = {
        "url": "about:blank",
        "asserts": [{"type": "js_truthy", "expression": "throw new Error('boom')"}],
    }
    launcher, _, page = _make_fake_launcher([])
    page.evaluate = AsyncMock(side_effect=RuntimeError("boom"))
    failures = asyncio.run(cls.run_spec(spec, launch=launcher))
    assert len(failures) == 1
    assert "boom" in failures[0].reason


def test_unknown_assert_type_reported():
    spec = {"url": "about:blank", "asserts": [{"type": "frobnicate"}]}
    failures, _ = _run_spec(spec, [])  # evaluate not called
    assert len(failures) == 1
    assert "frobnicate" in failures[0].reason


# --- Viewport, waits, clicks ---------------------------------------------


def test_mobile_viewport_used_when_mobile_true():
    spec = {"url": "about:blank", "mobile": True, "asserts": []}
    launcher, _, page = _make_fake_launcher([])
    asyncio.run(cls.run_spec(spec, launch=launcher))
    viewport = page.setViewport.call_args.args[0]
    assert viewport["width"] == 375
    assert viewport["height"] == 812
    assert viewport["isMobile"] is True


def test_desktop_viewport_is_default():
    spec = {"url": "about:blank", "asserts": []}
    _, page = _run_spec(spec, [])
    viewport = page.setViewport.call_args.args[0]
    assert viewport["width"] >= 1024
    assert not viewport.get("isMobile", False)


def test_wait_for_selector_invoked():
    spec = {"url": "about:blank", "wait_for_selector": ".ready", "asserts": []}
    launcher, _, page = _make_fake_launcher([])
    asyncio.run(cls.run_spec(spec, launch=launcher))
    selectors = [c.args[0] for c in page.waitForSelector.call_args_list]
    assert ".ready" in selectors


def test_click_before_assert_runs_in_order():
    spec = {
        "url": "about:blank",
        "click_before_assert": [".a", ".b", ".c"],
        "asserts": [],
    }
    launcher, _, page = _make_fake_launcher([])
    asyncio.run(cls.run_spec(spec, launch=launcher))
    clicks = [c.args[0] for c in page.click.call_args_list]
    assert clicks == [".a", ".b", ".c"]


def test_multiple_asserts_collect_all_failures():
    spec = {
        "url": "about:blank",
        "asserts": [
            {"type": "body_contains", "text": "x"},
            {"type": "body_contains", "text": "y"},
        ],
    }
    failures, _ = _run_spec(spec, [False, False])
    assert len(failures) == 2
    assert failures[0].index == 0
    assert failures[1].index == 1


def test_goto_uses_url_from_spec():
    spec = {"url": "https://example.invalid/page", "asserts": []}
    launcher, _, page = _make_fake_launcher([])
    asyncio.run(cls.run_spec(spec, launch=launcher))
    assert page.goto.call_args.args[0] == "https://example.invalid/page"


def test_browser_closed_even_on_exception():
    spec = {"url": "about:blank", "asserts": [{"type": "body_contains", "text": "x"}]}
    launcher, browser, page = _make_fake_launcher([])
    page.evaluate = AsyncMock(side_effect=RuntimeError("explode"))
    with pytest.raises(RuntimeError):
        asyncio.run(cls.run_spec(spec, launch=launcher))
    assert browser.close.called


# --- Retry logic ----------------------------------------------------------


def _make_launch_fn(evaluate_returns_per_attempt):
    """Return an async launcher that behaves differently across successive calls."""
    state = {"call": 0}

    async def fake_launch(*a, **kw):
        page = MagicMock()
        page.setViewport = AsyncMock()
        page.goto = AsyncMock()
        page.waitForSelector = AsyncMock()
        page.click = AsyncMock()
        returns = evaluate_returns_per_attempt[state["call"]]
        state["call"] += 1
        page.evaluate = AsyncMock(side_effect=list(returns))
        browser = MagicMock()
        browser.newPage = AsyncMock(return_value=page)
        browser.close = AsyncMock()
        return browser

    return fake_launch, state


def test_execute_retries_then_passes():
    spec = {"url": "about:blank", "asserts": [{"type": "body_contains", "text": "ok"}]}
    fake_launch, state = _make_launch_fn([[False], [False], [True]])
    failures = cls.execute(
        spec, retries=2, launch=fake_launch, sleep_fn=lambda _: None
    )
    assert failures == []
    assert state["call"] == 3


def test_execute_returns_failures_after_retries_exhausted():
    spec = {"url": "about:blank", "asserts": [{"type": "body_contains", "text": "no"}]}
    fake_launch, state = _make_launch_fn([[False], [False]])
    failures = cls.execute(
        spec, retries=1, launch=fake_launch, sleep_fn=lambda _: None
    )
    assert len(failures) == 1
    assert state["call"] == 2


def test_execute_zero_retries_single_attempt():
    spec = {"url": "about:blank", "asserts": [{"type": "body_contains", "text": "no"}]}
    fake_launch, state = _make_launch_fn([[False]])
    failures = cls.execute(
        spec, retries=0, launch=fake_launch, sleep_fn=lambda _: None
    )
    assert len(failures) == 1
    assert state["call"] == 1


# --- main() dispatch ------------------------------------------------------


def test_main_returns_zero_on_pass(tmp_path, monkeypatch):
    sp = tmp_path / "spec.json"
    sp.write_text(json.dumps({"url": "about:blank", "asserts": []}))
    monkeypatch.setattr(cls, "execute", lambda *a, **kw: [])
    rc = cls.main(["--spec", str(sp), "--retry", "0"])
    assert rc == 0


def test_main_returns_nonzero_on_assertion_fail(tmp_path, monkeypatch, capsys):
    sp = tmp_path / "spec.json"
    sp.write_text(json.dumps({"url": "about:blank", "asserts": []}))
    monkeypatch.setattr(
        cls,
        "execute",
        lambda *a, **kw: [cls.AssertionFailure(0, "body_contains", "missing x")],
    )
    rc = cls.main(["--spec", str(sp), "--retry", "0"])
    assert rc == 1
    captured = capsys.readouterr()
    assert "missing x" in captured.err


def test_main_returns_nonzero_on_malformed_spec(tmp_path, capsys):
    sp = tmp_path / "spec.json"
    sp.write_text("not valid json")
    rc = cls.main(["--spec", str(sp)])
    assert rc == 2
    captured = capsys.readouterr()
    assert "invalid spec" in captured.err
