"""Tests for the shared-page flow between check_live_site and persona_critique.

Before T2.1, persona_critique asserted via subprocess against check_live_site.py
and then opened a *second* pyppeteer session for the screenshot. The two
navigations produced screenshots whose DOM no longer matched the asserted
state — personas claimed features were missing when they were merely
below-the-fold in a freshly-loaded viewport.

T2.1 unifies this: one ``browser.newPage`` + one ``page.goto`` per persona,
asserts evaluated against the same page that feeds the screenshot.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import subprocess
import sys
import types
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CHECK_PATH = REPO_ROOT / "scripts" / "check_live_site.py"
CRITIQUE_PATH = REPO_ROOT / "scripts" / "persona_critique.py"


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


cls = _load("check_live_site_shared", CHECK_PATH)
pc = _load("persona_critique_shared", CRITIQUE_PATH)


def _make_persona_file(
    dir_: Path,
    name: str,
    *,
    url: str = "https://example.invalid/",
    asserts: list[dict[str, Any]] | None = None,
) -> Path:
    payload = {
        "persona": name,
        "url": url,
        "wait_ms": 0,
        "asserts": asserts or [],
        "llm": {"system_prompt": "SYS", "goals": "g"},
    }
    path = dir_ / f"{name}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _make_fake_launcher(
    evaluate_returns: list[Any] | None = None,
    *,
    screenshot_bytes: bytes = b"PNGDATA",
    html: str = "<html><body>ok</body></html>",
):
    """Return an AsyncMock pyppeteer launcher plus its browser/page mocks."""
    page = MagicMock()
    page.setViewport = AsyncMock()
    page.goto = AsyncMock()
    page.waitForSelector = AsyncMock()
    page.click = AsyncMock()
    page.evaluate = AsyncMock(side_effect=list(evaluate_returns or []))
    page.screenshot = AsyncMock(return_value=screenshot_bytes)
    page.content = AsyncMock(return_value=html)
    browser = MagicMock()
    browser.newPage = AsyncMock(return_value=page)
    browser.close = AsyncMock()
    launcher = AsyncMock(return_value=browser)
    return launcher, browser, page


# --- check_live_site.run_spec_and_capture -------------------------------


def test_run_spec_and_capture_uses_one_goto():
    """Shared-page flow makes exactly one page.goto call per invocation —
    the bug was persona_critique navigating a second time before capture."""
    spec = {"url": "https://example.invalid/", "asserts": []}
    launcher, browser, page = _make_fake_launcher([])
    failures, b64, html = asyncio.run(cls.run_spec_and_capture(spec, launch=launcher))
    assert failures == []
    assert page.goto.call_count == 1
    assert page.screenshot.call_count == 1
    assert page.content.call_count == 1
    assert browser.close.called


def test_run_spec_and_capture_returns_base64_screenshot():
    spec = {"url": "about:blank", "asserts": []}
    launcher, _, _ = _make_fake_launcher([], screenshot_bytes=b"\x89PNG\r\n\x1a\n")
    _, b64, _ = asyncio.run(cls.run_spec_and_capture(spec, launch=launcher))
    import base64 as _b64

    assert _b64.b64decode(b64) == b"\x89PNG\r\n\x1a\n"


def test_run_spec_and_capture_returns_full_html():
    spec = {"url": "about:blank", "asserts": []}
    launcher, _, _ = _make_fake_launcher(
        [], html="<html><body>everything</body></html>"
    )
    _, _, html = asyncio.run(cls.run_spec_and_capture(spec, launch=launcher))
    assert html == "<html><body>everything</body></html>"


def test_run_spec_and_capture_asserts_evaluated_on_same_page():
    """Assertions must run against the captured DOM, not a separate load."""
    spec = {
        "url": "about:blank",
        "asserts": [{"type": "body_contains", "text": "hi"}],
    }
    launcher, _, page = _make_fake_launcher([True])
    failures, _, _ = asyncio.run(cls.run_spec_and_capture(spec, launch=launcher))
    assert failures == []
    assert page.evaluate.call_count == 1


def test_run_spec_and_capture_collects_failures_but_still_captures():
    spec = {
        "url": "about:blank",
        "asserts": [{"type": "body_contains", "text": "missing"}],
    }
    launcher, _, page = _make_fake_launcher([False])
    failures, b64, html = asyncio.run(cls.run_spec_and_capture(spec, launch=launcher))
    assert len(failures) == 1
    assert "missing" in failures[0].reason
    # Capture happens even when asserts fail — the LLM still needs to look.
    assert b64 != ""
    assert html != ""
    assert page.screenshot.call_count == 1


def test_run_spec_and_capture_fullpage_flag_propagates():
    spec = {"url": "about:blank", "asserts": []}
    launcher, _, page = _make_fake_launcher([])
    asyncio.run(cls.run_spec_and_capture(spec, launch=launcher, full_page=True))
    args = page.screenshot.call_args.args[0]
    assert args["fullPage"] is True


def test_run_spec_and_capture_fullpage_defaults_false():
    spec = {"url": "about:blank", "asserts": []}
    launcher, _, page = _make_fake_launcher([])
    asyncio.run(cls.run_spec_and_capture(spec, launch=launcher))
    args = page.screenshot.call_args.args[0]
    assert args["fullPage"] is False


def test_run_spec_and_capture_honors_mobile_viewport():
    spec = {"url": "about:blank", "mobile": True, "asserts": []}
    launcher, _, page = _make_fake_launcher([])
    asyncio.run(cls.run_spec_and_capture(spec, launch=launcher))
    viewport = page.setViewport.call_args.args[0]
    assert viewport["width"] == 375
    assert viewport["isMobile"] is True


def test_run_spec_and_capture_runs_click_before_assert_on_same_page():
    spec = {
        "url": "about:blank",
        "click_before_assert": [".tab-2"],
        "asserts": [{"type": "body_contains", "text": "tab-2-content"}],
    }
    launcher, _, page = _make_fake_launcher([True])
    failures, _, _ = asyncio.run(cls.run_spec_and_capture(spec, launch=launcher))
    assert failures == []
    assert page.click.call_args.args[0] == ".tab-2"
    # Critical: only one navigation — click happens on the same page that
    # evaluates the assert and gets screenshotted.
    assert page.goto.call_count == 1


def test_run_spec_and_capture_closes_browser_on_exception():
    spec = {"url": "about:blank", "asserts": [{"type": "body_contains", "text": "x"}]}
    launcher, browser, page = _make_fake_launcher([])
    page.evaluate = AsyncMock(side_effect=RuntimeError("explode"))
    with pytest.raises(RuntimeError):
        asyncio.run(cls.run_spec_and_capture(spec, launch=launcher))
    assert browser.close.called


# --- persona_critique.run_shared_page_capture ---------------------------


def test_run_shared_page_capture_sync_wrapper_returns_six_tuple(tmp_path):
    """The sync wrapper is what run_all_personas consumes; shape must match
    run_check_live_site's prefix plus (shot, dom)."""
    spec = {"url": "about:blank", "asserts": []}
    launcher, _, _ = _make_fake_launcher([], html="<html>snapshot</html>")
    passed, rc, stdout, stderr, shot, dom = pc.run_shared_page_capture(
        spec, launch=launcher
    )
    assert passed is True
    assert rc == 0
    assert "OK" in stdout
    assert stderr == ""
    assert shot  # non-empty base64 string
    assert "snapshot" in dom


