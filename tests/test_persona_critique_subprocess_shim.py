"""Tests for the ``_ClaudeCodeSubprocessClient`` shim.

The shim is what powers the persona harness under Bedrock — it presents the
Anthropic SDK's ``client.messages.create(**kwargs)`` shape but shells out to
``claude -p``. The Anthropic SDK's ``AnthropicBedrock`` cannot be used
because it requires boto3-resolvable IAM credentials, while the Claude CLI
honors ``AWS_BEARER_TOKEN_BEDROCK`` directly. See the class docstring in
``scripts/persona_critique.py``.
"""
from __future__ import annotations

import base64
import importlib
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterator

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def pc_module(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    """Import ``scripts/persona_critique.py`` as a fresh module."""
    monkeypatch.syspath_prepend(str(REPO_ROOT / "scripts"))
    if "persona_critique" in sys.modules:
        del sys.modules["persona_critique"]
    spec = importlib.util.spec_from_file_location(
        "persona_critique",
        REPO_ROOT / "scripts" / "persona_critique.py",
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["persona_critique"] = mod
    spec.loader.exec_module(mod)
    yield mod
    sys.modules.pop("persona_critique", None)


def _make_user_message(
    *, with_image: bool, with_dom: bool
) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = []
    if with_image:
        # 1×1 PNG — minimum valid payload (transparent pixel).
        tiny_png = base64.b64encode(
            bytes.fromhex(
                "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
                "89000000097048597300000b1300000b1301009a9c180000000d49444154789c"
                "63000100000005000155d6f70f0000000049454e44ae426082"
            )
        ).decode("ascii")
        content.append(
            {
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png", "data": tiny_png},
            }
        )
    content.append({"type": "text", "text": "Score this page as persona X."})
    if with_dom:
        content.append({"type": "text", "text": "DOM snippet (truncated):\n<html>...</html>"})
    return content


def _stub_subprocess_run(
    monkeypatch: pytest.MonkeyPatch,
    pc_module: Any,
    envelope: dict[str, Any],
    captured: dict[str, Any],
) -> None:
    """Replace ``subprocess.run`` inside the persona_critique module only."""
    class _Proc:
        def __init__(self) -> None:
            self.returncode = 0
            self.stdout = json.dumps(envelope)
            self.stderr = ""

    def fake_run(cmd: list[str], **kwargs: Any) -> "_Proc":
        captured["cmd"] = list(cmd)
        captured["input"] = kwargs.get("input", "")
        captured["timeout"] = kwargs.get("timeout")
        return _Proc()

    monkeypatch.setattr(pc_module.subprocess, "run", fake_run)


# --- shim: minimum round-trip -----------------------------------------------


@pytest.mark.unit
def test_shim_round_trip_with_image_and_dom(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pc_module: Any
) -> None:
    """The shim: writes the image to disk, builds a prompt referencing it,
    runs ``claude -p``, and parses the JSON payload back into a tool_use block.
    """
    captured: dict[str, Any] = {}
    critique_json = json.dumps(
        {
            "verdict": "PASS",
            "summary": "All good.",
            "findings": [],
        }
    )
    envelope = {
        "type": "result",
        "result": critique_json,
        "usage": {"input_tokens": 42, "output_tokens": 7},
    }
    _stub_subprocess_run(monkeypatch, pc_module, envelope, captured)

    client = pc_module._ClaudeCodeSubprocessClient(
        scratch_dir=tmp_path / "shim"
    )
    tool = pc_module.PERSONA_CRITIQUE_TOOL

    resp = client.messages.create(
        model="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
        max_tokens=512,
        tools=[tool],
        tool_choice={"type": "tool", "name": tool["name"]},
        system="You are the logistics-user persona.",
        messages=[{"role": "user", "content": _make_user_message(with_image=True, with_dom=True)}],
    )

    assert len(resp.content) == 1
    block = resp.content[0]
    assert block.type == "tool_use"
    assert block.name == tool["name"]
    assert block.input["verdict"] == "PASS"
    assert block.input["findings"] == []
    assert resp.usage.input_tokens == 42
    assert resp.usage.output_tokens == 7


@pytest.mark.unit
def test_shim_command_uses_model_and_bedrock_safe_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pc_module: Any
) -> None:
    """The CLI invocation must pass --model and --output-format json; any
    other shape breaks JSON envelope parsing.
    """
    captured: dict[str, Any] = {}
    envelope = {"result": '{"verdict":"PASS","summary":"ok","findings":[]}', "usage": {}}
    _stub_subprocess_run(monkeypatch, pc_module, envelope, captured)

    client = pc_module._ClaudeCodeSubprocessClient(scratch_dir=tmp_path)
    model = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    client.messages.create(
        model=model,
        max_tokens=256,
        tools=[pc_module.PERSONA_CRITIQUE_TOOL],
        messages=[{"role": "user", "content": _make_user_message(with_image=False, with_dom=False)}],
    )
    cmd = captured["cmd"]
    assert cmd[0] == "claude"
    assert "--model" in cmd
    assert cmd[cmd.index("--model") + 1] == model
    assert "--output-format" in cmd
    assert cmd[cmd.index("--output-format") + 1] == "json"
    assert "-p" in cmd


@pytest.mark.unit
def test_shim_prompt_includes_schema_and_screenshot_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pc_module: Any
) -> None:
    """Prompt must carry (a) the JSON schema the CLI must mirror, (b) the
    absolute path to the screenshot so the CLI's Read tool can open it.
    """
    captured: dict[str, Any] = {}
    envelope = {"result": '{"verdict":"PASS","summary":"ok","findings":[]}', "usage": {}}
    _stub_subprocess_run(monkeypatch, pc_module, envelope, captured)

    client = pc_module._ClaudeCodeSubprocessClient(scratch_dir=tmp_path)
    client.messages.create(
        model="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
        max_tokens=512,
        tools=[pc_module.PERSONA_CRITIQUE_TOOL],
        messages=[{"role": "user", "content": _make_user_message(with_image=True, with_dom=False)}],
    )
    prompt = captured["input"]
    # Schema fields from PERSONA_CRITIQUE_TOOL.input_schema.
    assert '"verdict"' in prompt
    assert '"findings"' in prompt
    # Screenshot file reference; the path lives under the scratch_dir tmp.
    assert str(tmp_path) in prompt
    assert ".png" in prompt
    # Response-format discipline — guard against prose.
    assert "single JSON object" in prompt


