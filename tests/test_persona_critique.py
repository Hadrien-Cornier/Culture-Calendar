"""Tests for scripts/persona_critique.py.

The external side-effects (subprocess, pyppeteer, Anthropic SDK) are all
injected or mocked so the tests never hit the network or launch a browser.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import types
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "persona_critique.py"
CHECK_SCRIPT_PATH = REPO_ROOT / "scripts" / "check_live_site.py"


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("persona_critique", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["persona_critique"] = mod
    spec.loader.exec_module(mod)
    return mod


pc = _load_module()


def _make_persona_file(
    dir_: Path,
    name: str,
    *,
    url: str = "https://example.invalid/",
    asserts: list[dict[str, Any]] | None = None,
    llm_system: str = "you are a test persona",
    llm_goals: str = "verify things work",
) -> Path:
    payload = {
        "persona": name,
        "url": url,
        "wait_ms": 0,
        "asserts": asserts or [],
        "llm": {"system_prompt": llm_system, "goals": llm_goals},
    }
    path = dir_ / f"{name}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _fake_completed(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["python", "check_live_site.py"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


class _TrackingRunner:
    """Captures every subprocess.run invocation and returns queued outcomes."""

    def __init__(self, outcomes: list[subprocess.CompletedProcess]):
        self.outcomes = list(outcomes)
        self.calls: list[list[str]] = []

    def __call__(self, cmd, **_kwargs):
        self.calls.append(list(cmd))
        if not self.outcomes:
            return _fake_completed(0, "OK\n", "")
        return self.outcomes.pop(0)


# --- load_persona_paths ---------------------------------------------------


def test_load_persona_paths_sorted(tmp_path):
    _make_persona_file(tmp_path, "zeta")
    _make_persona_file(tmp_path, "alpha")
    _make_persona_file(tmp_path, "mu")
    paths = pc.load_persona_paths(tmp_path)
    names = [p.stem for p in paths]
    assert names == sorted(names)
    assert names[0] == "alpha"
    assert names[-1] == "zeta"


def test_load_persona_paths_missing_dir(tmp_path):
    with pytest.raises(FileNotFoundError):
        pc.load_persona_paths(tmp_path / "does-not-exist")


def test_load_persona_paths_empty_dir(tmp_path):
    with pytest.raises(FileNotFoundError):
        pc.load_persona_paths(tmp_path)


# --- run_check_live_site --------------------------------------------------


def test_run_check_live_site_pass(tmp_path):
    spec_path = _make_persona_file(tmp_path, "a")
    runner = _TrackingRunner([_fake_completed(0, "OK\n", "")])
    ok, rc, out, err = pc.run_check_live_site(
        CHECK_SCRIPT_PATH, spec_path, subprocess_runner=runner
    )
    assert ok is True
    assert rc == 0
    assert "OK" in out
    assert runner.calls and "--spec" in runner.calls[0]
    assert str(spec_path) in runner.calls[0]
    assert "--retry" in runner.calls[0]


def test_run_check_live_site_fail_captures_stderr(tmp_path):
    spec_path = _make_persona_file(tmp_path, "a")
    runner = _TrackingRunner(
        [_fake_completed(1, "", "assert[0] (selector_exists): missing .x")]
    )
    ok, rc, out, err = pc.run_check_live_site(
        CHECK_SCRIPT_PATH, spec_path, subprocess_runner=runner
    )
    assert ok is False
    assert rc == 1
    assert "missing .x" in err


def test_run_check_live_site_passes_retry_override(tmp_path):
    spec_path = _make_persona_file(tmp_path, "a")
    runner = _TrackingRunner([_fake_completed(0)])
    pc.run_check_live_site(
        CHECK_SCRIPT_PATH,
        spec_path,
        retries=3,
        subprocess_runner=runner,
    )
    # --retry appears followed by its value
    call = runner.calls[0]
    idx = call.index("--retry")
    assert call[idx + 1] == "3"


# --- build_anthropic_messages --------------------------------------------


def test_build_anthropic_messages_includes_screenshot_and_dom():
    persona = {
        "persona": "p1",
        "url": "https://x.invalid/",
        "llm": {"system_prompt": "SYS", "goals": "verify X"},
    }
    result = pc.PersonaResult(
        name="p1",
        passed=True,
        exit_code=0,
        stdout="",
        stderr="",
    )
    system, messages = pc.build_anthropic_messages(persona, result, "BASE64==", "<html>foo</html>")
    assert system == "SYS"
    assert len(messages) == 1
    content = messages[0]["content"]
    image_blocks = [b for b in content if b.get("type") == "image"]
    text_blocks = [b for b in content if b.get("type") == "text"]
    assert len(image_blocks) == 1
    assert image_blocks[0]["source"]["data"] == "BASE64=="
    assert image_blocks[0]["source"]["media_type"] == "image/png"
    assert any("<html>foo</html>" in b["text"] for b in text_blocks)
    assert any("verify X" in b["text"] for b in text_blocks)
    assert any("PASS" in b["text"] for b in text_blocks)


def test_build_anthropic_messages_omits_system_when_absent():
    persona = {"persona": "p1", "url": "https://x.invalid/", "llm": {}}
    result = pc.PersonaResult(name="p1", passed=False, exit_code=1, stdout="", stderr="err")
    system, messages = pc.build_anthropic_messages(persona, result, "B", "")
    assert system == ""
    # Text block still exists even without DOM snippet
    text_blocks = [b for b in messages[0]["content"] if b.get("type") == "text"]
    assert len(text_blocks) == 1
    assert "FAIL" in text_blocks[0]["text"]
    assert "err" in text_blocks[0]["text"]


# --- call_anthropic_critique ---------------------------------------------


def _build_fake_client(
    verdict: str = "PASS",
    summary: str = "quite nice indeed",
    findings: list[dict] | None = None,
) -> MagicMock:
    """Return a MagicMock Anthropic client that emits a tool_use block."""
    if findings is None:
        findings = []
    tool_block = types.SimpleNamespace(
        type="tool_use",
        name=pc.PERSONA_CRITIQUE_TOOL["name"],
        input={"verdict": verdict, "summary": summary, "findings": findings},
    )
    resp = types.SimpleNamespace(content=[tool_block])
    client = MagicMock()
    client.messages.create.return_value = resp
    return client


def test_call_anthropic_critique_defaults_to_configured_model():
    persona = {"persona": "p", "url": "u", "llm": {"system_prompt": "SYS", "goals": "g"}}
    result = pc.PersonaResult(name="p", passed=True, exit_code=0, stdout="", stderr="")
    client = _build_fake_client(verdict="PASS", summary="quite nice indeed")
    critique = pc.call_anthropic_critique(persona, result, "B", "<html></html>", client)
    assert isinstance(critique, pc.PersonaCritique)
    assert critique.verdict == "PASS"
    assert critique.summary == "quite nice indeed"
    assert critique.findings == ()
    kwargs = client.messages.create.call_args.kwargs
    # Default is Haiku 4.5 (selected by bench_personas.py on 2026-04-19; see
    # docs/persona_model_benchmark.md for the rationale).
    assert kwargs["model"] == pc.DEFAULT_MODEL == pc.HAIKU_MODEL
    assert kwargs["system"] == "SYS"
    assert kwargs["messages"][0]["role"] == "user"
    # Tool-use must be forced
    assert kwargs["tools"] == [pc.PERSONA_CRITIQUE_TOOL]
    assert kwargs["tool_choice"] == {
        "type": "tool",
        "name": pc.PERSONA_CRITIQUE_TOOL["name"],
    }


def test_call_anthropic_critique_accepts_explicit_model():
    persona = {"persona": "p", "url": "u", "llm": {}}
    result = pc.PersonaResult(name="p", passed=True, exit_code=0, stdout="", stderr="")
    client = _build_fake_client()
    pc.call_anthropic_critique(
        persona, result, "B", "", client, model="claude-opus-4-7"
    )
    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["model"] == "claude-opus-4-7"
    # Opus 4.7 rejects the temperature parameter; must be omitted.
    assert "temperature" not in kwargs


def test_call_anthropic_critique_parses_findings():
    persona = {"persona": "p", "url": "u", "llm": {}}
    result = pc.PersonaResult(name="p", passed=True, exit_code=0, stdout="", stderr="")
    client = _build_fake_client(
        verdict="FAIL",
        summary="missing address",
        findings=[
            {
                "code": "VENUE_ADDRESS_MISSING",
                "severity": "medium",
                "evidence": "AFS card shows no street",
                "suggested_fix": "Add neighborhood below subtitle",
            }
        ],
    )
    critique = pc.call_anthropic_critique(persona, result, "B", "", client)
    assert critique.verdict == "FAIL"
    assert len(critique.findings) == 1
    assert critique.findings[0].code == "VENUE_ADDRESS_MISSING"
    assert critique.findings[0].severity == "medium"


def test_call_anthropic_critique_rejects_missing_tool_use():
    """If the model ignores tool-choice, we must raise so the caller records
    it as a critique_error rather than silently returning empty output."""
    persona = {"persona": "p", "url": "u", "llm": {}}
    result = pc.PersonaResult(name="p", passed=True, exit_code=0, stdout="", stderr="")
    resp = types.SimpleNamespace(
        content=[types.SimpleNamespace(type="text", text="prose not tool")]
    )
    client = MagicMock()
    client.messages.create.return_value = resp
    with pytest.raises(ValueError, match="did not invoke tool"):
        pc.call_anthropic_critique(persona, result, "B", "", client)


def test_call_anthropic_critique_rejects_invalid_verdict():
    persona = {"persona": "p", "url": "u", "llm": {}}
    result = pc.PersonaResult(name="p", passed=True, exit_code=0, stdout="", stderr="")
    client = _build_fake_client(verdict="MAYBE")
    with pytest.raises(ValueError, match="invalid verdict"):
        pc.call_anthropic_critique(persona, result, "B", "", client)


def test_call_anthropic_critique_rejects_invalid_severity():
    persona = {"persona": "p", "url": "u", "llm": {}}
    result = pc.PersonaResult(name="p", passed=True, exit_code=0, stdout="", stderr="")
    client = _build_fake_client(
        verdict="FAIL",
        findings=[
            {
                "code": "X",
                "severity": "catastrophic",
                "evidence": "e",
                "suggested_fix": "f",
            }
        ],
    )
    with pytest.raises(ValueError, match="invalid severity"):
        pc.call_anthropic_critique(persona, result, "B", "", client)


def test_load_configured_model_falls_back_when_file_missing(tmp_path):
    assert pc._load_configured_model(tmp_path / "nope.json") == pc.DEFAULT_MODEL


def test_load_configured_model_reads_model_field(tmp_path):
    cfg = tmp_path / "persona_model.json"
    cfg.write_text(json.dumps({"model": "claude-opus-4-7", "other": "ignored"}))
    assert pc._load_configured_model(cfg) == "claude-opus-4-7"


def test_load_configured_model_ignores_malformed(tmp_path):
    cfg = tmp_path / "persona_model.json"
    cfg.write_text("not json")
    assert pc._load_configured_model(cfg) == pc.DEFAULT_MODEL


def test_call_anthropic_critique_raises_on_empty_content():
    persona = {"persona": "p", "url": "u", "llm": {}}
    result = pc.PersonaResult(name="p", passed=True, exit_code=0, stdout="", stderr="")
    client = MagicMock()
    client.messages.create.return_value = types.SimpleNamespace(content=[])
    with pytest.raises(ValueError, match="did not invoke tool"):
        pc.call_anthropic_critique(persona, result, "B", "", client)


# --- run_all_personas: fast mode skips Anthropic -------------------------


def test_fast_mode_skips_anthropic_entirely(tmp_path, monkeypatch):
    _make_persona_file(tmp_path, "p1")
    _make_persona_file(tmp_path, "p2")
    _make_persona_file(tmp_path, "p3")
    runner = _TrackingRunner([_fake_completed(0, "OK", "")] * 3)

    factory = MagicMock(side_effect=AssertionError("factory must not be invoked in --fast"))
    capture = MagicMock(side_effect=AssertionError("capture must not be invoked in --fast"))

    results = pc.run_all_personas(
        tmp_path,
        CHECK_SCRIPT_PATH,
        fast=True,
        subprocess_runner=runner,
        capture_fn=capture,
        anthropic_client_factory=factory,
    )
    assert len(results) == 3
    assert all(r.passed for r in results)
    assert all(r.critique is None for r in results)
    assert all(r.critique_error is None for r in results)
    factory.assert_not_called()
    capture.assert_not_called()


def test_fast_mode_reports_individual_failures(tmp_path):
    _make_persona_file(tmp_path, "ok")
    _make_persona_file(tmp_path, "sad")
    # Alphabetical order: "ok" first then "sad"
    runner = _TrackingRunner(
        [_fake_completed(0, "OK", ""), _fake_completed(1, "", "assert failed")]
    )
    results = pc.run_all_personas(
        tmp_path,
        CHECK_SCRIPT_PATH,
        fast=True,
        subprocess_runner=runner,
    )
    by_name = {r.name: r for r in results}
    assert by_name["ok"].passed is True
    assert by_name["sad"].passed is False
    assert "assert failed" in by_name["sad"].stderr


# --- run_all_personas: LLM mode calls Anthropic once per persona ---------


def test_llm_mode_calls_anthropic_once_per_persona(tmp_path):
    _make_persona_file(tmp_path, "p1")
    _make_persona_file(tmp_path, "p2")
    runner = _TrackingRunner([_fake_completed(0, "OK", "")] * 2)
    client = _build_fake_client(verdict="PASS", summary="looks fine")
    factory = MagicMock(return_value=client)
    capture = MagicMock(return_value=("B64", "<html></html>"))

    results = pc.run_all_personas(
        tmp_path,
        CHECK_SCRIPT_PATH,
        fast=False,
        subprocess_runner=runner,
        capture_fn=capture,
        anthropic_client_factory=factory,
    )
    assert len(results) == 2
    assert client.messages.create.call_count == 2
    assert capture.call_count == 2
    assert factory.call_count == 1  # client built once, reused
    for r in results:
        assert isinstance(r.critique, pc.PersonaCritique)
        assert r.critique.verdict == "PASS"
        assert r.critique.summary == "looks fine"
        assert r.critique_error is None


def test_llm_mode_capture_failure_is_recorded_not_fatal(tmp_path):
    _make_persona_file(tmp_path, "p1")
    _make_persona_file(tmp_path, "p2")
    runner = _TrackingRunner([_fake_completed(0, "OK", "")] * 2)
    client = _build_fake_client(verdict="PASS", summary="fine")
    factory = MagicMock(return_value=client)

    def flaky_capture(persona):
        if persona["persona"] == "p1":
            raise RuntimeError("browser crashed")
        return ("B64", "")

    results = pc.run_all_personas(
        tmp_path,
        CHECK_SCRIPT_PATH,
        fast=False,
        subprocess_runner=runner,
        capture_fn=flaky_capture,
        anthropic_client_factory=factory,
    )
    by_name = {r.name: r for r in results}
    assert by_name["p1"].critique is None
    assert "browser crashed" in (by_name["p1"].critique_error or "")
    assert isinstance(by_name["p2"].critique, pc.PersonaCritique)
    assert by_name["p2"].critique.summary == "fine"


# --- Cost-cap enforcement ------------------------------------------------


def test_cost_cap_raises_when_exceeded(tmp_path):
    for name in ("a", "b", "c"):
        _make_persona_file(tmp_path, name)
    runner = _TrackingRunner([_fake_completed(0)] * 3)
    client = _build_fake_client("fine")
    factory = MagicMock(return_value=client)
    capture = MagicMock(return_value=("B", "<x/>"))

    with pytest.raises(RuntimeError) as exc_info:
        pc.run_all_personas(
            tmp_path,
            CHECK_SCRIPT_PATH,
            fast=False,
            subprocess_runner=runner,
            capture_fn=capture,
            anthropic_client_factory=factory,
            max_llm_calls=2,
        )
    assert "cost cap" in str(exc_info.value).lower()


def test_cost_cap_default_is_six():
    assert pc.MAX_LLM_CALLS == 6


def test_fast_mode_ignores_cost_cap(tmp_path):
    for name in ("a", "b", "c", "d", "e", "f", "g"):
        _make_persona_file(tmp_path, name)
    runner = _TrackingRunner([_fake_completed(0)] * 7)
    results = pc.run_all_personas(
        tmp_path,
        CHECK_SCRIPT_PATH,
        fast=True,
        subprocess_runner=runner,
        max_llm_calls=2,
    )
    assert len(results) == 7


# --- Markdown rendering --------------------------------------------------


def test_render_markdown_has_expected_sections_fast():
    results = [
        pc.PersonaResult(name="a", passed=True, exit_code=0, stdout="OK", stderr=""),
        pc.PersonaResult(name="b", passed=False, exit_code=1, stdout="", stderr="boom"),
    ]
    md = pc.render_markdown(results, fast=True)
    assert md.startswith("# Persona Critique Scorecard")
    assert "fast" in md
    assert "| Persona | Result | Exit code |" in md
    assert "| a | PASS | 0 |" in md
    assert "| b | FAIL | 1 |" in md
    assert "Failure details" in md
    assert "boom" in md
    # Fast mode omits qualitative section
    assert "Qualitative critique" not in md


def test_render_markdown_llm_mode_includes_critique():
    results = [
        pc.PersonaResult(
            name="a",
            passed=True,
            exit_code=0,
            stdout="",
            stderr="",
            critique=pc.PersonaCritique(
                verdict="PASS",
                summary="delightful",
                findings=(),
            ),
        ),
        pc.PersonaResult(
            name="b",
            passed=False,
            exit_code=1,
            stdout="",
            stderr="missing",
            critique_error="TimeoutError: slow",
        ),
        pc.PersonaResult(
            name="c",
            passed=False,
            exit_code=1,
            stdout="",
            stderr="x",
            critique=pc.PersonaCritique(
                verdict="FAIL",
                summary="needs work",
                findings=(
                    pc.PersonaFinding(
                        code="FOO_BAR",
                        severity="high",
                        evidence="header hidden",
                        suggested_fix="unhide",
                    ),
                ),
            ),
        ),
    ]
    md = pc.render_markdown(results, fast=False)
    assert "llm" in md
    assert "## LLM verdicts" in md
    assert "## Qualitative critique" in md
    assert "delightful" in md
    assert "critique unavailable" in md
    assert "slow" in md
    # Structured findings table rendered for persona c
    assert "`FOO_BAR`" in md
    assert "high" in md
    assert "header hidden" in md
    assert "unhide" in md
    # Verdict summary table shows findings count
    assert "| a | PASS | 0 |" in md
    assert "| b | ERROR | — |" in md
    assert "| c | FAIL | 1 |" in md


def test_render_markdown_empty_results_still_valid():
    md = pc.render_markdown([], fast=True)
    assert "# Persona Critique Scorecard" in md
    assert "Personas evaluated: 0" in md
    assert md.endswith("\n")


# --- Module loader regression (Python 3.13 @dataclass bug) ---------------


def test_load_check_live_site_module_registers_in_sys_modules():
    """Regression for 2026-04-18-3 T5.2: Python 3.13 @dataclass decoration
    resolves ``cls.__module__`` via ``sys.modules``. Without registration
    before ``exec_module``, importing ``check_live_site.py`` raises
    ``AttributeError: 'NoneType' object has no attribute '__dict__'``.
    """
    sys.modules.pop("_check_live_site", None)
    mod = pc._load_check_live_site_module()
    assert sys.modules.get("_check_live_site") is mod
    assert hasattr(mod, "AssertionFailure")
    assert mod.AssertionFailure.__module__ == "_check_live_site"
    # Cached path returns the same module object.
    assert pc._load_check_live_site_module() is mod


# --- CLI main() ----------------------------------------------------------


def test_main_writes_scorecard_and_returns_zero_on_all_pass(tmp_path, monkeypatch):
    personas = tmp_path / "personas"
    personas.mkdir()
    _make_persona_file(personas, "only")

    out = tmp_path / "out.md"

    def fake_run_all(*_args, **_kwargs):
        return [pc.PersonaResult(name="only", passed=True, exit_code=0, stdout="", stderr="")]

    monkeypatch.setattr(pc, "run_all_personas", fake_run_all)
    rc = pc.main(
        [
            "--out",
            str(out),
            "--fast",
            "--personas-dir",
            str(personas),
            "--check-script",
            str(CHECK_SCRIPT_PATH),
        ]
    )
    assert rc == 0
    text = out.read_text(encoding="utf-8")
    assert "| only | PASS | 0 |" in text


def test_main_returns_nonzero_on_structural_failure(tmp_path, monkeypatch):
    personas = tmp_path / "personas"
    personas.mkdir()
    _make_persona_file(personas, "only")
    out = tmp_path / "out.md"

    def fake_run_all(*_args, **_kwargs):
        return [pc.PersonaResult(name="only", passed=False, exit_code=1, stdout="", stderr="x")]

    monkeypatch.setattr(pc, "run_all_personas", fake_run_all)
    rc = pc.main(
        [
            "--out",
            str(out),
            "--fast",
            "--personas-dir",
            str(personas),
            "--check-script",
            str(CHECK_SCRIPT_PATH),
        ]
    )
    assert rc == 1
    assert out.exists()


def test_main_returns_two_on_missing_personas_dir(tmp_path, capsys):
    out = tmp_path / "out.md"
    rc = pc.main(
        [
            "--out",
            str(out),
            "--fast",
            "--personas-dir",
            str(tmp_path / "nope"),
            "--check-script",
            str(CHECK_SCRIPT_PATH),
        ]
    )
    assert rc == 2
    captured = capsys.readouterr()
    assert "not found" in captured.err


def test_main_returns_two_on_cost_cap_runtime_error(tmp_path, monkeypatch):
    personas = tmp_path / "personas"
    personas.mkdir()
    _make_persona_file(personas, "only")
    out = tmp_path / "out.md"

    def fake_run_all(*_args, **_kwargs):
        raise RuntimeError("persona_critique: refusing to exceed cost cap")

    monkeypatch.setattr(pc, "run_all_personas", fake_run_all)
    rc = pc.main(
        [
            "--out",
            str(out),
            "--personas-dir",
            str(personas),
            "--check-script",
            str(CHECK_SCRIPT_PATH),
        ]
    )
    assert rc == 2


def test_cli_help_exits_zero():
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "--fast" in result.stdout
    assert "--personas-dir" in result.stdout
    assert "--out" in result.stdout
