"""Tests for EventProcessor rating branches.

Focus: the visual_arts rating branch added in task-T1.6 must route through the
art-critic prompt family, retry on refusal, and fall through to the standard
parse helper on success. process_events must pick it based on type.
"""

from __future__ import annotations

from typing import Dict, List

import pytest

from src.processor import EventProcessor


SAMPLE_VISUAL_ARTS_REVIEW = (
    "★ Rating: 8/10\n"
    "🎭 Formal Qualities — the series of chromogenic prints exploits a "
    "narrow tonal register to push depth into the surface.\n"
    "✨ Originality — the artist's lateral move from sculpture into "
    "photography reframes familiar subject matter.\n"
    "📚 Cultural Significance — the work enters a live conversation about "
    "labor and landscape in contemporary West Texas photography.\n"
    "💡 Historical Context — the show extends a 1970s Becher-school "
    "typological impulse into a distinctly regional register."
)

NISH_KUMAR_STYLE_REFUSAL = (
    "I cannot provide a critical review of this exhibition because the "
    "search results do not contain any relevant information about the show. "
    "Writing such a review would be speculative rather than grounded in sources."
)


def _make_processor(monkeypatch, api_key: str | None = "test-key") -> EventProcessor:
    """Build an EventProcessor without loading docs/data.json or summary generator."""
    if api_key is None:
        monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
    else:
        monkeypatch.setenv("PERPLEXITY_API_KEY", api_key)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(EventProcessor, "_load_existing_data", lambda self: None)
    processor = EventProcessor()
    processor.summary_generator = None
    return processor


def _visual_arts_event() -> Dict:
    return {
        "title": "Field Notes from the Llano",
        "type": "visual_arts",
        "event_category": "visual_arts",
        "venue": "Women & Their Work",
        "url": "https://example.org/field-notes",
        "dates": ["2026-05-01"],
        "times": ["10:00"],
        "artist": "Jane Doe",
        "medium": "photography",
    }


@pytest.mark.unit
def test_get_visual_arts_rating_returns_default_without_api_key(monkeypatch):
    processor = _make_processor(monkeypatch, api_key=None)
    result = processor._get_visual_arts_rating(_visual_arts_event())
    assert result == {"score": 5, "summary": "No API key provided"}


@pytest.mark.unit
def test_get_visual_arts_rating_parses_successful_response(monkeypatch):
    processor = _make_processor(monkeypatch)
    monkeypatch.setattr(processor, "_call_perplexity", lambda prompt: SAMPLE_VISUAL_ARTS_REVIEW)

    result = processor._get_visual_arts_rating(_visual_arts_event())

    assert result["score"] == 8
    assert "Formal Qualities" in result["summary"]


@pytest.mark.unit
def test_get_visual_arts_rating_retries_on_refusal(monkeypatch):
    processor = _make_processor(monkeypatch)
    responses = iter([NISH_KUMAR_STYLE_REFUSAL, NISH_KUMAR_STYLE_REFUSAL, SAMPLE_VISUAL_ARTS_REVIEW])
    monkeypatch.setattr(processor, "_call_perplexity", lambda prompt: next(responses))

    result = processor._get_visual_arts_rating(_visual_arts_event())

    assert result["score"] == 8
    # The refusal attempts were consumed before the successful knowledge prompt.
    assert "Formal Qualities" in result["summary"]


@pytest.mark.unit
def test_get_visual_arts_rating_falls_through_on_all_refusals(monkeypatch):
    processor = _make_processor(monkeypatch)
    monkeypatch.setattr(processor, "_call_perplexity", lambda prompt: NISH_KUMAR_STYLE_REFUSAL)
    monkeypatch.setattr(
        processor,
        "_claude_fallback_visual_arts",
        lambda event, details: None,
    )

    result = processor._get_visual_arts_rating(_visual_arts_event())

    assert result["score"] == 5
    assert "Unable to evaluate" in result["summary"]
    assert "Field Notes from the Llano" in result["summary"]


@pytest.mark.unit
def test_visual_arts_strict_prompt_uses_art_critic_sections(monkeypatch):
    processor = _make_processor(monkeypatch)
    details = "Exhibition: Field Notes from the Llano\nArtist(s): Jane Doe\nMedium: photography"

    prompt = processor._build_visual_arts_prompt_strict(details)

    # Art-critic framing — formal qualities, cultural significance, historical context.
    assert "art critic" in prompt.lower()
    assert "Formal Qualities" in prompt
    assert "Cultural Significance" in prompt
    assert "Historical Context" in prompt
    # Must NOT reuse cinematic / musical framing.
    assert "Artistic Merit" not in prompt
    assert "Intellectual Depth" not in prompt


@pytest.mark.unit
def test_process_events_routes_visual_arts_to_visual_arts_rating(monkeypatch):
    processor = _make_processor(monkeypatch)

    calls: List[str] = []

    def _visual_arts_stub(event: Dict) -> Dict:
        calls.append("visual_arts")
        return {"score": 7, "summary": "stub visual arts review"}

    def _fail(*_args, **_kwargs):  # pragma: no cover - guard, should not run
        raise AssertionError("wrong rating branch taken for visual_arts event")

    monkeypatch.setattr(processor, "_get_visual_arts_rating", _visual_arts_stub)
    monkeypatch.setattr(processor, "_get_classical_rating", _fail)
    monkeypatch.setattr(processor, "_get_book_club_rating", _fail)
    monkeypatch.setattr(processor, "_get_ai_rating", _fail)

    [enriched] = processor.process_events([_visual_arts_event()])

    assert calls == ["visual_arts"]
    assert enriched["ai_rating"] == {"score": 7, "summary": "stub visual arts review"}
    assert enriched["description"] == "stub visual arts review"
