"""Provider/model resolution + provider-agnostic content validation.

Covers the OpenRouter-preferred switch:

* ``resolve_provider_model()`` picks OpenRouter (deepseek-v4-flash) when its
  key is set, falls back to Anthropic Claude otherwise, and honours env
  model overrides — never a bare hardcode that can silently go stale (the
  retired ``google/gemini-2.5-flash`` id is what broke CI before).
* :class:`EventValidationService` content validation runs through the
  provider-agnostic ``LLMService._chat`` (not the Anthropic SDK directly), so
  it works under OpenRouter where ``llm_service.anthropic`` is ``None``.
"""

from unittest.mock import Mock

import pytest

from src.llm_service import (
    DEFAULT_ANTHROPIC_MODEL,
    DEFAULT_OPENROUTER_MODEL,
    LLMService,
    resolve_provider_model,
)
from src.validation_service import EventValidationService


def test_resolve_prefers_openrouter(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-key")
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    provider, model = resolve_provider_model()
    assert provider == "openrouter"
    # Default comes from config/master_config.yaml's llm.openrouter_model.
    assert model == DEFAULT_OPENROUTER_MODEL == "deepseek/deepseek-v4-flash"


def test_resolve_falls_back_to_anthropic(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-key")
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    provider, model = resolve_provider_model()
    assert provider == "anthropic"
    assert model == DEFAULT_ANTHROPIC_MODEL


def test_resolve_env_model_override_wins(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "deepseek/deepseek-v4-pro")
    provider, model = resolve_provider_model()
    assert provider == "openrouter"
    assert model == "deepseek/deepseek-v4-pro"


def test_resolve_no_keys_returns_none(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert resolve_provider_model() == (None, None)


def test_llm_service_builds_openrouter_client(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    svc = LLMService()
    assert svc.provider == "openrouter"
    assert svc.model == "deepseek/deepseek-v4-flash"
    assert svc.openai is not None
    assert svc.anthropic is None


def test_content_validation_uses_chat_not_anthropic_sdk():
    """Validation must route through _chat so it works under OpenRouter."""
    fake_llm = Mock()
    fake_llm.provider = "openrouter"
    fake_llm.anthropic = None  # the old SDK path would AttributeError on None
    fake_llm._chat = Mock(
        return_value=(
            '{"is_valid": true, "confidence": 0.9, '
            '"issues": [], "reasoning": "looks legit"}'
        )
    )

    svc = EventValidationService(llm_service=fake_llm)
    event = {
        "title": "Test Concert",
        "date": "2026-07-01",
        "time": "19:30",
        "venue": "Symphony",
        "type": "concert",
        "description": "A real evening of orchestral music. " * 5,
    }
    result = svc.validate_event_content_with_llm(event)

    fake_llm._chat.assert_called_once()
    assert result.passed is True
    assert "validation passed" in result.message.lower()
