#!/usr/bin/env python3
"""Persona critique orchestrator.

Iterates ``.overnight/personas/*.json``, runs ``scripts/check_live_site.py``
against each persona spec, and optionally asks Anthropic Claude Sonnet 4.6
for a qualitative critique given a pyppeteer-captured screenshot plus a DOM
snippet.

Two modes:

- ``--fast`` (default for smoke tests): structural asserts only, no
  Anthropic calls. Safe to run from CI and overnight validate oracles.
- LLM mode (the default when ``--fast`` is absent): one Anthropic call per
  persona, with a hard cap of ``MAX_LLM_CALLS`` per invocation.

The resulting markdown scorecard is written to ``--out``.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import importlib.util
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Sequence

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover — dotenv is a project dep
    def load_dotenv(*_args: Any, **_kwargs: Any) -> None:
        return None

load_dotenv()

MAX_LLM_CALLS = 6
DOM_SNIPPET_MAX_BYTES = 10_000
SONNET_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_TOKENS = 1024
DEFAULT_TEMPERATURE = 0.2

DEFAULT_PERSONAS_DIR = Path(".overnight/personas")
DEFAULT_CHECK_SCRIPT = Path("scripts/check_live_site.py")
DEFAULT_CHECK_RETRIES = 0
SUBPROCESS_TIMEOUT_S = 180


@dataclass(frozen=True)
class PersonaResult:
    """Outcome of a single persona's structural + optional LLM pass."""

    name: str
    passed: bool
    exit_code: int
    stdout: str
    stderr: str
    critique: str | None = None
    critique_error: str | None = None


def load_persona_paths(personas_dir: Path) -> list[Path]:
    """Return sorted list of persona JSON files. Raises if dir missing."""
    if not personas_dir.is_dir():
        raise FileNotFoundError(
            f"personas directory not found: {personas_dir}"
        )
    paths = sorted(personas_dir.glob("*.json"))
    if not paths:
        raise FileNotFoundError(
            f"no *.json persona specs found under {personas_dir}"
        )
    return paths


def run_check_live_site(
    check_script: Path,
    spec_path: Path,
    *,
    retries: int = DEFAULT_CHECK_RETRIES,
    python_exe: str | None = None,
    subprocess_runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    timeout: int = SUBPROCESS_TIMEOUT_S,
) -> tuple[bool, int, str, str]:
    """Run ``check_live_site.py --spec <path>`` and capture its outcome."""
    exe = python_exe or sys.executable
    cmd = [
        exe,
        str(check_script),
        "--spec",
        str(spec_path),
        "--retry",
        str(retries),
    ]
    try:
        proc = subprocess_runner(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:  # pragma: no cover
        return False, 124, "", f"timeout after {timeout}s: {exc}"
    passed = proc.returncode == 0
    return passed, proc.returncode, proc.stdout or "", proc.stderr or ""


# --- Pyppeteer screenshot + DOM capture (for LLM mode) -------------------


def _load_check_live_site_module() -> Any:
    """Import sibling ``check_live_site.py`` without requiring a package."""
    here = Path(__file__).resolve().parent / "check_live_site.py"
    spec = importlib.util.spec_from_file_location("_check_live_site", here)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


async def _async_capture(
    spec: dict[str, Any],
    launch: Callable[..., Awaitable[Any]] | None = None,
) -> tuple[str, str]:
    """Navigate to the persona URL, return (screenshot_b64, dom_snippet)."""
    cls = _load_check_live_site_module()
    if launch is None:
        from pyppeteer import launch as _launch
        launch = _launch
    launch_kwargs: dict[str, Any] = {
        "headless": True,
        "args": ["--no-sandbox"],
    }
    exe = cls._resolve_browser_executable()
    if exe:
        launch_kwargs["executablePath"] = exe
    browser = await launch(**launch_kwargs)
    try:
        page = await browser.newPage()
        viewport = (
            cls.MOBILE_VIEWPORT if spec.get("mobile") else cls.DESKTOP_VIEWPORT
        )
        await page.setViewport(viewport)
        await page.goto(
            spec["url"],
            waitUntil="networkidle2",
            timeout=cls.DEFAULT_NAV_TIMEOUT_MS,
        )
        wait_for_selector = spec.get("wait_for_selector")
        if wait_for_selector:
            try:
                await page.waitForSelector(
                    wait_for_selector,
                    timeout=cls.DEFAULT_SELECTOR_TIMEOUT_MS,
                )
            except Exception:  # noqa: BLE001
                pass
        wait_ms = spec.get("wait_ms")
        if wait_ms:
            await asyncio.sleep(wait_ms / 1000.0)
        shot_bytes = await page.screenshot({"type": "png", "fullPage": False})
        html = await page.content()
        snippet = html[:DOM_SNIPPET_MAX_BYTES]
        b64 = base64.b64encode(shot_bytes).decode("ascii")
        return b64, snippet
    finally:
        await browser.close()


def capture_screenshot_and_dom(
    spec: dict[str, Any],
    launch: Callable[..., Awaitable[Any]] | None = None,
) -> tuple[str, str]:
    """Sync wrapper around :func:`_async_capture`."""
    return asyncio.run(_async_capture(spec, launch=launch))


# --- Anthropic call ------------------------------------------------------


def build_anthropic_messages(
    persona: dict[str, Any],
    result: PersonaResult,
    screenshot_b64: str,
    dom_snippet: str,
) -> tuple[str, list[dict[str, Any]]]:
    """Return (system_prompt, messages) for the Anthropic call."""
    llm = persona.get("llm") or {}
    system_prompt = (llm.get("system_prompt") or "").strip()
    goals = (llm.get("goals") or "").strip()

    header = [
        f"Persona: {persona.get('persona', '(unnamed)')}.",
        f"Goals: {goals}" if goals else "",
        f"URL: {persona.get('url', '(unknown)')}.",
        f"Structural check: {'PASS' if result.passed else 'FAIL'} (exit {result.exit_code}).",
    ]
    if result.stderr.strip():
        header.append("Structural stderr:\n" + result.stderr.strip())
    header.append(
        "Below: a PNG screenshot of the rendered page, followed by the "
        f"first {DOM_SNIPPET_MAX_BYTES} bytes of outer HTML."
    )
    header.append(
        "Respond in 3-5 sentences covering (a) whether the experience "
        "delivers on your goals, (b) any failure modes you notice, and "
        "(c) the one concrete fix you'd ship first."
    )
    user_text = "\n\n".join(line for line in header if line)

    user_content: list[dict[str, Any]] = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": screenshot_b64,
            },
        },
        {"type": "text", "text": user_text},
    ]
    if dom_snippet:
        user_content.append(
            {
                "type": "text",
                "text": "DOM snippet (truncated):\n" + dom_snippet,
            }
        )
    return system_prompt, [{"role": "user", "content": user_content}]


