"""Regression tests for the July 2026 publishing freeze.

Incident chain: OpenRouter's deepseek-v4-flash returned ``content=None``
completions, crashing ``LLMService._chat`` on ``.strip()``; the validation
prompt read singular ``date``/``time`` keys so every normalized ``dates[]``
event showed ``Date: N/A`` and was judged invalid; and the gate aborted the
whole pipeline when even one scraper failed. Result: 17 days of failed daily
runs and a stale site while every scraper was healthy.

These tests pin the fixes:

* ``_chat`` never crashes on None/empty completions, retries with a bigger
  budget on ``finish_reason == 'length'``, and fails over to the other
  provider when its key is configured.
* Validation prompts include ``dates[]``/``times[]`` array values.
* LLM "invalid" verdicts are advisory (WARNING) and don't sink schema-valid
  events.
* The pipeline gate degrades gracefully: isolated venue failures publish the
  healthy subset; only systemic failure aborts.
"""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.llm_service import LLMService
from src.validation_service import EventValidationService, ValidationLevel


def _completion(content, finish_reason="stop"):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content),
                finish_reason=finish_reason,
            )
        ]
    )


def _openrouter_service(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "an-key")
    svc = LLMService()
    assert svc.provider == "openrouter"
    return svc


# ---------------------------------------------------------------------------
# _chat: None-content crash + retry + failover
# ---------------------------------------------------------------------------


def test_chat_none_content_does_not_crash(monkeypatch):
    """content=None (reasoning models) must return None, not AttributeError."""
    svc = _openrouter_service(monkeypatch)
    svc.anthropic = None  # isolate: no fallback masking the result
    svc.openai = Mock()
    svc.openai.chat.completions.create.return_value = _completion(None)

    assert svc._chat("sys", "user") is None


def test_chat_length_finish_reason_retries_with_bigger_budget(monkeypatch):
    svc = _openrouter_service(monkeypatch)
    svc.anthropic = None
    svc.openai = Mock()
    svc.openai.chat.completions.create.side_effect = [
        _completion(None, "length"),
        _completion("finally some text", "stop"),
    ]

    text = svc._chat("sys", "user", max_tokens=200)

    assert text == "finally some text"
    calls = svc.openai.chat.completions.create.call_args_list
    assert calls[0].kwargs["max_tokens"] == 200
    assert calls[1].kwargs["max_tokens"] == 800  # quadrupled


def test_chat_fails_over_to_anthropic(monkeypatch):
    """OpenRouter empty completion + configured Anthropic key -> fallback."""
    svc = _openrouter_service(monkeypatch)
    svc.openai = Mock()
    svc.openai.chat.completions.create.return_value = _completion(None)
    svc.anthropic = Mock()
    svc.anthropic.messages.create.return_value = SimpleNamespace(
        content=[SimpleNamespace(text="  anthropic says hi  ")]
    )

    assert svc._chat("sys", "user") == "anthropic says hi"