def test_run_shared_page_capture_reports_fail_with_stderr_reason():
    spec = {
        "url": "about:blank",
        "asserts": [{"type": "body_contains", "text": "absent"}],
    }
    launcher, _, _ = _make_fake_launcher([False])
    passed, rc, stdout, stderr, shot, dom = pc.run_shared_page_capture(
        spec, launch=launcher
    )
    assert passed is False
    assert rc == 1
    assert "absent" in stderr
    # Capture still happens even on assert failure — the LLM needs the image.
    assert shot
    assert dom


def test_run_shared_page_capture_truncates_dom_to_limit():
    spec = {"url": "about:blank", "asserts": []}
    long_html = "<html>" + ("x" * 20_000) + "</html>"
    launcher, _, _ = _make_fake_launcher([], html=long_html)
    _, _, _, _, _, dom = pc.run_shared_page_capture(
        spec, launch=launcher, dom_max_bytes=500
    )
    assert len(dom) == 500


# --- run_all_personas: shared-page is the default LLM path --------------


def test_llm_mode_uses_shared_page_fn_not_subprocess(tmp_path):
    """When no capture_fn is supplied in LLM mode, run_all_personas must
    route through shared_page_fn — no subprocess call to check_live_site.py."""
    _make_persona_file(tmp_path, "p1")
    _make_persona_file(tmp_path, "p2")

    subprocess_calls: list[list[str]] = []

    def forbidden_subprocess(cmd, **_kwargs):
        subprocess_calls.append(list(cmd))
        return subprocess.CompletedProcess(
            args=cmd, returncode=99, stdout="", stderr="",
        )

    shared_calls: list[str] = []

    def fake_shared_page(persona):
        shared_calls.append(persona["persona"])
        return (True, 0, "OK\n", "", "B64", "<html>x</html>")

    tool_block = types.SimpleNamespace(
        type="tool_use",
        name=pc.PERSONA_CRITIQUE_TOOL["name"],
        input={"verdict": "PASS", "summary": "ok", "findings": []},
    )
    resp = types.SimpleNamespace(content=[tool_block])
    client = MagicMock()
    client.messages.create.return_value = resp
    factory = MagicMock(return_value=client)

    results = pc.run_all_personas(
        tmp_path,
        CHECK_PATH,
        fast=False,
        subprocess_runner=forbidden_subprocess,
        shared_page_fn=fake_shared_page,
        anthropic_client_factory=factory,
    )

    assert len(results) == 2
    assert subprocess_calls == [], (
        "shared-page flow must not shell out to check_live_site.py"
    )
    assert shared_calls == ["p1", "p2"]
    # Each persona got exactly one Anthropic call using the shared capture.
    assert client.messages.create.call_count == 2
    for r in results:
        assert r.passed is True
        assert r.critique is not None
        assert r.critique.verdict == "PASS"