@pytest.mark.unit
def test_shim_writes_screenshot_png_to_scratch_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pc_module: Any
) -> None:
    """Every run must drop the decoded PNG under the scratch dir so the CLI
    can open it; otherwise the Read tool reference is a dead link.
    """
    captured: dict[str, Any] = {}
    envelope = {"result": '{"verdict":"PASS","summary":"ok","findings":[]}', "usage": {}}
    _stub_subprocess_run(monkeypatch, pc_module, envelope, captured)

    scratch = tmp_path / "shim-scratch"
    client = pc_module._ClaudeCodeSubprocessClient(scratch_dir=scratch)
    client.messages.create(
        model="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
        max_tokens=512,
        tools=[pc_module.PERSONA_CRITIQUE_TOOL],
        messages=[{"role": "user", "content": _make_user_message(with_image=True, with_dom=False)}],
    )
    pngs = list(scratch.glob("screenshot-*.png"))
    assert len(pngs) == 1, "exactly one screenshot file expected"
    # Must be a real PNG (starts with the 8-byte signature).
    assert pngs[0].read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


# --- shim: resilient parsing ------------------------------------------------


@pytest.mark.unit
def test_shim_strips_markdown_code_fences_from_model_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pc_module: Any
) -> None:
    """Model may add ```json …``` fences even when instructed not to; the
    shim must tolerate that rather than crash.
    """
    captured: dict[str, Any] = {}
    fenced = "```json\n" + json.dumps(
        {"verdict": "FAIL", "summary": "s", "findings": []}
    ) + "\n```"
    envelope = {"result": fenced, "usage": {}}
    _stub_subprocess_run(monkeypatch, pc_module, envelope, captured)

    client = pc_module._ClaudeCodeSubprocessClient(scratch_dir=tmp_path)
    resp = client.messages.create(
        model="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
        max_tokens=256,
        tools=[pc_module.PERSONA_CRITIQUE_TOOL],
        messages=[{"role": "user", "content": _make_user_message(with_image=False, with_dom=False)}],
    )
    assert resp.content[0].input["verdict"] == "FAIL"


@pytest.mark.unit
def test_shim_extracts_embedded_json_when_model_adds_prose(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pc_module: Any
) -> None:
    """Last-resort: if the CLI emits explanatory prose around the JSON, the
    shim extracts the first balanced object — otherwise a whole persona loop
    crashes on a formatting quirk.
    """
    captured: dict[str, Any] = {}
    messy = (
        "Here is my assessment:\n"
        + json.dumps({"verdict": "PASS", "summary": "s", "findings": []})
        + "\nLet me know if you need more detail."
    )
    envelope = {"result": messy, "usage": {}}
    _stub_subprocess_run(monkeypatch, pc_module, envelope, captured)

    client = pc_module._ClaudeCodeSubprocessClient(scratch_dir=tmp_path)
    resp = client.messages.create(
        model="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
        max_tokens=256,
        tools=[pc_module.PERSONA_CRITIQUE_TOOL],
        messages=[{"role": "user", "content": _make_user_message(with_image=False, with_dom=False)}],
    )
    assert resp.content[0].input["verdict"] == "PASS"


