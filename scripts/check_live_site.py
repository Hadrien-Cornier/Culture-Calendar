#!/usr/bin/env python3
"""Live-site verification tool using pyppeteer.

Loads a URL, optionally with a mobile viewport, waits for readiness,
performs a sequence of clicks, then evaluates a list of assertions from a
JSON spec file. Exits 0 on success, non-zero with reasons on stderr.

Spec JSON schema:
    {
      "url": "https://...",                 # required
      "mobile": true | false,                # optional (default false)
      "wait_ms": 1000,                       # optional settle delay
      "wait_for_selector": ".ready",         # optional CSS selector
      "click_before_assert": [".trigger"],   # optional sequential clicks
      "pre_screenshot_actions": [             # optional — replayed after asserts,
        {"type": "scroll", "y": 800},         #   before screenshot/DOM capture,
        {"type": "click",  "selector": ".x"}, #   so LLM personas see a
        {"type": "type",   "selector": "#q",  #   deliberately-chosen state
         "text": "austin"}                    #   (below-the-fold content,
      ],                                      #   opened disclosures, search
      "asserts": [                            # required list
        {"type": "body_contains",     "text": "..."},
        {"type": "body_not_contains", "text": "..."},
        {"type": "selector_exists",   "selector": "..."},
        {"type": "selector_min_count","selector": "...", "min": N},
        {"type": "selector_max_count","selector": "...", "max": N},
        {"type": "js_truthy",         "expression": "..."}
      ]
    }
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

DEFAULT_RETRY = 2
DEFAULT_NAV_TIMEOUT_MS = 30_000
DEFAULT_SELECTOR_TIMEOUT_MS = 10_000
CLICK_SETTLE_MS = 250
RETRY_BACKOFF_S = 5

MOBILE_VIEWPORT: dict[str, Any] = {
    "width": 375,
    "height": 812,
    "isMobile": True,
    "hasTouch": True,
    "deviceScaleFactor": 2,
}
DESKTOP_VIEWPORT: dict[str, Any] = {"width": 1280, "height": 800}


@dataclass(frozen=True)
class AssertionFailure:
    index: int
    assert_type: str
    reason: str

    def format(self) -> str:
        return f"assert[{self.index}] ({self.assert_type}): {self.reason}"


def load_spec(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"spec must be a JSON object, got {type(data).__name__}")
    if "url" not in data or not isinstance(data["url"], str):
        raise ValueError("spec missing required 'url' string")
    asserts = data.get("asserts", [])
    if not isinstance(asserts, list):
        raise ValueError("'asserts' must be a list")
    clicks = data.get("click_before_assert", [])
    if clicks is not None and not isinstance(clicks, list):
        raise ValueError("'click_before_assert' must be a list")
    pre_actions = data.get("pre_screenshot_actions")
    if pre_actions is not None and not isinstance(pre_actions, list):
        raise ValueError("'pre_screenshot_actions' must be a list")
    return data


def _wrap_expr(expr: str) -> str:
    """Wrap a JS snippet as a zero-arg function for pyppeteer evaluate.

    If the expression contains statements (`;`) or a bare `return`, wrap it
    as a block function body; otherwise wrap it as an arrow-return expression.
    """
    if ";" in expr or re.search(r"\breturn\b", expr):
        return "() => { " + expr + " }"
    return "() => (" + expr + ")"


async def _evaluate_assert(page: Any, a: dict[str, Any]) -> str | None:
    t = a.get("type")
    if t == "body_contains":
        text = a["text"]
        found = await page.evaluate(
            "(t) => document.body.innerText.includes(t)", text
        )
        return None if found else f"body did not contain {text!r}"
    if t == "body_not_contains":
        text = a["text"]
        found = await page.evaluate(
            "(t) => document.body.innerText.includes(t)", text
        )
        return None if not found else f"body unexpectedly contained {text!r}"
    if t == "selector_exists":
        sel = a["selector"]
        count = await page.evaluate(
            "(s) => document.querySelectorAll(s).length", sel
        )
        return None if count >= 1 else f"selector {sel!r} matched 0 elements"
    if t == "selector_min_count":
        sel = a["selector"]
        min_ = int(a["min"])
        count = await page.evaluate(
            "(s) => document.querySelectorAll(s).length", sel
        )
        if count >= min_:
            return None
        return f"selector {sel!r} matched {count}, expected >= {min_}"
    if t == "selector_max_count":
        sel = a["selector"]
        max_ = int(a["max"])
        count = await page.evaluate(
            "(s) => document.querySelectorAll(s).length", sel
        )
        if count <= max_:
            return None
        return f"selector {sel!r} matched {count}, expected <= {max_}"
    if t == "js_truthy":
        expr = a["expression"]
        code = _wrap_expr(expr)
        try:
            result = await page.evaluate(code)
        except Exception as exc:  # noqa: BLE001
            return f"expression raised: {exc}"
        return None if result else f"expression evaluated falsy: {expr!r}"
    return f"unknown assert type {t!r}"


_CANDIDATE_BROWSER_PATHS = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium-browser",
    "/usr/bin/chromium",
)


def _resolve_browser_executable() -> str | None:
    """Return a browser executablePath pyppeteer can launch, or None.

    pyppeteer's bundled Chromium 117 x64 crashes under Rosetta on Apple
    Silicon. Prefer an installed system browser so the validator works on
    a plain developer laptop without `pyppeteer-install` heroics.

    Priority: PYPPETEER_EXECUTABLE_PATH env var, then common install paths.
    """
    import os
    env = os.environ.get("PYPPETEER_EXECUTABLE_PATH")
    if env and os.path.exists(env):
        return env
    for p in _CANDIDATE_BROWSER_PATHS:
        if os.path.exists(p):
            return p
    return None


async def _prepare_page(page: Any, spec: dict[str, Any]) -> None:
    """Navigate ``page`` to the spec URL and apply its wait/click directives.

    Extracted so the assert-only path and the capture-also path share one
    implementation — navigating twice would defeat the shared-page refactor.
    """
    viewport = MOBILE_VIEWPORT if spec.get("mobile") else DESKTOP_VIEWPORT
    await page.setViewport(viewport)
    await page.goto(
        spec["url"],
        waitUntil="networkidle2",
        timeout=DEFAULT_NAV_TIMEOUT_MS,
    )
    wait_for_selector = spec.get("wait_for_selector")
    if wait_for_selector:
        await page.waitForSelector(
            wait_for_selector, timeout=DEFAULT_SELECTOR_TIMEOUT_MS
        )
    wait_ms = spec.get("wait_ms")
    if wait_ms:
        await asyncio.sleep(wait_ms / 1000.0)
    for sel in spec.get("click_before_assert") or []:
        await page.waitForSelector(sel, timeout=DEFAULT_SELECTOR_TIMEOUT_MS)
        await page.click(sel)
        await asyncio.sleep(CLICK_SETTLE_MS / 1000.0)


async def _evaluate_asserts(
    page: Any, spec: dict[str, Any]
) -> list[AssertionFailure]:
    failures: list[AssertionFailure] = []
    for i, a in enumerate(spec.get("asserts") or []):
        reason = await _evaluate_assert(page, a)
        if reason:
            failures.append(AssertionFailure(i, a.get("type", "?"), reason))
    return failures


async def _run_pre_screenshot_actions(
    page: Any, actions: list[dict[str, Any]]
) -> None:
    """Replay scroll/click/type directives on ``page`` in declared order.

    Personas use these to put the page into a specific visual state before
    the LLM sees the screenshot — scrolled to a section, disclosure panels
    opened, search inputs populated — so the model doesn't flag implemented
    features as missing merely because they're below the fold.

    Raises ``ValueError`` on unknown action types to surface spec typos
    instead of silently dropping them.
    """
    for action in actions:
        if not isinstance(action, dict):
            raise ValueError(
                f"pre_screenshot_actions entries must be objects, got {type(action).__name__}"
            )
        t = action.get("type")
        if t == "scroll":
            x = int(action.get("x", 0))
            y = int(action.get("y", 0))
            await page.evaluate(
                "(c) => window.scrollTo(c.x, c.y)", {"x": x, "y": y}
            )
            await asyncio.sleep(CLICK_SETTLE_MS / 1000.0)
        elif t == "click":
            sel = action["selector"]
            await page.waitForSelector(sel, timeout=DEFAULT_SELECTOR_TIMEOUT_MS)
            await page.click(sel)
            await asyncio.sleep(CLICK_SETTLE_MS / 1000.0)
        elif t == "type":
            sel = action["selector"]
            text = action.get("text", "")
            await page.waitForSelector(sel, timeout=DEFAULT_SELECTOR_TIMEOUT_MS)
            await page.type(sel, text)
            await asyncio.sleep(CLICK_SETTLE_MS / 1000.0)
        else:
            raise ValueError(f"unknown pre_screenshot_action type {t!r}")


async def run_spec(
    spec: dict[str, Any],
    launch: Callable[..., Awaitable[Any]] | None = None,
) -> list[AssertionFailure]:
    """Open the URL in a headless browser and evaluate the spec's asserts."""
    if launch is None:
        from pyppeteer import launch as _launch
        launch = _launch
    launch_kwargs: dict[str, Any] = {"headless": True, "args": ["--no-sandbox"]}
    exe = _resolve_browser_executable()
    if exe:
        launch_kwargs["executablePath"] = exe
    browser = await launch(**launch_kwargs)
    try:
        page = await browser.newPage()
        await _prepare_page(page, spec)
        return await _evaluate_asserts(page, spec)
    finally:
        await browser.close()