def _extract_text_from_response(resp: Any) -> str:
    """Pull concatenated text blocks out of an Anthropic Messages response."""
    content = getattr(resp, "content", None)
    if content is None and isinstance(resp, dict):
        content = resp.get("content")
    if content is None:
        return ""
    parts: list[str] = []
    for block in content:
        text = getattr(block, "text", None)
        if text is None and isinstance(block, dict):
            text = block.get("text")
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


def call_anthropic_critique(
    persona: dict[str, Any],
    result: PersonaResult,
    screenshot_b64: str,
    dom_snippet: str,
    client: Any,
    *,
    model: str = SONNET_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = DEFAULT_TEMPERATURE,
) -> str:
    """One Anthropic call; return qualitative critique text (possibly empty)."""
    system_prompt, messages = build_anthropic_messages(
        persona, result, screenshot_b64, dom_snippet
    )
    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": messages,
    }
    if system_prompt:
        kwargs["system"] = system_prompt
    resp = client.messages.create(**kwargs)
    return _extract_text_from_response(resp)


def _default_anthropic_client_factory() -> Any:  # pragma: no cover
    import anthropic

    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY missing; needed for LLM persona critique. "
            "Pass --fast to skip Anthropic calls."
        )
    return anthropic.Anthropic(api_key=key)


# --- Orchestration -------------------------------------------------------


