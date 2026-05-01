#!/usr/bin/env python3
"""Persona critique orchestrator.

Iterates ``personas/live-site/*.json``, runs ``scripts/check_live_site.py``
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
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Sequence

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover — dotenv is a project dep
    def load_dotenv(*_args: Any, **_kwargs: Any) -> None:
        return None

load_dotenv()

MAX_LLM_CALLS = 6
DOM_SNIPPET_MAX_BYTES = 40_000


def _bedrock_mode() -> bool:
    """Whether the harness should route calls through AWS Bedrock.

    Mirrors Claude Code's ``CLAUDE_CODE_USE_BEDROCK`` convention — set to
    ``1`` / ``true`` to prefer ``anthropic.AnthropicBedrock`` over the direct
    API. Defaults to direct API for backwards compatibility.
    """
    return os.environ.get("CLAUDE_CODE_USE_BEDROCK", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


# Direct-API model IDs (original defaults; used when Bedrock is disabled).
_DIRECT_SONNET_DEFAULT = "claude-sonnet-4-6"
_DIRECT_HAIKU_DEFAULT = "claude-haiku-4-5-20251001"
_DIRECT_OPUS_DEFAULT = "claude-opus-4-7"

# Bedrock inference-profile IDs (used when CLAUDE_CODE_USE_BEDROCK=1).
_BEDROCK_SONNET_DEFAULT = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
_BEDROCK_HAIKU_DEFAULT = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
_BEDROCK_OPUS_DEFAULT = "us.anthropic.claude-opus-4-1-20250805-v1:0"


def _resolve_model(env_name: str, bedrock_default: str, direct_default: str) -> str:
    """Return the configured model ID for a tier.

    Precedence: explicit env var → bedrock default (if Bedrock mode) →
    direct-API default.
    """
    override = os.environ.get(env_name)
    if override and override.strip():
        return override.strip()
    return bedrock_default if _bedrock_mode() else direct_default


SONNET_MODEL = _resolve_model(
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    _BEDROCK_SONNET_DEFAULT,
    _DIRECT_SONNET_DEFAULT,
)
HAIKU_MODEL = _resolve_model(
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    _BEDROCK_HAIKU_DEFAULT,
    _DIRECT_HAIKU_DEFAULT,
)
OPUS_MODEL = _resolve_model(
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    _BEDROCK_OPUS_DEFAULT,
    _DIRECT_OPUS_DEFAULT,
)
DEFAULT_MODEL = HAIKU_MODEL
DEFAULT_MAX_TOKENS = 1024
DEFAULT_TEMPERATURE = 0.2
# Models that reject the ``temperature`` parameter (API returns 400 since
# 2026-04). Any model whose ID contains ``opus`` is treated as temperature-free
# so both direct-API and Bedrock Opus IDs are covered without a hardcoded list.
MODELS_WITHOUT_TEMPERATURE: frozenset[str] = frozenset({OPUS_MODEL})


def _model_accepts_temperature(model: str) -> bool:
    if model in MODELS_WITHOUT_TEMPERATURE:
        return False
    return "opus" not in model.lower()

DEFAULT_PERSONAS_DIR = Path("personas/live-site")
DEFAULT_CHECK_SCRIPT = Path("scripts/check_live_site.py")
DEFAULT_CHECK_RETRIES = 0
SUBPROCESS_TIMEOUT_S = 180
CONFIG_MODEL_PATH = Path("config/persona_model.json")
COSTS_LOG_PATH = Path(".overnight/persona-costs.jsonl")

# USD per 1M tokens. Kept co-located with the call site; ``bench_personas.py``
# imports this table so the two tools agree on pricing. Update when Anthropic
# adjusts rates.
PRICING_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    HAIKU_MODEL: (1.0, 5.0),
    SONNET_MODEL: (3.0, 15.0),
    OPUS_MODEL: (15.0, 75.0),
}


def _compute_cost_usd(
    model: str, input_tokens: int, output_tokens: int
) -> float | None:
    """Estimate one-call cost. Returns ``None`` for unpriced models."""
    rate = PRICING_USD_PER_MTOK.get(model)
    if rate is None:
        return None
    in_rate, out_rate = rate
    return round(
        (input_tokens * in_rate + output_tokens * out_rate) / 1_000_000.0, 6
    )


def _log_cost_event(
    event: dict[str, Any], *, path: Path = COSTS_LOG_PATH
) -> None:
    """Append ``event`` as a JSONL line to ``path``. Best-effort; never raises.

    Logging is observability, not correctness — a full disk or a CI sandbox
    without the ``.overnight/`` directory must not break the critique flow.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, separators=(",", ":")) + "\n")
    except Exception:
        pass