async def run_spec_and_capture(
    spec: dict[str, Any],
    launch: Callable[..., Awaitable[Any]] | None = None,
    *,
    full_page: bool = False,
) -> tuple[list[AssertionFailure], str, str]:
    """Run asserts AND capture screenshot + DOM on the same page.

    Returns ``(failures, screenshot_b64, dom_html)``. The screenshot is a
    base64-encoded PNG; ``dom_html`` is the page's full outer HTML. Callers
    may truncate the DOM to fit LLM context limits.

    Shared-page is the point: persona_critique must not navigate twice —
    one ``page.goto`` per persona keeps the asserted state and the captured
    image consistent.
    """
    if launch is None:
        from pyppeteer import launch as _launch
        launch = _launch
    launch_kwargs: dict[str, Any] = {"headless": True, "args": ["--no-sandbox"]}
    exe = _resolve_browser_executable()
    if exe:
        launch_kwargs["executablePath"] = exe
    browser = await launch(**launch_kwargs)
    try:
        page = await browser.newPage()
        await _prepare_page(page, spec)
        failures = await _evaluate_asserts(page, spec)
        pre_actions = spec.get("pre_screenshot_actions") or []
        if pre_actions:
            await _run_pre_screenshot_actions(page, pre_actions)
        shot_bytes = await page.screenshot({"type": "png", "fullPage": full_page})
        html = await page.content()
        b64 = base64.b64encode(shot_bytes).decode("ascii")
        return failures, b64, html
    finally:
        await browser.close()


