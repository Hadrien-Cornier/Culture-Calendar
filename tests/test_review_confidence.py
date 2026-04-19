"""Tests for the review_confidence signal on _parse_ai_response.

Contract: _parse_ai_response returns a dict including a review_confidence
field set to "low" when the summary is a refusal or contains an
explicit-insufficient phrase, and "high" otherwise. Confidence must NOT be
derived from raw length — a terse but substantive review scores high, and a
long evasive answer scores low.
"""

from __future__ import annotations

import pytest

from src.processor import EventProcessor


REFUSAL_STYLE_SUMMARY = (
    "I cannot provide a critical review of this show because the search "
    "results do not contain any relevant information about the performer. "
    "Writing such a review would be speculative rather than grounded in sources."
)

EXPLICIT_INSUFFICIENT_SUMMARY = (
    "★ Rating: 6/10\n"
    "This chamber recital pairs two mid-career violinists in a program of "
    "Romantic sonatas. Could not verify the exact repertoire against the "
    "venue's program notes, and there is limited information about the "
    "ensemble's prior Austin appearances."
)

LONG_SUBSTANTIVE_REVIEW = (
    "★ Rating: 8/10\n"
    "🎭 Artistic Merit — the ensemble builds from a rigorous early-music "
    "rhetoric and leans into the ornamented repeats without ever slipping "
    "into museum-piece caution.\n"
    "✨ Originality — the pairing of a Biber rosary sonata with a Rameau "
    "suite would be a gimmick in lesser hands; here it reads as an argument "
    "about devotional theatre.\n"
    "📚 Cultural Significance — Austin has a thin early-music bench and "
    "programs of this specificity rarely survive a single season.\n"
    "💡 Intellectual Depth — the group respects the listener enough to "
    "trust that structural repetition can still surprise."
)

TERSE_HIGH_SIGNAL_REVIEW = (
    "A masterpiece. Director Kubrick's 2001 remains peerless. 9/10."
)


def _make_processor(monkeypatch) -> EventProcessor:
    """Build an EventProcessor without hitting docs/data.json or network."""
    monkeypatch.setenv("PERPLEXITY_API_KEY", "test-key")
    monkeypatch.setattr(EventProcessor, "_load_existing_data", lambda self: None)
    processor = EventProcessor()
    processor.summary_generator = None
    return processor


@pytest.mark.unit
def test_refusal_response_marked_low_confidence(monkeypatch) -> None:
    processor = _make_processor(monkeypatch)
    result = processor._parse_ai_response(REFUSAL_STYLE_SUMMARY)
    assert result["review_confidence"] == "low"


@pytest.mark.unit
def test_explicit_insufficient_phrase_marked_low_confidence(monkeypatch) -> None:
    processor = _make_processor(monkeypatch)
    result = processor._parse_ai_response(EXPLICIT_INSUFFICIENT_SUMMARY)
    assert result["review_confidence"] == "low"


@pytest.mark.unit
def test_long_substantive_review_marked_high_confidence(monkeypatch) -> None:
    processor = _make_processor(monkeypatch)
    result = processor._parse_ai_response(LONG_SUBSTANTIVE_REVIEW)
    assert result["review_confidence"] == "high"


@pytest.mark.unit
def test_high_signal_terse_review_marked_high_confidence(monkeypatch) -> None:
    """Terse but substantive text must not be downgraded purely for its length."""
    processor = _make_processor(monkeypatch)
    result = processor._parse_ai_response(TERSE_HIGH_SIGNAL_REVIEW)
    assert result["review_confidence"] == "high"


# --- Cache-aware re-rate of refusal-shaped cached entries (task-T2.4) ------
# Regression guard: if a previous run cached a Perplexity refusal as the
# summary, the next regular run must treat that entry as stale and re-rate
# it via the fresh retry chain — without needing --force-reprocess. Cached
# entries that carry a legitimate (even low-score) review must still be
# served from cache, so honest low-rating work is not churned.

from typing import Dict, List  # noqa: E402


def _movie_event(title: str = "LANCELOT DU LAC") -> Dict:
    return {
        "title": title,
        "type": "movie",
        "venue": "afs",
        "url": "https://example.org/lancelot",
        "dates": ["2026-05-01"],
        "times": ["19:30"],
    }


@pytest.mark.unit
def test_process_events_rerates_refusal_shaped_cached_entry(monkeypatch) -> None:
    processor = _make_processor(monkeypatch)
    event = _movie_event()

    processor.movie_cache[event["title"].upper().strip()] = {
        "score": 5,
        "summary": REFUSAL_STYLE_SUMMARY,
    }

    calls: List[str] = []

    def _ai_rating_stub(e: Dict) -> Dict:
        calls.append(e["title"])
        return {"score": 9, "summary": "Bresson's austere craft..."}

    monkeypatch.setattr(processor, "_get_ai_rating", _ai_rating_stub)

    [enriched] = processor.process_events([event])

    assert calls == [event["title"]]
    assert enriched["ai_rating"]["score"] == 9
    assert enriched["ai_rating"]["summary"].startswith("Bresson")
    assert processor.movie_cache[event["title"].upper().strip()]["score"] == 9


