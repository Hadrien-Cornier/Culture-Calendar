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