def test_shared_page_failure_is_recorded_not_fatal(tmp_path):
    """If the shared-page capture explodes on one persona, that persona
    records critique_error=... but the next persona still runs."""
    _make_persona_file(tmp_path, "p1")
    _make_persona_file(tmp_path, "p2")

    def flaky_shared_page(persona):
        if persona["persona"] == "p1":
            raise RuntimeError("browser crashed")
        return (True, 0, "OK\n", "", "B64", "<html>ok</html>")

    tool_block = types.SimpleNamespace(
        type="tool_use",
        name=pc.PERSONA_CRITIQUE_TOOL["name"],
        input={"verdict": "PASS", "summary": "ok", "findings": []},
    )
    resp = types.SimpleNamespace(content=[tool_block])
    client = MagicMock()
    client.messages.create.return_value = resp
    factory = MagicMock(return_value=client)

    results = pc.run_all_personas(
        tmp_path,
        CHECK_PATH,
        fast=False,
        shared_page_fn=flaky_shared_page,
        anthropic_client_factory=factory,
    )
    by_name = {r.name: r for r in results}
    assert by_name["p1"].critique is None
    assert "browser crashed" in (by_name["p1"].critique_error or "")
    assert by_name["p2"].critique is not None
    assert by_name["p2"].critique.verdict == "PASS"


def test_shared_page_propagates_assert_failures_to_persona_result(tmp_path):
    """Structural failures from the shared page must flow into PersonaResult
    so the scorecard still reports them."""
    _make_persona_file(tmp_path, "p1")

    def failing_shared_page(_persona):
        return (False, 1, "", "assert[0] (selector_exists): missing .x", "B64", "<html/>")

    tool_block = types.SimpleNamespace(
        type="tool_use",
        name=pc.PERSONA_CRITIQUE_TOOL["name"],
        input={"verdict": "FAIL", "summary": "missing x", "findings": []},
    )
    resp = types.SimpleNamespace(content=[tool_block])
    client = MagicMock()
    client.messages.create.return_value = resp

    results = pc.run_all_personas(
        tmp_path,
        CHECK_PATH,
        fast=False,
        shared_page_fn=failing_shared_page,
        anthropic_client_factory=MagicMock(return_value=client),
    )
    assert len(results) == 1
    r = results[0]
    assert r.passed is False
    assert r.exit_code == 1
    assert "missing .x" in r.stderr
    assert r.critique is not None
    assert r.critique.verdict == "FAIL"


