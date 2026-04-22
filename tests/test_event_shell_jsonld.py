"""Tests for aggregateRating + offers in the event-shell JSON-LD.

Covers the rich-result additions: each per-event shell emits schema.org
``Offer`` (with ``url``) and ``AggregateRating`` so Google and other
search crawlers can surface ticket links and star ratings. Kept in a
dedicated module so the contract stays legible even as the main
builder test file grows.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_event_shells.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("build_event_shells", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


bes = _load_module()


def _event(**overrides) -> dict:
    base = {
        "id": "test-movie",
        "title": "Test Movie",
        "rating": 9,
        "oneLiner": "A stirring test of cinematic rigour.",
        "description": "<p>A long description.</p>",
        "venue": "Paramount Theatre",
        "type": "movie",
        "url": "https://tickets.example.com/test-movie",
        "screenings": [
            {
                "date": "2026-05-01",
                "time": "19:30",
                "url": "https://tickets.example.com/test-movie/2026-05-01",
            }
        ],
    }
    base.update(overrides)
    return base


def _extract_event_jsonld(html: str) -> dict:
    """Return the parsed ``Event`` JSON-LD payload (not the BreadcrumbList)."""
    for match in re.finditer(
        r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL
    ):
        raw = match.group(1).replace("<\\/", "</")
        payload = json.loads(raw)
        if payload.get("@type") == "Event":
            return payload
    raise AssertionError("No Event JSON-LD block found in shell HTML")


class TestTicketUrl:
    def test_prefers_first_screening_url(self):
        event = _event()
        shell = bes._shell_from_event(event)
        assert shell.ticket_url == "https://tickets.example.com/test-movie/2026-05-01"

    def test_falls_back_to_event_url(self):
        event = _event(screenings=[{"date": "2026-05-01", "time": "19:30"}])
        shell = bes._shell_from_event(event)
        assert shell.ticket_url == "https://tickets.example.com/test-movie"

    def test_falls_back_to_anchor_when_no_urls(self):
        event = _event(url=None, screenings=[])
        shell = bes._shell_from_event(event)
        assert shell.ticket_url == shell.anchor_url

    def test_empty_string_treated_as_missing(self):
        event = _event(url="", screenings=[{"date": "2026-05-01", "url": ""}])
        shell = bes._shell_from_event(event)
        assert shell.ticket_url == shell.anchor_url


class TestOffersJsonLd:
    def test_offers_block_present(self):
        shell = bes._shell_from_event(_event())
        payload = _extract_event_jsonld(bes.render_shell_html(shell))
        assert "offers" in payload
        offers = payload["offers"]
        assert offers["@type"] == "Offer"

    def test_offers_url_points_to_ticket_link(self):
        shell = bes._shell_from_event(_event())
        payload = _extract_event_jsonld(bes.render_shell_html(shell))
        assert payload["offers"]["url"].startswith("https://tickets.example.com/")

    def test_offers_url_present_even_without_ticket_info(self):
        event = _event(url=None, screenings=[])
        shell = bes._shell_from_event(event)
        payload = _extract_event_jsonld(bes.render_shell_html(shell))
        assert payload["offers"]["url"] == shell.anchor_url

    def test_offers_has_availability(self):
        shell = bes._shell_from_event(_event())
        payload = _extract_event_jsonld(bes.render_shell_html(shell))
        assert payload["offers"]["availability"].endswith("/InStock")


class TestAggregateRating:
    def test_aggregate_rating_present_when_rated(self):
        shell = bes._shell_from_event(_event(rating=8))
        payload = _extract_event_jsonld(bes.render_shell_html(shell))
        agg = payload["aggregateRating"]
        assert agg["@type"] == "AggregateRating"
        assert agg["ratingValue"] == 8
        assert agg["bestRating"] == 10
        assert agg["worstRating"] == 0
        assert agg["ratingCount"] >= 1

    def test_aggregate_rating_omitted_when_unrated(self):
        shell = bes._shell_from_event(_event(rating=None))
        payload = _extract_event_jsonld(bes.render_shell_html(shell))
        assert "aggregateRating" not in payload

    def test_aggregate_rating_omitted_for_non_numeric_rating(self):
        shell = bes._shell_from_event(_event(rating="tbd"))
        payload = _extract_event_jsonld(bes.render_shell_html(shell))
        assert "aggregateRating" not in payload
