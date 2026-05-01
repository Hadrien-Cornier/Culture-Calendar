"""End-to-end tests for the ballet dance review pipeline.

These tests stitch together the three layers that produce a ballet
review on the live site:

1. ``BalletAustinScraper.scrape_events`` — must emit events tagged
   ``type=dance`` (NOT ``concert``, which was the bug that motivated
   the dance handler — see commit ``1510b62`` and CLAUDE.md task-2.1).
2. ``EventProcessor.process_events`` — must route ``type=dance`` events
   to ``_get_dance_rating`` and never to ``_get_classical_rating`` /
   ``_get_ai_rating``. The dance rating prompts must use dance-critic
   framing (Choreographic Craft, Performance Quality), not the
   musical-criticism rubric.
3. ``SummaryGenerator._call_claude_api`` — must dispatch
   ``type=dance`` to ``_build_dance_prompt`` so the one-liner names
   the choreographer, company, and program rather than a generic
   concert-style summary.

Together they guarantee the user-visible review on a Ballet Austin
card is dance-aware end to end. Network is fully mocked: Perplexity
and Anthropic clients return canned responses so the test runs as a
unit (`-m "not live and not integration"`).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

import pytest

from src.processor import EventProcessor
from src.scrapers.ballet_austin_scraper import BalletAustinScraper
from src.summary_generator import SummaryGenerator


# ---------------------------------------------------------------------------
# Canned LLM responses
# ---------------------------------------------------------------------------

DANCE_REVIEW = (
    "★ Rating: 8/10\n"
    "🎭 Choreographic Craft — Stephen Mills threads neoclassical phrases "
    "through unison passages that carry real architectural weight, with "
    "partnering work that quotes Balanchine without imitating him.\n"
    "✨ Performance Quality — the Ballet Austin company dances with precise "
    "upper-body carriage and a willingness to let silences in the score "
    "breathe before the next attack.\n"
    "📚 Cultural Significance — the programme situates Mills's commissioned "
    "repertoire alongside the established neoclassical canon, a useful "
    "argument for a regional company on the national stage.\n"
    "💡 Historical Context — the evening reads as a deliberate descendant of "
    "the string-quartet tradition Balanchine codified at NYCB."
)

DANCE_REFUSAL = (
    "I cannot provide a critical review of this performance because the "
    "search results do not surface any specific information about it. "
    "Writing such a review would be speculative rather than grounded in sources."
)

DANCE_ONE_LINER = (
    "Mills's neoclassical evening pairs a Balanchine debt with Ballet "
    "Austin's own commissioned voice."
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

BALLET_FIXTURE: Dict = {
    "balletAustin": [
        {
            "title": "GRIMM TALES",
            "program": "A bold reimagining of 19th-century fairy tales with "
            "original music by Graham Reynolds.",
            "dates": ["2026-09-26", "2026-09-27"],
            "times": ["7:30 PM", "3:00 PM"],
            "venue_name": "The Long Center",
            "series": "Ballet Austin 2026/27 Season",
            "type": "dance",
        },
        {
            "title": "IN MOTION",
            "program": "A curated selection of three deeply personal works "
            "by Stephen Mills.",
            "dates": ["2026-02-13"],
            "times": ["7:30 PM"],
            "venue_name": "The Long Center",
            "series": "Ballet Austin 2025/26 Season",
            "type": "dance",
        },
    ]
}


@pytest.fixture
def ballet_data_file(tmp_path: Path) -> Path:
    """Write a controlled ballet_data.json fixture and return its path."""
    f = tmp_path / "ballet_data.json"
    f.write_text(json.dumps(BALLET_FIXTURE), encoding="utf-8")
    return f


@pytest.fixture
def ballet_scraper(ballet_data_file: Path, monkeypatch) -> BalletAustinScraper:
    """A BalletAustinScraper pointed at the fixture instead of docs/."""
    # No API keys needed — the scraper just reads JSON. LLMService init in
    # BaseScraper tolerates missing keys (it logs a warning and continues).
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    scraper = BalletAustinScraper()
    scraper.data_file = str(ballet_data_file)
    return scraper


def _make_processor(monkeypatch, *, with_summary_generator: bool = False) -> EventProcessor:
    """Build an EventProcessor isolated from docs/data.json and the network."""
    monkeypatch.setenv("PERPLEXITY_API_KEY", "test-key")
    if with_summary_generator:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-used")
    else:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(EventProcessor, "_load_existing_data", lambda self: None)

    if with_summary_generator:
        # Skip on-disk cache I/O so the test never reads or writes the real
        # cache/summary_cache.json file.
        monkeypatch.setattr(SummaryGenerator, "_load_cache", lambda self: None)
        monkeypatch.setattr(SummaryGenerator, "_save_cache", lambda self: None)

    processor = EventProcessor()
    if not with_summary_generator:
        processor.summary_generator = None
    else:
        processor.summary_generator.summary_cache = {}
    return processor


def _ballet_event() -> Dict:
    """A normalized dance event matching the BalletAustinScraper output shape."""
    return {
        "title": "IN MOTION",
        "program": "A curated selection of three deeply personal works by Stephen Mills.",
        "series": "Ballet Austin 2025/26 Season",
        "date": "2026-02-13",
        "time": "7:30 PM",
        "venue": "BalletAustin",
        "company": "Ballet Austin",
        "choreographer": "Stephen Mills",
        "location": "The Long Center",
        "type": "dance",
        "url": "https://balletaustin.org",
    }


# ---------------------------------------------------------------------------
# Layer 1 — scraper produces dance events
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_scraper_emits_dance_type_for_every_event(ballet_scraper):
    """Every event from the Ballet Austin scraper is tagged ``type=dance``.

    Regression guard for the original bug at
    ``src/scrapers/ballet_austin_scraper.py:66`` where every ballet event
    was tagged ``type=concert`` and routed through the classical-music
    rating prompts. Task-2.1 (commit ``1510b62``) flipped that to
    ``dance``; this test fails the moment anyone flips it back.
    """
    events = ballet_scraper.scrape_events()

    assert events, "scraper produced no events from the fixture"
    types = {e.get("type") for e in events}
    assert types == {"dance"}, (
        f"Ballet events must all be type=dance, got {types}"
    )
    # And explicitly never concert — the precise bug we are guarding against.
    assert "concert" not in types


@pytest.mark.unit
def test_scraper_preserves_program_and_series_metadata(ballet_scraper):
    """Program + series fields must reach the processor untouched.

    These two fields are what the dance prompts use to produce a
    repertoire-aware review. If the scraper drops them, the downstream
    Claude prompt has nothing dance-specific to work with.
    """
    events = ballet_scraper.scrape_events()

    grimm = next((e for e in events if e["title"] == "GRIMM TALES"), None)
    assert grimm is not None
    assert "Graham Reynolds" in grimm["program"]
    assert grimm["series"] == "Ballet Austin 2026/27 Season"

    in_motion = next((e for e in events if e["title"] == "IN MOTION"), None)
    assert in_motion is not None
    assert "Stephen Mills" in in_motion["program"]
    assert in_motion["series"] == "Ballet Austin 2025/26 Season"


@pytest.mark.unit
def test_scraper_expands_dates_into_separate_events(ballet_scraper):
    """A multi-date production fans out into one event per occurrence.

    GRIMM TALES has two dates in the fixture; both must surface so the
    downstream calendar can list both performances.
    """
    events = ballet_scraper.scrape_events()
    grimm_dates = sorted(e["date"] for e in events if e["title"] == "GRIMM TALES")
    assert grimm_dates == ["2026-09-26", "2026-09-27"]


# ---------------------------------------------------------------------------
# Layer 2 — processor routes dance events to the dance handler
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_process_events_routes_dance_event_to_dance_rating(monkeypatch):
    """A ``type=dance`` event hits ``_get_dance_rating`` and nothing else.

    Mocks every other rating branch with a tripwire that fails the test
    if called. This is the regression guard that makes sure ballet
    events never silently fall back to the classical-music prompts even
    after a future refactor of the dispatcher.
    """
    processor = _make_processor(monkeypatch)
    calls: List[str] = []

    def _dance_stub(event: Dict) -> Dict:
        calls.append("dance")
        return {"score": 8, "summary": DANCE_REVIEW}

    def _trip(*_args, **_kwargs):  # pragma: no cover - tripwire
        raise AssertionError("dance event must not route to non-dance rating")

    monkeypatch.setattr(processor, "_get_dance_rating", _dance_stub)
    monkeypatch.setattr(processor, "_get_classical_rating", _trip)
    monkeypatch.setattr(processor, "_get_book_club_rating", _trip)
    monkeypatch.setattr(processor, "_get_visual_arts_rating", _trip)
    monkeypatch.setattr(processor, "_get_ai_rating", _trip)

    [enriched] = processor.process_events([_ballet_event()])

    assert calls == ["dance"]
    assert enriched["ai_rating"]["score"] == 8
    assert "Choreographic Craft" in enriched["description"]


@pytest.mark.unit
def test_dance_rating_uses_dance_critic_prompt(monkeypatch):
    """The strict prompt the processor sends Perplexity has dance framing.

    We capture every prompt sent to ``_call_perplexity`` and assert
    against the first one (the strict attempt). It must mention a dance
    critic and the dance-specific section headers, and must NOT reuse
    the classical-music rubric ("Artistic Merit", "Intellectual Depth")
    or the visual-arts rubric ("Formal Qualities").
    """
    processor = _make_processor(monkeypatch)
    captured: List[str] = []

    def _capture(prompt: str) -> str:
        captured.append(prompt)
        return DANCE_REVIEW

    monkeypatch.setattr(processor, "_call_perplexity", _capture)

    result = processor._get_dance_rating(_ballet_event())

    assert result["score"] == 8
    assert captured, "no prompt was sent to Perplexity"
    strict_prompt = captured[0]
    assert "dance critic" in strict_prompt.lower()
    assert "Choreographic Craft" in strict_prompt
    assert "Performance Quality" in strict_prompt
    # Cross-rubric leak-checks — the dance prompt is its own thing.
    assert "Artistic Merit" not in strict_prompt
    assert "Intellectual Depth" not in strict_prompt
    assert "Formal Qualities" not in strict_prompt
    # The event-level metadata that distinguishes a ballet event must be
    # threaded into the prompt verbatim, otherwise the LLM has no anchor.
    assert "Stephen Mills" in strict_prompt
    assert "Ballet Austin" in strict_prompt


@pytest.mark.unit
def test_dance_rating_recovers_from_initial_refusal(monkeypatch):
    """First strict prompt refuses; permissive retry produces a real review.

    Mirrors the production cascade: the strict dance prompt may refuse
    when Perplexity finds thin sources, the permissive retry instructs
    the model to draw on training-time knowledge of the choreographer
    and company. The ballet event must come out the other side with a
    valid score, not the default sentinel.
    """
    processor = _make_processor(monkeypatch)
    responses = iter([DANCE_REFUSAL, DANCE_REVIEW])
    monkeypatch.setattr(processor, "_call_perplexity", lambda _p: next(responses))

    result = processor._get_dance_rating(_ballet_event())

    assert result["score"] == 8
    assert "Choreographic Craft" in result["summary"]


@pytest.mark.unit
def test_dance_rating_total_refusal_falls_back_gracefully(monkeypatch):
    """All three Perplexity attempts refuse and Claude fallback is unavailable.

    Returned dict must be the human-readable sentinel — score 5 with a
    summary that names the performance — so downstream confidence
    detection can flag the event as "Pending more research" rather than
    leaving an empty review on the card.
    """
    processor = _make_processor(monkeypatch)
    monkeypatch.setattr(processor, "_call_perplexity", lambda _p: DANCE_REFUSAL)
    monkeypatch.setattr(processor, "_claude_fallback_dance", lambda *_a, **_kw: None)

    result = processor._get_dance_rating(_ballet_event())

    assert result["score"] == 5
    assert "Unable to evaluate" in result["summary"]
    assert "IN MOTION" in result["summary"]


# ---------------------------------------------------------------------------
# Layer 3 — full pipeline: scraper → processor → summary generator
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_full_pipeline_dance_review_lands_with_dance_aware_one_liner(
    ballet_scraper, monkeypatch
):
    """Scraper → processor → summary generator: every link is dance-aware.

    Asserts the chain end to end with both LLMs mocked:

    - Scraper emits ``type=dance`` events.
    - Processor's ``_call_perplexity`` returns the canned dance review.
    - SummaryGenerator's Claude client receives a dance-style prompt
      (with ``Program / Repertoire:`` framing, the choreographer's name,
      and the company's name) and returns the canned one-liner.
    - The enriched event carries an ``ai_rating`` with dance-critic
      sections and an ``oneLinerSummary`` from Claude.
    """
    processor = _make_processor(monkeypatch, with_summary_generator=True)
    monkeypatch.setattr(processor, "_call_perplexity", lambda _p: DANCE_REVIEW)

    captured_prompts: List[str] = []

    def fake_messages_create(**kwargs):
        captured_prompts.append(kwargs["messages"][0]["content"])

        class _Resp:
            content = [type("X", (), {"text": DANCE_ONE_LINER})()]

        return _Resp()

    monkeypatch.setattr(
        processor.summary_generator.client.messages,
        "create",
        fake_messages_create,
    )

    raw_events = ballet_scraper.scrape_events()
    # Pick one event and enrich it with the choreographer + company fields
    # the dance prompt builder reads. (The scraper does not yet populate
    # those — a future enrichment-layer task could; the prompt builder
    # accepts their absence by falling back to ``venue``, but threading
    # them in is the realistic production shape so we test both.)
    in_motion = next(e for e in raw_events if e["title"] == "IN MOTION")
    in_motion["company"] = "Ballet Austin"
    in_motion["choreographer"] = "Stephen Mills"

    [enriched] = processor.process_events([in_motion])

    # Layer 2: dance review attached.
    assert enriched["ai_rating"]["score"] == 8
    assert "Choreographic Craft" in enriched["description"]

    # Layer 3: dance prompt was used (not the generic / concert prompt).
    assert captured_prompts, "Claude API was never called"
    dance_prompt = captured_prompts[0]
    assert "Program / Repertoire:" in dance_prompt
    assert "Stephen Mills" in dance_prompt
    assert "Ballet Austin" in dance_prompt
    assert "2025/26 Season" in dance_prompt
    # And NOT the concert prompt's signature framing.
    assert "musical style, period" not in dance_prompt

    # One-liner reaches the event for the frontend card.
    assert enriched["oneLinerSummary"] == DANCE_ONE_LINER


@pytest.mark.unit
def test_full_pipeline_does_not_route_dance_through_concert_handler(monkeypatch):
    """A regression test for the original bug at one wider remove.

    Even with a fully integrated processor + summary generator, a
    ``type=dance`` event must never cause ``_get_classical_rating`` to
    fire. The tripwire on every non-dance handler asserts that. This is
    the bug class that motivated the entire dance-handler workstream
    (CLAUDE.md task-2.1), so the guard belongs in the e2e suite even
    when individual layers also test it.
    """
    processor = _make_processor(monkeypatch, with_summary_generator=True)

    def _trip(*_a, **_kw):  # pragma: no cover - tripwire
        raise AssertionError("dance event must not route to a non-dance handler")

    monkeypatch.setattr(processor, "_get_classical_rating", _trip)
    monkeypatch.setattr(processor, "_get_book_club_rating", _trip)
    monkeypatch.setattr(processor, "_get_visual_arts_rating", _trip)
    monkeypatch.setattr(processor, "_get_ai_rating", _trip)
    monkeypatch.setattr(processor, "_call_perplexity", lambda _p: DANCE_REVIEW)

    def fake_messages_create(**_kwargs):
        class _Resp:
            content = [type("X", (), {"text": DANCE_ONE_LINER})()]

        return _Resp()

    monkeypatch.setattr(
        processor.summary_generator.client.messages,
        "create",
        fake_messages_create,
    )

    [enriched] = processor.process_events([_ballet_event()])

    assert enriched["ai_rating"]["score"] == 8
    assert enriched["oneLinerSummary"] == DANCE_ONE_LINER
