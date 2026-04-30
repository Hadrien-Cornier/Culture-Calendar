"""Unit tests for SummaryGenerator prompt builders.

Focus: ``_build_book_prompt`` must return ``None`` (skip summary) when
book/author metadata is absent, instead of raising — book-club events
without a titled book have nothing useful to summarize, and raising
forced the whole event through the error path. Other validation
failures (missing title, missing/short description, missing event
dict) remain hard errors because they signal upstream pipeline bugs
rather than normal-shape data gaps.
"""

import pytest

from src.summary_generator import SummaryGenerator


@pytest.fixture
def generator(monkeypatch):
    """SummaryGenerator with a stubbed Anthropic key (no network calls)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-used")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    return SummaryGenerator()


LONG_DESCRIPTION = (
    "Detailed literary analysis spanning several themes, "
    "narrative voice, and historical context. " * 4
)


def test_build_book_prompt_missing_book_and_author_returns_none(generator):
    event = {"venue": "Alienated Majesty Books"}
    result = generator._build_book_prompt(
        "January Book Club", LONG_DESCRIPTION, event
    )
    assert result is None


def test_build_book_prompt_with_book_returns_prompt(generator):
    event = {
        "venue": "Alienated Majesty Books",
        "book": "My Brilliant Friend",
        "author": "",
    }
    result = generator._build_book_prompt(
        "Ferrante Reading Group", LONG_DESCRIPTION, event
    )
    assert isinstance(result, str)
    assert "My Brilliant Friend" in result


def test_build_book_prompt_with_author_only_returns_prompt(generator):
    event = {
        "venue": "First Light Austin",
        "book": "",
        "author": "Susan Sontag",
    }
    result = generator._build_book_prompt(
        "Sontag Discussion", LONG_DESCRIPTION, event
    )
    assert isinstance(result, str)
    assert "Susan Sontag" in result


def test_build_book_prompt_missing_title_still_raises(generator):
    event = {"book": "X", "author": "Y", "venue": "Z"}
    with pytest.raises(ValueError, match="missing required title"):
        generator._build_book_prompt("", LONG_DESCRIPTION, event)


def test_build_book_prompt_missing_description_still_raises(generator):
    event = {"book": "X", "author": "Y", "venue": "Z"}
    with pytest.raises(ValueError, match="missing required AI analysis"):
        generator._build_book_prompt("Some Event", "", event)


def test_build_book_prompt_short_description_still_raises(generator):
    event = {"book": "X", "author": "Y", "venue": "Z"}
    with pytest.raises(ValueError, match="insufficient AI analysis"):
        generator._build_book_prompt("Some Event", "too short", event)


def test_build_book_prompt_missing_event_dict_still_raises(generator):
    with pytest.raises(ValueError, match="missing essential event data"):
        generator._build_book_prompt("Some Event", LONG_DESCRIPTION, None)


def test_call_claude_api_returns_none_for_book_event_missing_metadata(
    generator, monkeypatch
):
    """End-to-end: book_club event with no book/author skips API call entirely."""
    called = {"count": 0}

    def fail_if_called(*_a, **_kw):  # pragma: no cover - guard
        called["count"] += 1
        raise AssertionError("API must not be called when metadata is missing")

    monkeypatch.setattr(generator.client.messages, "create", fail_if_called)

    event = {
        "title": "January Book Club",
        "description": LONG_DESCRIPTION,
        "type": "book_club",
        "venue": "Alienated Majesty Books",
    }
    assert generator._call_claude_api(event) is None
    assert called["count"] == 0


# Title-rejection scope: festival/workshop/gala/tribute words alone should
# not veto an event when richer metadata (director / book / author /
# featured artist / composers) confirms it's a specific, summarizable thing.

def test_festival_title_with_director_is_specific(generator):
    event = {
        "title": "Bergman Festival",
        "description": "Short description",
        "director": "Ingmar Bergman",
    }
    assert generator._is_specific_event(event) is True


def test_workshop_title_with_featured_artist_is_specific(generator):
    event = {
        "title": "Piano Workshop with Pollini",
        "description": "Brief blurb",
        "featured_artist": "Maurizio Pollini",
    }
    assert generator._is_specific_event(event) is True


def test_gala_title_with_composers_is_specific(generator):
    event = {
        "title": "Symphony Gala",
        "description": "Brief blurb",
        "composers": ["Ludwig van Beethoven"],
    }
    assert generator._is_specific_event(event) is True


def test_tribute_title_with_author_is_specific(generator):
    event = {
        "title": "Tribute to Toni Morrison",
        "description": "Brief blurb",
        "author": "Toni Morrison",
    }
    assert generator._is_specific_event(event) is True


def test_festival_title_without_metadata_still_rejected(generator):
    event = {
        "title": "Generic Movie Festival",
        "description": "Brief blurb",
        "venue": "Some Theater",
    }
    assert generator._is_specific_event(event) is False


def test_workshop_title_without_metadata_still_rejected(generator):
    event = {
        "title": "Songwriting Workshop",
        "description": "Brief blurb",
        "venue": "Some Studio",
    }
    assert generator._is_specific_event(event) is False


def test_symposium_still_rejects_even_with_metadata(generator):
    """Non-overridable indicators stay strict — symposium/conference/lecture
    are formats, not specific summarizable events."""
    event = {
        "title": "Annual Film Symposium",
        "description": "Brief blurb",
        "director": "Some Director",
    }
    assert generator._is_specific_event(event) is False


def test_lecture_still_rejects_even_with_metadata(generator):
    event = {
        "title": "Lecture on Cinema",
        "description": "Brief blurb",
        "director": "Some Director",
    }
    assert generator._is_specific_event(event) is False


def test_retrospective_in_title_still_rejects_without_metadata(generator):
    event = {
        "title": "Cinema Retrospective",
        "description": "Brief blurb",
        "venue": "Some Theater",
    }
    assert generator._is_specific_event(event) is False
