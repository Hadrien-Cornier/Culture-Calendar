"""Tests for T2.4 — ground-truth JSON passed from check_live_site to persona LLM.

Before T2.4, the LLM persona critique saw a screenshot + a DOM snippet and
nothing else. Personas routinely marked present features as missing when the
screenshot was ambiguous and the DOM snippet truncated away the relevant
landmark. T2.4 captures per-selector ``{exists, count}`` observations against
the same pyppeteer page that feeds the screenshot and injects the payload
into the Anthropic prompt labelled as observed fact — so the LLM cannot
hallucinate that a feature is absent when the DOM proves otherwise.

Pyppeteer is mocked everywhere — no browser launches.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
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


cls = _load("check_live_site_gt", CHECK_PATH)
pc = _load("persona_critique_gt", CRITIQUE_PATH)


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
    page.evaluate = AsyncMock(side_effect=eval_fn) if eval_fn else AsyncMock(return_value=0)
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
        cls.run_spec_and_capture(
            {"url": "about:blank", "asserts": []}, launch=launcher
        )
    )
    assert len(out) == 3


# --- persona_critique.run_shared_page_capture_with_ground_truth ----------


def test_shared_page_capture_with_ground_truth_returns_seven_tuple():
    page = _make_page(html="<html>x</html>")
    launcher, _ = _make_launcher(page)
    out = pc.run_shared_page_capture_with_ground_truth(
        {"url": "about:blank", "asserts": []}, launch=launcher
    )
    assert len(out) == 7
    passed, rc, stdout, stderr, shot, dom, gt = out
    assert passed is True
    assert rc == 0
    assert "OK" in stdout
    assert stderr == ""
    assert shot
    assert "x" in dom
    assert isinstance(gt, dict)


def test_shared_page_capture_with_ground_truth_propagates_counts():
    """When the spec names a selector, the ground-truth dict must reflect
    the real querySelectorAll count from the shared page."""
    call_count = 0

    async def fake_eval(code, arg=None):
        nonlocal call_count
        if "querySelectorAll" in str(code):
            call_count += 1
            return 7 if arg == ".matched" else 0
        return True

    page = _make_page(eval_fn=fake_eval)
    launcher, _ = _make_launcher(page)
    spec = {
        "url": "about:blank",
        "asserts": [{"type": "selector_exists", "selector": ".matched"}],
    }
    _, _, _, _, _, _, gt = pc.run_shared_page_capture_with_ground_truth(
        spec, launch=launcher
    )
    assert gt[".matched"]["exists"] is True
    assert gt[".matched"]["count"] == 7


# --- format_ground_truth_for_prompt --------------------------------------


def test_format_ground_truth_renders_stable_json():
    payload = {".a": {"exists": True, "count": 2}, ".b": {"exists": False, "count": 0}}
    out = pc.format_ground_truth_for_prompt(payload)
    # Stable ordering is critical for prompt caching across runs.
    parsed = json.loads(out)
    assert parsed == payload
    # sort_keys=True so selectors are ordered alphabetically.
    assert out.index(".a") < out.index(".b")


def test_format_ground_truth_empty_returns_empty_string():
    assert pc.format_ground_truth_for_prompt({}) == ""


# --- build_anthropic_messages injects ground truth -----------------------


def _make_persona_result(name: str = "p", passed: bool = True) -> Any:
    return pc.PersonaResult(
        name=name, passed=passed, exit_code=0, stdout="OK\n", stderr=""
    )


def test_build_messages_appends_ground_truth_block():
    persona = {
        "persona": "p1",
        "url": "https://x",
        "llm": {"system_prompt": "SYS", "goals": "test"},
    }
    gt = {".event-card": {"exists": True, "count": 12}}
    system, messages = pc.build_anthropic_messages(
        persona,
        _make_persona_result(),
        "B64",
        "<html/>",
        ground_truth=gt,
    )
    texts = [
        b["text"]
        for b in messages[0]["content"]
        if isinstance(b, dict) and b.get("type") == "text"
    ]
    combined = "\n".join(texts)
    assert "Ground truth" in combined
    assert "event-card" in combined
    assert '"count":12' in combined or '"count": 12' in combined


def test_build_messages_omits_ground_truth_block_when_empty():
    persona = {"persona": "p1", "url": "x", "llm": {}}
    _, messages = pc.build_anthropic_messages(
        persona, _make_persona_result(), "B64", "<html/>", ground_truth={}
    )
    texts = [
        b["text"]
        for b in messages[0]["content"]
        if isinstance(b, dict) and b.get("type") == "text"
    ]
    assert not any("Ground truth" in t for t in texts)


def test_build_messages_ground_truth_sits_before_dom_snippet():
    """Ordering matters: a persona tempted to claim a selector is missing
    should see the contradicting ground-truth JSON before the truncated
    DOM slice, not after."""
    persona = {"persona": "p1", "url": "x", "llm": {}}
    gt = {".x": {"exists": True, "count": 1}}
    _, messages = pc.build_anthropic_messages(
        persona, _make_persona_result(), "B64", "<html/>", ground_truth=gt
    )
    blocks = messages[0]["content"]
    text_block_labels: list[str] = []
    for b in blocks:
        if isinstance(b, dict) and b.get("type") == "text":
            if "Ground truth" in b["text"]:
                text_block_labels.append("gt")
            elif "DOM snippet" in b["text"]:
                text_block_labels.append("dom")
    assert text_block_labels == ["gt", "dom"]


# --- call_anthropic_critique forwards ground_truth -----------------------


def test_call_anthropic_critique_passes_ground_truth_through():
    captured: dict[str, Any] = {}

    class _FakeBlock:
        type = "tool_use"
        name = pc.PERSONA_CRITIQUE_TOOL["name"]
        input = {"verdict": "PASS", "summary": "ok", "findings": []}

    class _FakeUsage:
        input_tokens = 10
        output_tokens = 5

    class _FakeResp:
        content = [_FakeBlock()]
        usage = _FakeUsage()

    class _Messages:
        def create(self, **kwargs):
            captured.update(kwargs)
            return _FakeResp()

    class _Client:
        messages = _Messages()

    gt = {".q": {"exists": True, "count": 3}}
    critique = pc.call_anthropic_critique(
        persona={"persona": "p", "url": "x", "llm": {}},
        result=_make_persona_result(),
        screenshot_b64="B64",
        dom_snippet="<html/>",
        client=_Client(),
        ground_truth=gt,
        log_fn=lambda _evt: None,
    )
    assert critique.verdict == "PASS"
    user_content = captured["messages"][0]["content"]
    texts = [
        b["text"]
        for b in user_content
        if isinstance(b, dict) and b.get("type") == "text"
    ]
    assert any("Ground truth" in t for t in texts)
    assert any('"count":3' in t or '"count": 3' in t for t in texts)


# --- run_all_personas threads ground_truth into the LLM call -------------


def _make_persona_file(
    dir_: Path,
    name: str,
    *,
    selector: str = ".event-card",
) -> Path:
    payload = {
        "persona": name,
        "url": "https://example.invalid/",
        "wait_ms": 0,
        "asserts": [{"type": "selector_exists", "selector": selector}],
        "llm": {"system_prompt": "SYS", "goals": "g"},
    }
    path = dir_ / f"{name}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_run_all_personas_forwards_ground_truth_to_build_messages(tmp_path):
    _make_persona_file(tmp_path, "p1", selector=".event-card")

    def shared_page_fn(_persona):
        # 7-tuple path: passed, rc, stdout, stderr, shot, dom, ground_truth
        return (
            True,
            0,
            "OK\n",
            "",
            "B64",
            "<html/>",
            {".event-card": {"exists": True, "count": 5}},
        )

    captured: dict[str, Any] = {}

    class _FakeBlock:
        type = "tool_use"
        name = pc.PERSONA_CRITIQUE_TOOL["name"]
        input = {"verdict": "PASS", "summary": "ok", "findings": []}

    class _FakeUsage:
        input_tokens = 1
        output_tokens = 1

    class _FakeResp:
        content = [_FakeBlock()]
        usage = _FakeUsage()

    class _Messages:
        def create(self, **kwargs):
            captured.update(kwargs)
            return _FakeResp()

    class _Client:
        messages = _Messages()

    results = pc.run_all_personas(
        tmp_path,
        CHECK_PATH,
        fast=False,
        shared_page_fn=shared_page_fn,
        anthropic_client_factory=lambda: _Client(),
    )
    assert len(results) == 1
    assert results[0].critique is not None
    assert results[0].critique.verdict == "PASS"
    # Ground-truth block must have landed in the Anthropic call.
    user_content = captured["messages"][0]["content"]
    gt_block = next(
        (
            b
            for b in user_content
            if isinstance(b, dict) and b.get("type") == "text"
            and "Ground truth" in b.get("text", "")
        ),
        None,
    )
    assert gt_block is not None
    assert "event-card" in gt_block["text"]
    assert "5" in gt_block["text"]


def test_run_all_personas_tolerates_legacy_six_tuple_shared_fn(tmp_path):
    """Old test fixtures (and bench_personas.py) still return 6-tuples
    without a ground-truth slot. The orchestrator must accept both shapes
    so those callers keep working — the only cost is an empty ground-truth
    block, which :func:`format_ground_truth_for_prompt` elides."""
    _make_persona_file(tmp_path, "p1")

    def legacy_shared(_persona):
        return (True, 0, "OK\n", "", "B64", "<html/>")

    class _FakeBlock:
        type = "tool_use"
        name = pc.PERSONA_CRITIQUE_TOOL["name"]
        input = {"verdict": "PASS", "summary": "ok", "findings": []}

    class _FakeUsage:
        input_tokens = 1
        output_tokens = 1

    class _FakeResp:
        content = [_FakeBlock()]
        usage = _FakeUsage()

    class _Messages:
        def create(self, **_kwargs):
            return _FakeResp()

    class _Client:
        messages = _Messages()

    results = pc.run_all_personas(
        tmp_path,
        CHECK_PATH,
        fast=False,
        shared_page_fn=legacy_shared,
        anthropic_client_factory=lambda: _Client(),
    )
    assert len(results) == 1
    assert results[0].critique is not None


# --- End-to-end: default shared_fn is the ground-truth-aware one ---------


def test_default_shared_fn_is_ground_truth_aware(monkeypatch, tmp_path):
    """When run_all_personas receives no explicit ``shared_page_fn``, it
    must default to :func:`run_shared_page_capture_with_ground_truth` —
    this is the regression guard against silently reverting to the 6-tuple
    variant and losing the ground-truth injection."""
    _make_persona_file(tmp_path, "p1")

    called: list[str] = []

    def stub_with_gt(spec):
        called.append("gt")
        return (True, 0, "OK\n", "", "B64", "<html/>", {".a": {"exists": True, "count": 1}})

    monkeypatch.setattr(
        pc, "run_shared_page_capture_with_ground_truth", stub_with_gt
    )

    class _FakeBlock:
        type = "tool_use"
        name = pc.PERSONA_CRITIQUE_TOOL["name"]
        input = {"verdict": "PASS", "summary": "ok", "findings": []}

    class _FakeUsage:
        input_tokens = 1
        output_tokens = 1

    class _FakeResp:
        content = [_FakeBlock()]
        usage = _FakeUsage()

    class _Messages:
        def create(self, **_kwargs):
            return _FakeResp()

    class _Client:
        messages = _Messages()

    results = pc.run_all_personas(
        tmp_path,
        CHECK_PATH,
        fast=False,
        anthropic_client_factory=lambda: _Client(),
    )
    assert called == ["gt"]
    assert results[0].critique is not None
