"""Repair diagnosis must use the supported Messages API and pinned dependencies."""

import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import anthropic
import yaml

try:
    import httpx2 as httpx  # Anthropic v1 transport
except ImportError:
    import httpx  # Repository-pinned Anthropic 0.68 transport

from scripts.self_heal import CLAUDE_MODEL, diagnose_and_fix


def test_diagnosis_accepts_client_without_sampling_parameters():
    captured = {}

    def create(*, model, max_tokens, messages):
        captured.update(model=model, max_tokens=max_tokens, messages=messages)
        return SimpleNamespace(
            content=[
                SimpleNamespace(
                    text=json.dumps(
                        {
                            "diagnosis": "Empty completion budget",
                            "fix": None,
                            "confidence": "high",
                        }
                    )
                )
            ]
        )

    result = diagnose_and_fix(
        SimpleNamespace(messages=SimpleNamespace(create=create)),
        "AFS one-liners failed",
        None,
        None,
        None,
    )
    assert result["confidence"] == "high"
    assert "AFS one-liners failed" in captured["messages"][0]["content"]
    assert captured["model"] == CLAUDE_MODEL
    assert CLAUDE_MODEL != "claude-sonnet-4-20250514"


def test_diagnosis_reads_text_after_non_text_blocks():
    client = SimpleNamespace(
        messages=SimpleNamespace(
            create=lambda **_: SimpleNamespace(
                content=[
                    SimpleNamespace(type="thinking"),
                    SimpleNamespace(
                        text='{"diagnosis":"ok","fix":null,"confidence":"high"}'
                    ),
                ]
            )
        )
    )
    assert diagnose_and_fix(client, "logs", None, None, None)["diagnosis"] == "ok"


def test_diagnosis_empty_content_returns_no_fix():
    client = SimpleNamespace(
        messages=SimpleNamespace(create=lambda **_: SimpleNamespace(content=[]))
    )
    result = diagnose_and_fix(client, "logs", None, None, None)
    assert result["fix"] is None
    assert result["confidence"] == "low"


def test_diagnosis_uses_actual_pinned_sdk_interface_without_network():
    def respond(request):
        body = json.loads(request.content)
        assert "temperature" not in body
        return httpx.Response(
            200,
            json={
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "model": body["model"],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 10, "output_tokens": 20},
                "content": [
                    {
                        "type": "text",
                        "text": '{"diagnosis":"ok","fix":null,"confidence":"high"}',
                    }
                ],
            },
        )

    client = anthropic.Anthropic(
        api_key="unused",
        http_client=httpx.Client(transport=httpx.MockTransport(respond)),
    )
    inspect.signature(client.messages.create).bind(
        model="test", max_tokens=4000, messages=[{"role": "user", "content": "logs"}]
    )
    assert diagnose_and_fix(client, "logs", None, None, None)["diagnosis"] == "ok"


def test_self_heal_installs_repository_pins():
    root = Path(__file__).resolve().parents[1]
    workflow = yaml.safe_load((root / ".github/workflows/self-heal.yml").read_text())
    install = next(
        s
        for s in workflow["jobs"]["self-heal"]["steps"]
        if s.get("name") == "Install dependencies"
    )
    assert "pip install -r requirements.txt" in install["run"]
    assert "pip install anthropic" not in install["run"]