# --- shim: failure modes ----------------------------------------------------


@pytest.mark.unit
def test_shim_raises_when_cli_exits_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pc_module: Any
) -> None:
    class _Proc:
        returncode = 42
        stdout = ""
        stderr = "boom"

    def fake_run(cmd: list[str], **kwargs: Any) -> "_Proc":
        return _Proc()

    monkeypatch.setattr(pc_module.subprocess, "run", fake_run)

    client = pc_module._ClaudeCodeSubprocessClient(scratch_dir=tmp_path)
    with pytest.raises(RuntimeError, match=r"claude -p exited 42"):
        client.messages.create(
            model="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
            max_tokens=256,
            tools=[pc_module.PERSONA_CRITIQUE_TOOL],
            messages=[{"role": "user", "content": _make_user_message(with_image=False, with_dom=False)}],
        )


@pytest.mark.unit
def test_shim_raises_when_cli_not_on_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pc_module: Any
) -> None:
    def fake_run(cmd: list[str], **kwargs: Any) -> Any:
        raise FileNotFoundError(cmd[0])

    monkeypatch.setattr(pc_module.subprocess, "run", fake_run)

    client = pc_module._ClaudeCodeSubprocessClient(scratch_dir=tmp_path)
    with pytest.raises(RuntimeError, match=r"CLI not on PATH"):
        client.messages.create(
            model="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
            max_tokens=256,
            tools=[pc_module.PERSONA_CRITIQUE_TOOL],
            messages=[{"role": "user", "content": _make_user_message(with_image=False, with_dom=False)}],
        )


@pytest.mark.unit
def test_shim_raises_on_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pc_module: Any
) -> None:
    def fake_run(cmd: list[str], **kwargs: Any) -> Any:
        import subprocess as _sp
        raise _sp.TimeoutExpired(cmd[0], timeout=1)

    monkeypatch.setattr(pc_module.subprocess, "run", fake_run)

    client = pc_module._ClaudeCodeSubprocessClient(
        scratch_dir=tmp_path, timeout_s=1
    )
    with pytest.raises(RuntimeError, match=r"timed out after 1s"):
        client.messages.create(
            model="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
            max_tokens=256,
            tools=[pc_module.PERSONA_CRITIQUE_TOOL],
            messages=[{"role": "user", "content": _make_user_message(with_image=False, with_dom=False)}],
        )


# --- shim: plumbs through call_anthropic_critique ---------------------------


@pytest.mark.unit
def test_call_anthropic_critique_works_with_subprocess_shim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pc_module: Any
) -> None:
    """End-to-end: ``call_anthropic_critique`` — the real function the harness
    calls — must happily consume the shim's synthesized tool_use response.
    """
    captured: dict[str, Any] = {}
    critique = {
        "verdict": "FAIL",
        "summary": "Address hidden behind click.",
        "findings": [
            {
                "code": "VENUE_ADDRESS_MISSING",
                "severity": "critical",
                "evidence": "Subtitle shows only short slug 'AFS'.",
                "suggested_fix": "Render ev.venue_address inline.",
            }
        ],
    }
    envelope = {"result": json.dumps(critique), "usage": {"input_tokens": 100, "output_tokens": 50}}
    _stub_subprocess_run(monkeypatch, pc_module, envelope, captured)

    # Build a PersonaResult with the minimum fields the code reads.
    persona_result = pc_module.PersonaResult(
        name="logistics-user",
        passed=True,
        exit_code=0,
        stdout="",
        stderr="",
    )
    persona = {
        "persona": "logistics-user",
        "url": "http://127.0.0.1:8765/",
        "llm": {
            "system_prompt": "You are a logistics-first user.",
            "goals": "See address without clicking.",
        },
    }

    client = pc_module._ClaudeCodeSubprocessClient(scratch_dir=tmp_path)
    logged: list[dict[str, Any]] = []
    res = pc_module.call_anthropic_critique(
        persona,
        persona_result,
        "iVBORw0KGgo=",
        "<html></html>",
        client,
        model="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
        log_fn=logged.append,
    )
    assert res.verdict == "FAIL"
    assert len(res.findings) == 1
    assert res.findings[0].code == "VENUE_ADDRESS_MISSING"
    # Cost event emitted with non-zero token counts.
    assert logged and logged[0]["input_tokens"] == 100
    assert logged[0]["output_tokens"] == 50