def run_all_personas(
    personas_dir: Path,
    check_script: Path,
    *,
    fast: bool,
    check_retries: int = DEFAULT_CHECK_RETRIES,
    subprocess_runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    capture_fn: Callable[[dict[str, Any]], tuple[str, str]] | None = None,
    anthropic_client_factory: Callable[[], Any] | None = None,
    python_exe: str | None = None,
    max_llm_calls: int = MAX_LLM_CALLS,
) -> list[PersonaResult]:
    """Run every persona spec and return per-persona results."""
    paths = load_persona_paths(personas_dir)
    if not check_script.is_file():
        raise FileNotFoundError(f"check script not found: {check_script}")

    client: Any = None
    llm_calls_used = 0

    if not fast:
        factory = anthropic_client_factory or _default_anthropic_client_factory
        client = factory()

    results: list[PersonaResult] = []
    for path in paths:
        persona = json.loads(path.read_text(encoding="utf-8"))
        name = persona.get("persona") or path.stem
        passed, rc, stdout, stderr = run_check_live_site(
            check_script,
            path,
            retries=check_retries,
            python_exe=python_exe,
            subprocess_runner=subprocess_runner,
        )
        critique: str | None = None
        critique_error: str | None = None
        if not fast:
            if llm_calls_used >= max_llm_calls:
                raise RuntimeError(
                    f"persona_critique: refusing to exceed cost cap "
                    f"of {max_llm_calls} Anthropic calls per run"
                )
            try:
                shot, dom = (capture_fn or capture_screenshot_and_dom)(
                    persona
                )
                critique = call_anthropic_critique(
                    persona,
                    PersonaResult(
                        name=name,
                        passed=passed,
                        exit_code=rc,
                        stdout=stdout,
                        stderr=stderr,
                    ),
                    shot,
                    dom,
                    client,
                )
            except Exception as exc:  # noqa: BLE001
                critique_error = f"{type(exc).__name__}: {exc}"
            finally:
                llm_calls_used += 1

        results.append(
            PersonaResult(
                name=name,
                passed=passed,
                exit_code=rc,
                stdout=stdout,
                stderr=stderr,
                critique=critique,
                critique_error=critique_error,
            )
        )
    return results


# --- Markdown rendering --------------------------------------------------


def render_markdown(results: Sequence[PersonaResult], *, fast: bool) -> str:
    """Render the scorecard as markdown."""
    lines: list[str] = ["# Persona Critique Scorecard", ""]
    mode_label = (
        "fast (structural asserts only; Anthropic skipped)"
        if fast
        else "llm (Anthropic critique per persona)"
    )
    lines.append(f"Mode: **{mode_label}**. Personas evaluated: {len(results)}.")
    lines.append("")

    lines.append("## Structural results")
    lines.append("")
    lines.append("| Persona | Result | Exit code |")
    lines.append("|---|---|---|")
    for r in results:
        verdict = "PASS" if r.passed else "FAIL"
        lines.append(f"| {r.name} | {verdict} | {r.exit_code} |")

    failed = [r for r in results if not r.passed]
    if failed:
        lines.append("")
        lines.append("## Failure details")
        for r in failed:
            lines.append("")
            lines.append(f"### {r.name}")
            lines.append("")
            lines.append("```")
            lines.append((r.stderr.strip() or r.stdout.strip() or "(no output)"))
            lines.append("```")

    if not fast:
        lines.append("")
        lines.append("## Qualitative critique")
        for r in results:
            lines.append("")
            lines.append(f"### {r.name}")
            lines.append("")
            if r.critique_error:
                lines.append(f"_critique unavailable: {r.critique_error}_")
            elif r.critique:
                lines.append(r.critique.strip())
            else:
                lines.append("_no critique returned_")

    return "\n".join(lines) + "\n"


# --- CLI -----------------------------------------------------------------


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="persona_critique.py",
        description=(
            "Run every persona spec against the live site and write a "
            "markdown scorecard. --fast skips Anthropic."
        ),
    )
    p.add_argument(
        "--out",
        required=True,
        type=Path,
        help="Path to write the markdown scorecard.",
    )
    p.add_argument(
        "--fast",
        action="store_true",
        help="Structural asserts only; do not call Anthropic.",
    )
    p.add_argument(
        "--personas-dir",
        type=Path,
        default=DEFAULT_PERSONAS_DIR,
        help=f"Directory of persona *.json specs (default {DEFAULT_PERSONAS_DIR}).",
    )
    p.add_argument(
        "--check-script",
        type=Path,
        default=DEFAULT_CHECK_SCRIPT,
        help=f"Path to check_live_site.py (default {DEFAULT_CHECK_SCRIPT}).",
    )
    p.add_argument(
        "--check-retries",
        type=int,
        default=DEFAULT_CHECK_RETRIES,
        help=(
            f"Value of --retry to pass to check_live_site.py "
            f"(default {DEFAULT_CHECK_RETRIES})."
        ),
    )
    return p.parse_args(list(argv))


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        results = run_all_personas(
            args.personas_dir,
            args.check_script,
            fast=args.fast,
            check_retries=args.check_retries,
        )
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    markdown = render_markdown(results, fast=args.fast)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(markdown, encoding="utf-8")

    passed_count = sum(1 for r in results if r.passed)
    print(
        f"wrote {args.out}: {passed_count}/{len(results)} personas passed "
        f"({'fast' if args.fast else 'llm'} mode)"
    )
    return 0 if passed_count == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