def _load_configured_model(config_path: Path = CONFIG_MODEL_PATH) -> str:
    """Read the persistently-selected model from ``config_path``.

    Falls back to :data:`DEFAULT_MODEL` when the file is missing or malformed.
    The file is written by ``scripts/bench_personas.py`` after comparing
    Haiku/Sonnet/Opus against the live site.
    """
    try:
        with config_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        model = data.get("model")
        if isinstance(model, str) and model.strip():
            return model.strip()
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return DEFAULT_MODEL


SEVERITY_LEVELS: tuple[str, ...] = ("critical", "high", "medium", "low")
PERSONA_CRITIQUE_TOOL: dict[str, Any] = {
    "name": "record_persona_critique",
    "description": (
        "Record the persona's verdict on the live site as structured data. "
        "Verdict must be PASS if the persona's primary user story can be "
        "accomplished without friction, else FAIL. List every blocker as a "
        "finding — the calling system uses these to diff across deployments."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "verdict": {
                "type": "string",
                "enum": ["PASS", "FAIL"],
                "description": "PASS if the persona's user story is served, else FAIL.",
            },
            "summary": {
                "type": "string",
                "description": "2-4 sentence qualitative critique through the persona's lens.",
            },
            "findings": {
                "type": "array",
                "description": (
                    "Structured issues. Empty list when verdict=PASS and the "
                    "persona has no concerns. One entry per distinct blocker."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": (
                                "Stable machine-readable code in SCREAMING_SNAKE_CASE, "
                                "e.g. EXPAND_AFFORDANCE_UNLABELED, VENUE_ADDRESS_MISSING."
                            ),
                        },
                        "severity": {
                            "type": "string",
                            "enum": list(SEVERITY_LEVELS),
                        },
                        "evidence": {
                            "type": "string",
                            "description": "Exact text or selector that demonstrates the issue.",
                        },
                        "suggested_fix": {
                            "type": "string",
                            "description": "Concrete one-line fix proposal.",
                        },
                    },
                    "required": ["code", "severity", "evidence", "suggested_fix"],
                },
            },
        },
        "required": ["verdict", "summary", "findings"],
    },
}


@dataclass(frozen=True)
class PersonaFinding:
    """One structured issue flagged by a persona."""

    code: str
    severity: str
    evidence: str
    suggested_fix: str


@dataclass(frozen=True)
class PersonaCritique:
    """Structured LLM verdict + findings for one persona."""

    verdict: str
    summary: str
    findings: tuple[PersonaFinding, ...] = ()


@dataclass(frozen=True)
class PersonaResult:
    """Outcome of a single persona's structural + optional LLM pass."""

    name: str
    passed: bool
    exit_code: int
    stdout: str
    stderr: str
    critique: PersonaCritique | None = None
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
    """Import sibling ``check_live_site.py`` without requiring a package.

    Registers the module in ``sys.modules`` before ``exec_module`` because
    Python 3.13's ``@dataclass`` resolves ``cls.__module__`` through
    ``sys.modules`` during decoration — without the registration, the
    decorator raises ``AttributeError: 'NoneType' object has no attribute
    '__dict__'`` at import time.
    """
    module_name = "_check_live_site"
    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached
    here = Path(__file__).resolve().parent / "check_live_site.py"
    spec = importlib.util.spec_from_file_location(module_name, here)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return mod