def test_fast_mode_bypasses_shared_page(tmp_path):
    """fast=True must still shell out to check_live_site.py; shared-page is
    only for the LLM path where we need the screenshot anyway."""
    _make_persona_file(tmp_path, "p1")

    class _Runner:
        def __init__(self):
            self.calls = 0

        def __call__(self, cmd, **_kwargs):
            self.calls += 1
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="OK\n", stderr=""
            )

    runner = _Runner()

    def forbidden_shared_page(_persona):
        raise AssertionError("shared_page_fn must not run in --fast mode")

    results = pc.run_all_personas(
        tmp_path,
        CHECK_PATH,
        fast=True,
        subprocess_runner=runner,
        shared_page_fn=forbidden_shared_page,
    )
    assert len(results) == 1
    assert results[0].passed is True
    assert runner.calls == 1


def test_explicit_capture_fn_preserves_legacy_two_session_path(tmp_path):
    """Backward-compat: tests and benchmarks that inject ``capture_fn`` still
    get the old behavior (subprocess assert → fresh-page capture). This keeps
    bench_personas.py working without a rewrite."""
    _make_persona_file(tmp_path, "p1")
    runner_calls: list[list[str]] = []

    def subprocess_runner(cmd, **_kwargs):
        runner_calls.append(list(cmd))
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="OK\n", stderr=""
        )

    capture_calls: list[str] = []

    def capture(persona):
        capture_calls.append(persona["persona"])
        return ("LEGACY_B64", "<html>legacy</html>")

    def forbidden_shared_page(_persona):
        raise AssertionError(
            "shared_page_fn must not run when capture_fn is supplied"
        )

    tool_block = types.SimpleNamespace(
        type="tool_use",
        name=pc.PERSONA_CRITIQUE_TOOL["name"],
        input={"verdict": "PASS", "summary": "ok", "findings": []},
    )
    client = MagicMock()
    client.messages.create.return_value = types.SimpleNamespace(content=[tool_block])

    results = pc.run_all_personas(
        tmp_path,
        CHECK_PATH,
        fast=False,
        subprocess_runner=subprocess_runner,
        capture_fn=capture,
        shared_page_fn=forbidden_shared_page,
        anthropic_client_factory=MagicMock(return_value=client),
    )
    assert len(results) == 1
    assert len(runner_calls) == 1, "legacy path still asserts via subprocess"
    assert capture_calls == ["p1"]


def test_shared_page_respects_cost_cap(tmp_path):
    for name in ("a", "b", "c"):
        _make_persona_file(tmp_path, name)

    def shared_page(_persona):
        return (True, 0, "OK\n", "", "B", "<x/>")

    tool_block = types.SimpleNamespace(
        type="tool_use",
        name=pc.PERSONA_CRITIQUE_TOOL["name"],
        input={"verdict": "PASS", "summary": "ok", "findings": []},
    )
    client = MagicMock()
    client.messages.create.return_value = types.SimpleNamespace(content=[tool_block])

    with pytest.raises(RuntimeError, match="cost cap"):
        pc.run_all_personas(
            tmp_path,
            CHECK_PATH,
            fast=False,
            shared_page_fn=shared_page,
            anthropic_client_factory=MagicMock(return_value=client),
            max_llm_calls=2,
        )


# --- End-to-end sanity: real run_spec_and_capture via persona wrapper ----


def test_run_shared_page_capture_uses_single_goto_via_launcher_injection():
    """Most important regression guard for T2.1: when persona_critique.run_
    shared_page_capture drives check_live_site.run_spec_and_capture with a
    launcher injected through the exposed keyword, the resulting pyppeteer
    page.goto is called exactly once."""
    launcher, _, page = _make_fake_launcher([], html="<html>once</html>")
    spec = {"url": "about:blank", "asserts": []}
    passed, rc, stdout, stderr, shot, dom = pc.run_shared_page_capture(
        spec, launch=launcher
    )
    assert passed is True
    assert rc == 0
    assert page.goto.call_count == 1
    assert page.screenshot.call_count == 1
    assert "once" in dom