def test_chat_fails_over_to_openrouter(monkeypatch):
    """Anthropic error + configured OpenRouter key -> fallback."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "an-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key-later")
    svc = LLMService()
    # Force anthropic-primary ordering while both clients exist.
    svc.provider, svc.model = "anthropic", "claude-haiku-4-5-20251001"
    svc.anthropic = Mock()
    svc.anthropic.messages.create.side_effect = RuntimeError("api down")
    svc.openai = Mock()
    svc.openai.chat.completions.create.return_value = _completion("or text")

    assert svc._chat("sys", "user") == "or text"


# ---------------------------------------------------------------------------
# Validation prompt: normalized dates[]/times[] shape must be visible
# ---------------------------------------------------------------------------


def _fake_llm(chat_return):
    fake = Mock()
    fake.provider = "anthropic"
    fake._chat = Mock(return_value=chat_return)
    return fake


VALID_JSON = '{"is_valid": true, "confidence": 0.9, "issues": [], "reasoning": "ok"}'
INVALID_JSON = (
    '{"is_valid": false, "confidence": 0.95, "issues": ["x"], "reasoning": "smells"}'
)

DATES_EVENT = {
    "title": "Paris, Texas - 40th Anniversary Screening",
    "dates": ["2026-07-24", "2026-07-26"],
    "times": ["7:00 PM", "4:00 PM"],
    "venue": "AFS",
    "type": "screening",
    "description": "Wim Wenders masterpiece in a new 4K restoration. " * 3,
}


def test_validation_prompt_includes_dates_arrays():
    fake = _fake_llm(VALID_JSON)
    svc = EventValidationService(llm_service=fake)

    result = svc.validate_event_content_with_llm(DATES_EVENT)

    assert result.passed is True
    prompt = fake._chat.call_args[0][1]
    assert "2026-07-24" in prompt
    assert "7:00 PM" in prompt
    assert "Date: N/A" not in prompt


def test_validation_prompt_still_handles_singular_shape():
    fake = _fake_llm(VALID_JSON)
    svc = EventValidationService(llm_service=fake)
    event = {
        "title": "Test Concert",
        "date": "2026-07-01",
        "time": "19:30",
        "venue": "Symphony",
        "type": "concert",
        "description": "A real evening of orchestral music. " * 5,
    }

    result = svc.validate_event_content_with_llm(event)

    assert result.passed is True
    prompt = fake._chat.call_args[0][1]
    assert "2026-07-01" in prompt
    assert "19:30" in prompt


def test_llm_invalid_verdict_is_advisory_not_critical():
    fake = _fake_llm(INVALID_JSON)
    svc = EventValidationService(llm_service=fake)

    result = svc.validate_event_content_with_llm(DATES_EVENT)

    assert result.passed is False
    assert result.level == ValidationLevel.WARNING


def test_advisory_verdict_does_not_sink_scraper_health():
    fake = _fake_llm(INVALID_JSON)
    svc = EventValidationService(llm_service=fake)

    health = svc.validate_scraper_health("AFS", [DATES_EVENT] * 3)

    assert health.success_rate == 1.0
    assert health.events_validated == 3


# ---------------------------------------------------------------------------
# Gate: graceful degradation vs systemic abort
# ---------------------------------------------------------------------------


def _schema_broken_event():
    return {"title": "", "venue": "AFS"}  # missing title + dates -> CRITICAL


def test_gate_continues_when_one_venue_fails():
    svc = EventValidationService(llm_service=_fake_llm(VALID_JSON))

    should_continue, _ = svc.validate_all_scrapers(
        {"AFS": [DATES_EVENT], "Broken": [_schema_broken_event()]}
    )

    assert should_continue is True


def test_gate_aborts_when_failures_outnumber_successes():
    svc = EventValidationService(llm_service=_fake_llm(VALID_JSON))

    should_continue, _ = svc.validate_all_scrapers(
        {
            "AFS": [DATES_EVENT],
            "Broken1": [_schema_broken_event()],
            "Broken2": [_schema_broken_event()],
        }
    )

    assert should_continue is False


def test_gate_aborts_when_everything_fails():
    svc = EventValidationService(llm_service=_fake_llm(VALID_JSON))

    should_continue, _ = svc.validate_all_scrapers(
        {"Broken1": [_schema_broken_event()], "Broken2": [_schema_broken_event()]}
    )

    assert should_continue is False


def test_gate_aborts_when_no_events_at_all():
    svc = EventValidationService(llm_service=_fake_llm(VALID_JSON))

    should_continue, _ = svc.validate_all_scrapers({"AFS": [], "Symphony": []})

    assert should_continue is False


# ---------------------------------------------------------------------------
# Recurring events: must emit the normalized dates[]/times[] shape
# ---------------------------------------------------------------------------


def test_recurring_meetup_events_have_normalized_dates():
    """Recurring events bypass scraper.format_event, so they must normalize
    themselves — NewYorkerMeetup was the one venue failing schema validation
    in the recovery run (missing `dates`)."""
    from src.recurring_events import RecurringEventGenerator

    svc = EventValidationService(llm_service=_fake_llm(VALID_JSON))
    for event in RecurringEventGenerator().generate_new_yorker_meetup_events(2):
        assert event["dates"] == [event["date"]]
        assert len(event["dates"]) == len(event["times"]) == 1
        assert svc.validate_event_schema(event).passed


def test_custom_recurring_events_have_normalized_dates():
    from src.recurring_events import RecurringEventGenerator

    events = RecurringEventGenerator().add_custom_recurring_event(
        title="Test Club",
        venue="TestVenue",
        location="Somewhere",
        day_of_week="Thursday",
        time="6:30 PM",
        description="A test recurring event.",
        url="https://example.com",
        weeks_ahead=2,
    )
    for event in events:
        assert event["dates"] == [event["date"]]
        assert event["times"] == ["6:30 PM"]