async def _async_capture(
    spec: dict[str, Any],
    launch: Callable[..., Awaitable[Any]] | None = None,
) -> tuple[str, str]:
    """Navigate to the persona URL, return (screenshot_b64, dom_snippet).

    Legacy fresh-page path: independent browser session used only when the
    caller explicitly wants a capture detached from any assertion run (e.g.
    ``bench_personas.py`` still does the assertion pass via subprocess).
    For shared-page captures that stay consistent with the asserted state,
    see :func:`run_shared_page_capture`.
    """
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
        shot_bytes = await page.screenshot({"type": "png", "fullPage": True})
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


def run_shared_page_capture(
    spec: dict[str, Any],
    launch: Callable[..., Awaitable[Any]] | None = None,
    *,
    full_page: bool = True,
    dom_max_bytes: int = DOM_SNIPPET_MAX_BYTES,
) -> tuple[bool, int, str, str, str, str]:
    """Run asserts + capture screenshot/DOM from the same pyppeteer page.

    Returns ``(passed, exit_code, stdout, stderr, screenshot_b64, dom_snippet)``.
    The tuple prefix mirrors :func:`run_check_live_site` so
    :func:`run_all_personas` can drop it in without special-casing.

    This is the shared-page entry point: one ``browser.newPage`` + one
    ``page.goto`` per persona, asserts evaluated against the same DOM that
    feeds the screenshot. No second navigation before screenshot capture.

    ``full_page`` defaults to ``True`` here so the LLM sees below-the-fold
    content — personas otherwise flag already-implemented features as
    missing just because they're scrolled out of the default viewport.
    """
    passed, exit_code, stdout, stderr, shot_b64, snippet, _ = (
        run_shared_page_capture_with_ground_truth(
            spec,
            launch=launch,
            full_page=full_page,
            dom_max_bytes=dom_max_bytes,
        )
    )
    return passed, exit_code, stdout, stderr, shot_b64, snippet


def run_shared_page_capture_with_ground_truth(
    spec: dict[str, Any],
    launch: Callable[..., Awaitable[Any]] | None = None,
    *,
    full_page: bool = True,
    dom_max_bytes: int = DOM_SNIPPET_MAX_BYTES,
) -> tuple[bool, int, str, str, str, str, dict[str, dict[str, Any]]]:
    """Same as :func:`run_shared_page_capture` plus per-selector ground truth.

    The seventh tuple element maps CSS selectors derived from the persona
    spec (asserts, click_before_assert, pre_screenshot_actions — see
    :func:`check_live_site.derive_ground_truth_selectors`) to
    ``{"exists": bool, "count": int}`` observations against the live page.
    The orchestrator injects this dict into the LLM prompt so the persona
    cannot hallucinate that a selector is missing when the DOM proves
    otherwise.
    """
    cls = _load_check_live_site_module()
    failures, shot_b64, dom_html, ground_truth = asyncio.run(
        cls.run_spec_capture_and_ground_truth(
            spec,
            launch=launch,
            full_page=full_page,
            collect_ground_truth=True,
        )
    )
    passed = len(failures) == 0
    exit_code = 0 if passed else 1
    stdout = "OK\n" if passed else ""
    stderr = "" if passed else "\n".join(f.format() for f in failures)
    snippet = dom_html[:dom_max_bytes] if dom_max_bytes else dom_html
    return passed, exit_code, stdout, stderr, shot_b64, snippet, ground_truth


def format_ground_truth_for_prompt(
    ground_truth: dict[str, dict[str, Any]]
) -> str:
    """Render ``{selector: {exists, count}}`` as a compact JSON block.

    Empty inputs return an empty string so callers can omit the section
    without producing a stub prompt element.
    """
    if not ground_truth:
        return ""
    return json.dumps(ground_truth, separators=(",", ":"), sort_keys=True)


# --- Anthropic call ------------------------------------------------------


