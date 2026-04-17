"""Classification tests for scrapers and processor short-circuits.

Focus: Paper Cuts @ AFS Cinema is a pop-up bookshop Alienated Majesty runs in
the AFS Cinema lobby, NOT a book club and NOT the film itself. The scraper
must emit it as type=other with a deterministic factual description, and the
processor must not overwrite pre-filled descriptions on type=other events.
"""

from __future__ import annotations

import os
from typing import Dict

import pytest

from src.refusal import is_refusal_response
from src.scrapers.alienated_majesty_scraper import AlienatedMajestyBooksScraper


def _paper_cuts_event() -> Dict:
    """Build a Paper Cuts event through the scraper's own helper."""
    return AlienatedMajestyBooksScraper._build_paper_cuts_event(
        title="Paper Cuts @ AFS Cinema - Stalker",
        paired_film="Stalker",
        date_iso="2026-05-17",
        url="https://www.alienatedmajestybooks.com/book-clubs",
    )


@pytest.mark.unit
def test_paper_cuts_event_is_type_other_not_book_club():
    event = _paper_cuts_event()
    assert event["type"] == "other"
    assert event["type"] != "book_club"


@pytest.mark.unit
def test_paper_cuts_description_is_factual_not_refusal():
    event = _paper_cuts_event()
    description = event.get("description", "")
    assert description.strip(), "Paper Cuts events must carry a pre-filled description"
    assert "pop-up bookshop" in description.lower()
    assert "Stalker" in description
    assert is_refusal_response(description) is False


@pytest.mark.unit
def test_paper_cuts_one_liner_mentions_paired_film():
    event = _paper_cuts_event()
    one_liner = event.get("one_liner_summary", "")
    assert one_liner.startswith("Pop-up bookshop")
    assert "Stalker" in one_liner
    assert "AFS Cinema lobby" in one_liner


@pytest.mark.unit
def test_paper_cuts_event_has_venue_and_paired_film_fields():
    event = _paper_cuts_event()
    assert event["venue"] == "AFS Cinema Lobby"
    assert event["paired_film"] == "Stalker"
    assert event["series"] == "Paper Cuts @ AFS Cinema"


@pytest.mark.unit
def test_processor_skips_llm_for_type_other_with_prefilled_description(monkeypatch):
    """Processor must not overwrite a scraper-authored description on type=other."""
    # Isolate the processor from env-driven LLM paths.
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    from src.processor import EventProcessor

    processor = EventProcessor()

    prefilled_description = (
        "<p>Alienated Majesty sets up a curated pop-up bookshop in the "
        "AFS Cinema lobby around the screening of Stalker.</p>"
    )
    event = {
        "title": "Paper Cuts @ AFS Cinema - Stalker",
        "type": "other",
        "description": prefilled_description,
        "one_liner_summary": "Pop-up bookshop by Alienated Majesty around Stalker.",
        "dates": ["2026-05-17"],
        "times": ["7:00 PM"],
        "venue": "AFS Cinema Lobby",
    }

    def _fail(*_args, **_kwargs):
        raise AssertionError("LLM path must not run for type=other with pre-filled description")

    # If any of these are invoked, the short-circuit is broken.
    monkeypatch.setattr(processor, "_get_ai_rating", _fail)
    monkeypatch.setattr(processor, "_get_classical_rating", _fail)
    monkeypatch.setattr(processor, "_get_book_club_rating", _fail)

    [enriched] = processor.process_events([event])

    assert enriched["description"] == prefilled_description
    assert enriched["type"] == "other"
    assert enriched["ai_rating"]["summary"] == prefilled_description
    assert is_refusal_response(enriched["description"]) is False