def execute(
    spec: dict[str, Any],
    retries: int = DEFAULT_RETRY,
    launch: Callable[..., Awaitable[Any]] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> list[AssertionFailure]:
    """Run `run_spec` with up to `retries` additional attempts on failure.

    Each retry sleeps RETRY_BACKOFF_S seconds (injectable for tests) to let
    CDN caches catch up after a fresh deploy.
    """
    last: list[AssertionFailure] = []
    for attempt in range(retries + 1):
        last = asyncio.run(run_spec(spec, launch=launch))
        if not last:
            return []
        if attempt < retries:
            sleep_fn(RETRY_BACKOFF_S)
    return last


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="check_live_site.py",
        description=(
            "Load a URL via pyppeteer and verify assertions from a spec file."
        ),
    )
    p.add_argument(
        "--spec",
        required=True,
        type=Path,
        help="Path to a spec JSON file (see module docstring for schema).",
    )
    p.add_argument(
        "--retry",
        type=int,
        default=DEFAULT_RETRY,
        help=(
            f"Additional retries on assertion failure "
            f"(default {DEFAULT_RETRY}, for CDN cache propagation)."
        ),
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if not args.spec.is_file():
        print(f"error: spec file not found: {args.spec}", file=sys.stderr)
        return 2
    try:
        spec = load_spec(args.spec)
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"error: invalid spec: {exc}", file=sys.stderr)
        return 2
    failures = execute(spec, retries=max(0, args.retry))
    if not failures:
        print("OK")
        return 0
    for f in failures:
        print(f.format(), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
