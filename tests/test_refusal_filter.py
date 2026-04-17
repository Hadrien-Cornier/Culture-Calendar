"""Tests for the description-level refusal filter."""

import pytest

from src.refusal import REFUSAL_STUB, filter_refusal, is_refusal_response


NISH_KUMAR_STYLE_REFUSAL = (
    "I cannot provide a critical review of this comedy special because "
    "the search results do not contain any relevant information about "
    "Nish Kumar's upcoming Paramount performance. Writing such a review "
    "would be speculative rather than grounded in sources."
)

LEGITIMATE_REVIEW = (
    "★ Rating: 8/10\n"
    "🎭 Artistic Merit — Kumar's stand-up is built on tight political "
    "argument and crisp timing; his 2019 tour footage shows he can carry "
    "a 70-minute set on rhetorical escalation alone.\n"
    "✨ Originality — the material rejects both smug centrism and lazy "
    "edgelord bait; it leans on research and specificity, which few "
    "touring comedians bother with.\n"
    "📚 Cultural Significance — Kumar is one of the few British comedians "
    "whose material crosses the Atlantic without losing bite.\n"
    "💡 Intellectual Depth — the set assumes the audience can follow a "
    "policy argument to its conclusion. That respect is rare."
)


@pytest.mark.unit
def test_filter_refusal_substitutes_nish_kumar_style_refusal() -> None:
    assert filter_refusal(NISH_KUMAR_STYLE_REFUSAL) == REFUSAL_STUB


@pytest.mark.unit
def test_filter_refusal_passes_through_legitimate_review() -> None:
    assert filter_refusal(LEGITIMATE_REVIEW) == LEGITIMATE_REVIEW


@pytest.mark.unit
def test_filter_refusal_handles_empty_input() -> None:
    assert filter_refusal("") == ""
    assert filter_refusal(None) is None  # type: ignore[arg-type]


@pytest.mark.unit
def test_is_refusal_response_detects_nish_kumar_style() -> None:
    assert is_refusal_response(NISH_KUMAR_STYLE_REFUSAL) is True


@pytest.mark.unit
def test_is_refusal_response_rejects_legitimate_review() -> None:
    assert is_refusal_response(LEGITIMATE_REVIEW) is False


@pytest.mark.unit
def test_is_refusal_response_rejects_empty() -> None:
    assert is_refusal_response("") is False
    assert is_refusal_response(None) is False  # type: ignore[arg-type]


@pytest.mark.unit
def test_processor_reexports_is_refusal_response() -> None:
    """summary_generator.py and scripts/verify_calendar.py import
    is_refusal_response from src.processor; the re-export must remain."""
    from src.processor import is_refusal_response as reexported

    assert reexported(NISH_KUMAR_STYLE_REFUSAL) is True
    assert reexported(LEGITIMATE_REVIEW) is False


# --- clean_event_refusals: walks BOTH description and one_liner_summary ----
# Regression: the 04-18 T2.4 cleanup only checked `description` and left
# refusal-shaped `one_liner_summary` values intact on-site. This must not
# recur.


@pytest.mark.unit
def test_clean_event_refusals_cleans_both_fields() -> None:
    from src.refusal import clean_event_refusals

    event = {
        "title": "Nish Kumar",
        "description": NISH_KUMAR_STYLE_REFUSAL,
        "one_liner_summary": (
            "I cannot provide a meaningful summary without actual "
            "event details to work from."
        ),
    }
    cleaned, changed = clean_event_refusals(event)

    assert cleaned["description"] == REFUSAL_STUB
    assert cleaned["one_liner_summary"] == REFUSAL_STUB
    assert set(changed) == {"description", "one_liner_summary"}


@pytest.mark.unit
def test_clean_event_refusals_leaves_legitimate_unchanged() -> None:
    from src.refusal import clean_event_refusals

    event = {
        "title": "Something Good",
        "description": LEGITIMATE_REVIEW,
        "one_liner_summary": "A terrific night out.",
    }
    cleaned, changed = clean_event_refusals(event)

    assert cleaned == event
    assert changed == []


@pytest.mark.unit
def test_clean_event_refusals_does_not_mutate_input() -> None:
    from src.refusal import clean_event_refusals

    event = {"description": NISH_KUMAR_STYLE_REFUSAL, "one_liner_summary": ""}
    _, _ = clean_event_refusals(event)

    # Original must still carry the refusal text — the function returns a copy.
    assert event["description"] == NISH_KUMAR_STYLE_REFUSAL
