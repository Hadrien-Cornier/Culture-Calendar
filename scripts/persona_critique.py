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
DOM_SNIPPET_MAX_BYTES = 10_000


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

DEFAULT_PERSONAS_DIR = Path(".overnight/personas")
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
) -> PersonaCritique:
    """One Anthropic call using tool-use to force a structured verdict.

    Raises ValueError if the response omits the tool-use block or the payload
    fails schema validation — the caller is expected to convert to
    ``critique_error``.

    On success, emits a JSONL cost-event via ``log_fn``. The default
    :func:`_log_cost_event` appends to :data:`COSTS_LOG_PATH`; tests can pass
    a no-op.
    """
    system_prompt, messages = build_anthropic_messages(
        persona, result, screenshot_b64, dom_snippet
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


def _default_anthropic_client_factory() -> Any:  # pragma: no cover
    import anthropic

    if _bedrock_mode():
        # AnthropicBedrock relies on the AWS SDK's default credential chain
        # (env vars, ~/.aws/credentials, IAM role). We don't surface a
        # pre-flight check here so operators can use any AWS auth flavor.
        bedrock_cls = getattr(anthropic, "AnthropicBedrock", None)
        if bedrock_cls is None:
            raise RuntimeError(
                "anthropic.AnthropicBedrock not available; upgrade the "
                "anthropic SDK or unset CLAUDE_CODE_USE_BEDROCK."
            )
        return bedrock_cls()

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
    model: str = DEFAULT_MODEL,
) -> list[PersonaResult]:
    """Run every persona spec and return per-persona results."""
    paths = load_persona_paths(personas_dir)
    if not check_script.is_file():
        raise FileNotFoundError(f"check script not found: {check_script}")

    client: Any = None
    llm_calls_used = 0
    run_id = uuid.uuid4().hex[:12]

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
        critique: PersonaCritique | None = None
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
                    model=model,
                    run_id=run_id,
                    context="persona_critique",
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