def build_anthropic_messages(
    persona: dict[str, Any],
    result: PersonaResult,
    screenshot_b64: str,
    dom_snippet: str,
    ground_truth: dict[str, dict[str, Any]] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Return (system_prompt, messages) for the Anthropic call.

    ``ground_truth`` (when provided and non-empty) is injected as a
    dedicated text block labelled ``Ground truth``. The prompt instructs
    the model that this dict is observed fact — if the persona would be
    inclined to flag a selector as missing, they must cross-check this
    block first.
    """
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
        "Call the `record_persona_critique` tool exactly once with the "
        "persona's verdict, a 2-4 sentence qualitative summary, and zero or "
        "more structured findings. One finding per distinct blocker; use "
        "stable SCREAMING_SNAKE_CASE codes (EXPAND_AFFORDANCE_UNLABELED, "
        "VENUE_ADDRESS_MISSING, TITLE_OVERFLOW_MOBILE) so the calling system "
        "can diff across deployments. Severity must be one of "
        f"{list(SEVERITY_LEVELS)}. PASS only if the persona's user story is "
        "served end-to-end; any blocking issue means FAIL."
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
    gt_text = format_ground_truth_for_prompt(ground_truth or {})
    if gt_text:
        user_content.append(
            {
                "type": "text",
                "text": (
                    "Ground truth (observed DOM facts — per-selector "
                    "presence/count captured from the same page as the "
                    "screenshot above; do NOT contradict these without "
                    "explicit evidence in the screenshot):\n" + gt_text
                ),
            }
        )
    if dom_snippet:
        user_content.append(
            {
                "type": "text",
                "text": "DOM snippet (truncated):\n" + dom_snippet,
            }
        )
    return system_prompt, [{"role": "user", "content": user_content}]


def _extract_tool_use_block(resp: Any, tool_name: str) -> dict[str, Any] | None:
    """Return the first ``tool_use`` block matching ``tool_name`` (or None)."""
    content = getattr(resp, "content", None)
    if content is None and isinstance(resp, dict):
        content = resp.get("content")
    if content is None:
        return None
    for block in content:
        btype = getattr(block, "type", None)
        bname = getattr(block, "name", None)
        binput = getattr(block, "input", None)
        if btype is None and isinstance(block, dict):
            btype = block.get("type")
            bname = block.get("name")
            binput = block.get("input")
        if btype == "tool_use" and bname == tool_name and isinstance(binput, dict):
            return binput
    return None


def _parse_critique_payload(payload: dict[str, Any]) -> PersonaCritique:
    """Construct a PersonaCritique from a tool-use input dict."""
    verdict = str(payload.get("verdict", "")).strip().upper()
    if verdict not in {"PASS", "FAIL"}:
        raise ValueError(f"invalid verdict {verdict!r}")
    summary = str(payload.get("summary", "")).strip()
    findings_raw = payload.get("findings") or []
    if not isinstance(findings_raw, list):
        raise ValueError("findings must be a list")
    findings: list[PersonaFinding] = []
    for item in findings_raw:
        if not isinstance(item, dict):
            raise ValueError("each finding must be an object")
        sev = str(item.get("severity", "")).strip().lower()
        if sev not in SEVERITY_LEVELS:
            raise ValueError(f"invalid severity {sev!r}")
        findings.append(
            PersonaFinding(
                code=str(item.get("code", "")).strip(),
                severity=sev,
                evidence=str(item.get("evidence", "")).strip(),
                suggested_fix=str(item.get("suggested_fix", "")).strip(),
            )
        )
    return PersonaCritique(verdict=verdict, summary=summary, findings=tuple(findings))


def call_anthropic_critique(
    persona: dict[str, Any],
    result: PersonaResult,
    screenshot_b64: str,
    dom_snippet: str,
    client: Any,
    *,
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = DEFAULT_TEMPERATURE,
    run_id: str | None = None,
    context: str = "persona_critique",
    log_fn: Callable[[dict[str, Any]], None] = _log_cost_event,
    ground_truth: dict[str, dict[str, Any]] | None = None,
) -> PersonaCritique:
    """One Anthropic call using tool-use to force a structured verdict.

    Raises ValueError if the response omits the tool-use block or the payload
    fails schema validation — the caller is expected to convert to
    ``critique_error``.

    On success, emits a JSONL cost-event via ``log_fn``. The default
    :func:`_log_cost_event` appends to :data:`COSTS_LOG_PATH`; tests can pass
    a no-op.

    ``ground_truth`` (per-selector presence/count captured by
    :func:`run_shared_page_capture_with_ground_truth`) is forwarded to
    :func:`build_anthropic_messages` so the prompt can anchor the model to
    observed DOM facts.
    """
    system_prompt, messages = build_anthropic_messages(
        persona, result, screenshot_b64, dom_snippet, ground_truth=ground_truth
    )
    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": messages,
        "tools": [PERSONA_CRITIQUE_TOOL],
        "tool_choice": {"type": "tool", "name": PERSONA_CRITIQUE_TOOL["name"]},
    }
    if _model_accepts_temperature(model):
        kwargs["temperature"] = temperature
    if system_prompt:
        kwargs["system"] = system_prompt
    resp = client.messages.create(**kwargs)

    usage = getattr(resp, "usage", None)
    input_tokens = getattr(usage, "input_tokens", 0) if usage else 0
    output_tokens = getattr(usage, "output_tokens", 0) if usage else 0
    log_fn(
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "run_id": run_id,
            "context": context,
            "persona": persona.get("persona", "unknown"),
            "model": model,
            "input_tokens": int(input_tokens or 0),
            "output_tokens": int(output_tokens or 0),
            "cost_usd": _compute_cost_usd(
                model, int(input_tokens or 0), int(output_tokens or 0)
            ),
        }
    )

    payload = _extract_tool_use_block(resp, PERSONA_CRITIQUE_TOOL["name"])
    if payload is None:
        raise ValueError(
            f"model {model!r} did not invoke tool "
            f"{PERSONA_CRITIQUE_TOOL['name']!r}"
        )
    return _parse_critique_payload(payload)


@dataclass(frozen=True)
class _ShimUsage:
    """Mirror of ``anthropic.types.Usage`` used by the subprocess shim."""

    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class _ShimContentBlock:
    """Mirror of an Anthropic tool_use content block used by the shim."""

    type: str
    name: str
    input: dict[str, Any]


@dataclass(frozen=True)
class _ShimResponse:
    """Mirror of ``anthropic.types.Message`` carrying a single tool_use block.

    The surrounding code reads ``.content`` (iterable of blocks) and ``.usage``
    (``.input_tokens`` / ``.output_tokens``). Nothing else is inspected, so a
    frozen dataclass with those attributes is a sufficient stand-in.
    """

    content: tuple[_ShimContentBlock, ...]
    usage: _ShimUsage


class _ClaudeCodeSubprocessClient:
    """Presents ``client.messages.create(**kwargs)`` via ``claude -p``.

    Background: under ``CLAUDE_CODE_USE_BEDROCK=1`` the Anthropic Python SDK's
    ``AnthropicBedrock`` class requires boto3-resolvable AWS IAM credentials
    (access key + secret). Operators using ``AWS_BEARER_TOKEN_BEDROCK`` (the
    Claude CLI auth shortcut) have no such credentials available, so the SDK
    path fails with ``RuntimeError: could not resolve credentials from
    session``. The ``claude -p`` CLI already honors whatever Bedrock auth the
    user has wired up (bearer token, IAM, profile) — shelling out to it gives
    us a single Bedrock auth surface for both the long-runner council and the
    persona harness.

    Tool-use is faked: the schema + requested payload shape is placed in the
    prompt, the CLI is asked to reply with a single JSON object, and the text
    response is parsed into a synthetic ``tool_use`` content block so the rest
    of :func:`call_anthropic_critique` sees the same return shape as the SDK.
    """

    def __init__(
        self,
        *,
        claude_cmd: str = "claude",
        timeout_s: int = 240,
        scratch_dir: Path | None = None,
    ) -> None:
        self._claude_cmd = claude_cmd
        self._timeout_s = timeout_s
        self._scratch_dir = scratch_dir

        class _Messages:
            def __init__(self, outer: "_ClaudeCodeSubprocessClient") -> None:
                self._outer = outer

            def create(self, **kwargs: Any) -> _ShimResponse:
                return self._outer._create(**kwargs)

        self.messages = _Messages(self)

    def _create(self, **kwargs: Any) -> _ShimResponse:
        model = kwargs.get("model") or DEFAULT_MODEL
        messages = kwargs.get("messages") or []
        system_prompt = (kwargs.get("system") or "").strip()
        tools = kwargs.get("tools") or []

        if len(messages) != 1 or messages[0].get("role") != "user":
            raise ValueError(
                "_ClaudeCodeSubprocessClient expects exactly one user message; "
                f"got {len(messages)} messages"
            )
        user_content = messages[0].get("content") or []
        if not isinstance(user_content, list):
            raise ValueError("user message content must be a list of blocks")

        tool_schema_text = self._render_tool_schema(tools)
        screenshot_path = self._extract_screenshot(user_content)
        user_text, dom_text = self._extract_text_blocks(user_content)

        prompt = self._build_prompt(
            system_prompt=system_prompt,
            tool_schema_text=tool_schema_text,
            screenshot_path=screenshot_path,
            user_text=user_text,
            dom_text=dom_text,
        )

        cmd = [
            self._claude_cmd,
            "--dangerously-skip-permissions",
            "-p",
            "--model",
            model,
            "--output-format",
            "json",
        ]
        try:
            proc = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=self._timeout_s,
                check=False,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"{self._claude_cmd!r} CLI not on PATH; required for "
                "subprocess-based persona critique"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"claude -p subprocess timed out after {self._timeout_s}s"
            ) from exc

        if proc.returncode != 0:
            raise RuntimeError(
                f"claude -p exited {proc.returncode}: "
                f"{(proc.stderr or proc.stdout)[:500]}"
            )

        envelope = self._parse_cli_envelope(proc.stdout)
        text_result = envelope.get("result") or ""
        payload = self._parse_critique_text(text_result)

        usage_raw = envelope.get("usage") or {}
        usage = _ShimUsage(
            input_tokens=int(usage_raw.get("input_tokens") or 0),
            output_tokens=int(usage_raw.get("output_tokens") or 0),
        )
        tool_name = (
            tools[0].get("name") if tools else PERSONA_CRITIQUE_TOOL["name"]
        )
        block = _ShimContentBlock(type="tool_use", name=tool_name, input=payload)
        return _ShimResponse(content=(block,), usage=usage)

    @staticmethod
    def _render_tool_schema(tools: list[dict[str, Any]]) -> str:
        if not tools:
            return ""
        # Every caller passes the PERSONA_CRITIQUE_TOOL schema; render its
        # input_schema as pretty JSON so the CLI can mirror it.
        tool = tools[0]
        schema = tool.get("input_schema") or {}
        return json.dumps(schema, indent=2)

    def _extract_screenshot(
        self, user_content: list[dict[str, Any]]
    ) -> Path | None:
        """Write the first image block to a temp PNG file; return the path.

        Returns ``None`` when the content has no image block. The Claude CLI
        has Read access via ``--dangerously-skip-permissions`` and can open
        the PNG when the prompt references the absolute path.
        """
        for block in user_content:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "image":
                continue
            source = block.get("source") or {}
            if source.get("type") != "base64":
                continue
            b64 = source.get("data") or ""
            if not b64:
                continue
            scratch = self._scratch_dir or Path(".long-run/_shim")
            scratch.mkdir(parents=True, exist_ok=True)
            path = scratch / f"screenshot-{uuid.uuid4().hex}.png"
            path.write_bytes(base64.b64decode(b64))
            return path.resolve()
        return None

    @staticmethod
    def _extract_text_blocks(
        user_content: list[dict[str, Any]],
    ) -> tuple[str, str]:
        """Return ``(user_text, dom_text)`` — the two text blocks we recognize.

        :func:`build_anthropic_messages` always emits ``(image, user_text,
        dom_text?)`` in that order; we preserve the split so the prompt can
        label them to help the CLI model.
        """
        texts: list[str] = []
        for block in user_content:
            if isinstance(block, dict) and block.get("type") == "text":
                texts.append(block.get("text") or "")
        if not texts:
            return "", ""
        if len(texts) == 1:
            return texts[0], ""
        return texts[0], "\n\n".join(texts[1:])

    @staticmethod
    def _build_prompt(
        *,
        system_prompt: str,
        tool_schema_text: str,
        screenshot_path: Path | None,
        user_text: str,
        dom_text: str,
    ) -> str:
        parts: list[str] = []
        if system_prompt:
            parts.append(f"# Persona\n\n{system_prompt}")
        if screenshot_path is not None:
            parts.append(
                "# Screenshot\n\n"
                f"Read the PNG at `{screenshot_path}` "
                "using the Read tool before scoring."
            )
        parts.append(f"# Task\n\n{user_text}")
        if dom_text:
            parts.append(dom_text)
        if tool_schema_text:
            parts.append(
                "# Response format\n\n"
                "Respond with a single JSON object matching this schema. "
                "Emit NOTHING else — no prose, no markdown code fences, no "
                "commentary before or after. The orchestrator parses your "
                "response with `json.loads` and will reject any non-JSON output.\n\n"
                f"```json\n{tool_schema_text}\n```"
            )
        return "\n\n".join(parts)

    @staticmethod
    def _parse_cli_envelope(stdout: str) -> dict[str, Any]:
        stdout = stdout.strip()
        if not stdout:
            raise RuntimeError("claude -p returned empty stdout")
        # ``--output-format json`` always emits one JSON object on stdout.
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            # Some CLI versions stream NDJSON; take the last line.
            last = stdout.splitlines()[-1]
            return json.loads(last)

    @staticmethod
    def _parse_critique_text(text: str) -> dict[str, Any]:
        """Parse a JSON critique payload from the CLI's response text.

        Tolerates leading/trailing whitespace and accidental ```json fences
        — the model is instructed not to add them, but we defend against it.
        """
        stripped = text.strip()
        if stripped.startswith("```"):
            # Strip an optional code-fence wrapper.
            lines = stripped.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            stripped = "\n".join(lines).strip()
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            # Fallback: extract the first balanced JSON object in the text.
            start = stripped.find("{")
            end = stripped.rfind("}")
            if 0 <= start < end:
                return json.loads(stripped[start : end + 1])
            raise


def _default_anthropic_client_factory() -> Any:  # pragma: no cover
    """Build the default LLM transport.

    Under ``CLAUDE_CODE_USE_BEDROCK=1`` the ``claude -p`` CLI already has
    Bedrock auth wired up (IAM role, profile, or ``AWS_BEARER_TOKEN_BEDROCK``)
    and shelling out is the most reliable path — avoids a second Bedrock auth
    surface that would need its own boto3-resolvable credentials. Direct API
    mode still uses ``anthropic.Anthropic`` so existing unit tests and operator
    workflows keep working.
    """
    if _bedrock_mode():
        return _ClaudeCodeSubprocessClient()

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
    shared_page_fn: Callable[[dict[str, Any]], tuple[bool, int, str, str, str, str]]
    | None = None,
    anthropic_client_factory: Callable[[], Any] | None = None,
    python_exe: str | None = None,
    max_llm_calls: int = MAX_LLM_CALLS,
    model: str = DEFAULT_MODEL,
) -> list[PersonaResult]:
    """Run every persona spec and return per-persona results.

    Two check-live-site modes:

    - **fast mode** (``fast=True``): shells out to ``check_live_site.py`` via
      ``subprocess_runner`` and skips Anthropic entirely.
    - **LLM mode** (``fast=False``): single pyppeteer session per persona
      where asserts and screenshot/DOM come from the same page. This is the
      shared-page flow (T2.1); the asserted state and the captured image
      are guaranteed to match. Callers may still override with ``capture_fn``
      (legacy two-navigation path) to preserve backward compatibility — in
      that case assertions run via ``subprocess_runner`` first, then the
      capture_fn navigates a fresh page for the screenshot.
    """
    paths = load_persona_paths(personas_dir)
    if not check_script.is_file():
        raise FileNotFoundError(f"check script not found: {check_script}")

    client: Any = None
    llm_calls_used = 0
    run_id = uuid.uuid4().hex[:12]

    if not fast:
        factory = anthropic_client_factory or _default_anthropic_client_factory
        client = factory()

    use_shared_page = (
        not fast and capture_fn is None
    )
    shared_fn = shared_page_fn or run_shared_page_capture_with_ground_truth

    results: list[PersonaResult] = []
    for path in paths:
        persona = json.loads(path.read_text(encoding="utf-8"))
        name = persona.get("persona") or path.stem

        shot: str | None = None
        dom: str | None = None
        ground_truth: dict[str, dict[str, Any]] = {}
        shared_error: str | None = None

        if use_shared_page:
            if llm_calls_used >= max_llm_calls:
                raise RuntimeError(
                    f"persona_critique: refusing to exceed cost cap "
                    f"of {max_llm_calls} Anthropic calls per run"
                )
            try:
                shared_out = shared_fn(persona)
                if len(shared_out) == 7:
                    passed, rc, stdout, stderr, shot, dom, ground_truth = shared_out
                else:
                    passed, rc, stdout, stderr, shot, dom = shared_out
            except Exception as exc:  # noqa: BLE001
                passed, rc, stdout, stderr = False, 2, "", f"{type(exc).__name__}: {exc}"
                shared_error = f"{type(exc).__name__}: {exc}"
        else:
            passed, rc, stdout, stderr = run_check_live_site(
                check_script,
                path,
                retries=check_retries,
                python_exe=python_exe,
                subprocess_runner=subprocess_runner,
            )

        critique: PersonaCritique | None = None
        critique_error: str | None = None
        if not fast:
            if not use_shared_page:
                if llm_calls_used >= max_llm_calls:
                    raise RuntimeError(
                        f"persona_critique: refusing to exceed cost cap "
                        f"of {max_llm_calls} Anthropic calls per run"
                    )
            try:
                if shared_error is not None:
                    raise RuntimeError(shared_error)
                if shot is None or dom is None:
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
                    model=model,
                    run_id=run_id,
                    context="persona_critique",
                    ground_truth=ground_truth,
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
    passed_count = sum(1 for r in results if r.passed)
    total = len(results)
    overall = "PASS" if passed_count == total and total > 0 else "FAIL"
    lines.append(
        f"**Overall: {overall} {passed_count}/{total} personas.**"
    )
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
        lines.append("## LLM verdicts")
        lines.append("")
        lines.append("| Persona | Verdict | Findings |")
        lines.append("|---|---|---|")
        for r in results:
            if r.critique_error:
                lines.append(f"| {r.name} | ERROR | — |")
            elif r.critique is None:
                lines.append(f"| {r.name} | — | — |")
            else:
                lines.append(
                    f"| {r.name} | {r.critique.verdict} | {len(r.critique.findings)} |"
                )

        lines.append("")
        lines.append("## Qualitative critique")
        for r in results:
            lines.append("")
            lines.append(f"### {r.name}")
            lines.append("")
            if r.critique_error:
                lines.append(f"_critique unavailable: {r.critique_error}_")
                continue
            if r.critique is None:
                lines.append("_no critique returned_")
                continue
            lines.append(f"**Verdict:** {r.critique.verdict}")
            lines.append("")
            if r.critique.summary:
                lines.append(r.critique.summary.strip())
                lines.append("")
            if r.critique.findings:
                lines.append("| Code | Severity | Evidence | Suggested fix |")
                lines.append("|---|---|---|---|")
                for f in r.critique.findings:
                    evidence = f.evidence.replace("|", "\\|").replace("\n", " ")
                    fix = f.suggested_fix.replace("|", "\\|").replace("\n", " ")
                    lines.append(
                        f"| `{f.code}` | {f.severity} | {evidence} | {fix} |"
                    )

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
    p.add_argument(
        "--model",
        type=str,
        default=None,
        help=(
            "Anthropic model ID for LLM critiques. Defaults to value in "
            f"{CONFIG_MODEL_PATH} if present, else {DEFAULT_MODEL}."
        ),
    )
    return p.parse_args(list(argv))


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    model = args.model or _load_configured_model()
    try:
        results = run_all_personas(
            args.personas_dir,
            args.check_script,
            fast=args.fast,
            check_retries=args.check_retries,
            model=model,
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