@pytest.mark.unit
def test_process_events_keeps_legitimate_low_score_cached_entry(monkeypatch) -> None:
    processor = _make_processor(monkeypatch)
    event = _movie_event(title="THE HEIGHT OF THE COCONUT TREES")

    legitimate_low_score_summary = (
        "★ Rating: 2/10\n"
        "🎭 Artistic Merit — the film hits no identifiable register; the "
        "cinematography is serviceable but the pacing collapses in the "
        "second act.\n"
        "✨ Originality — nothing on-screen distinguishes the material from "
        "a standard regional art-house entry.\n"
        "📚 Cultural Significance — limited; the film has not entered any "
        "critical conversation since its 2024 festival premiere.\n"
        "💡 Intellectual Depth — the script settles for restatement rather "
        "than inquiry."
    )
    processor.movie_cache[event["title"].upper().strip()] = {
        "score": 2,
        "summary": legitimate_low_score_summary,
    }

    def _fail(*_args, **_kwargs):  # pragma: no cover
        raise AssertionError("AI rating should NOT be called on legitimate cache hit")

    monkeypatch.setattr(processor, "_get_ai_rating", _fail)
    monkeypatch.setattr(processor, "_get_classical_rating", _fail)
    monkeypatch.setattr(processor, "_get_book_club_rating", _fail)
    monkeypatch.setattr(processor, "_get_visual_arts_rating", _fail)

    [enriched] = processor.process_events([event])

    assert enriched["ai_rating"]["score"] == 2
    assert enriched["ai_rating"]["summary"] == legitimate_low_score_summary
    assert enriched["description"] == legitimate_low_score_summary


# --- build_event_from_template: missing field falls back to "unknown" ------
# Contract: the output builder reads ai_rating.review_confidence if present.
# When an event arrives without any confidence signal (e.g., a pre-T2.1
# cached entry, a scraper that bypassed the AI pipeline, or a unit-test
# fixture), the emitted JSON must carry "unknown" — never None or missing.
# This protects the UI bucket logic in docs/script.js which treats
# `(ev.review_confidence || "unknown")` as the canonical default.


def _movie_template():
    from src.config_loader import ConfigLoader

    config = ConfigLoader()
    return ConfigLoader(), config.get_template("movie")


@pytest.mark.unit
def test_build_event_from_template_defaults_missing_confidence_to_unknown() -> None:
    from update_website_data import build_event_from_template

    config, template = _movie_template()
    event = {
        "title": "UNRATED EDGE CASE",
        "type": "movie",
        "venue": "afs",
        "url": "https://example.org/x",
        "dates": ["2026-05-01"],
        "times": ["19:30"],
        "ai_rating": {"score": 7, "summary": "A concise but honest review."},
    }

    output = build_event_from_template(event, template, config)

    assert output["review_confidence"] == "unknown"


@pytest.mark.unit
def test_build_event_from_template_passes_through_explicit_confidence() -> None:
    from update_website_data import build_event_from_template

    config, template = _movie_template()
    event = {
        "title": "LOW CONFIDENCE CASE",
        "type": "movie",
        "venue": "afs",
        "url": "https://example.org/x",
        "dates": ["2026-05-01"],
        "times": ["19:30"],
        "ai_rating": {
            "score": 5,
            "summary": "Thin sources; see venue page.",
            "review_confidence": "low",
        },
    }

    output = build_event_from_template(event, template, config)

    assert output["review_confidence"] == "low"


@pytest.mark.unit
def test_build_event_from_template_handles_missing_ai_rating() -> None:
    """An event with no ai_rating dict at all must still yield unknown."""
    from update_website_data import build_event_from_template

    config, template = _movie_template()
    event = {
        "title": "NO AI RATING AT ALL",
        "type": "movie",
        "venue": "afs",
        "url": "https://example.org/x",
        "dates": ["2026-05-01"],
        "times": ["19:30"],
    }

    output = build_event_from_template(event, template, config)

    assert output["review_confidence"] == "unknown"


# --- is_refusal_response integration sanity --------------------------------
# compute_confidence delegates refusal detection to is_refusal_response,
# so a regression in the refusal detector is a regression in the confidence
# signal. Guard the contract end-to-end here rather than rely solely on the
# parse-level tests above.


@pytest.mark.unit
def test_is_refusal_response_detects_canonical_refusal() -> None:
    from src.processor import is_refusal_response

    assert is_refusal_response(REFUSAL_STYLE_SUMMARY) is True


@pytest.mark.unit
def test_is_refusal_response_passes_substantive_review() -> None:
    from src.processor import is_refusal_response

    assert is_refusal_response(LONG_SUBSTANTIVE_REVIEW) is False
    assert is_refusal_response(TERSE_HIGH_SIGNAL_REVIEW) is False


@pytest.mark.unit
def test_is_refusal_response_ignores_empty_or_short_text() -> None:
    """Empty / very short strings are not refusals — they're a separate gate."""
    from src.processor import is_refusal_response

    assert is_refusal_response("") is False
    assert is_refusal_response("TBD") is False


@pytest.mark.unit
def test_compute_confidence_unknown_on_empty_returns_low_not_unknown() -> None:
    """Contract guard: _parse_ai_response never emits "unknown" directly —
    the "unknown" bucket is reserved for build_event_from_template fallback
    when ai_rating lacks the field entirely. compute_confidence on an empty
    string must return "low" so an empty LLM response is quarantined, not
    silently passed as unknown."""
    from src.processor import compute_confidence

    assert compute_confidence("") == "low"
    assert compute_confidence(None) == "low"  # type: ignore[arg-type]
