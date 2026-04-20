"""Unit tests for scripts/build_rss_feed.py.

Covers ranking, top-N selection, description composition, deep-link
anchors, and XML round-tripping through ``xml.etree.ElementTree``.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_rss_feed.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("build_rss_feed", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["build_rss_feed"] = mod
    spec.loader.exec_module(mod)
    return mod


brf = _load_module()


NOW = datetime(2026, 4, 20, 12, 0, 0, tzinfo=timezone.utc)


def _sample_events() -> list[dict]:
    return [
        {
            "id": "upcoming-top",
            "title": "Bold Baroque Night",
            "rating": 9,
            "one_liner_summary": "A bracing early-Baroque programme.",
            "description": "<p>Full review body.</p>",
            "type": "concert",
            "venue": "La Follia Hall",
            "url": "https://example.org/baroque",
            "screenings": [
                {"date": "2026-05-01", "time": "19:30", "venue": "La Follia Hall"},
            ],
        },
        {
            "id": "past-top",
            "title": "Past Masterpiece",
            "rating": 10,
            "one_liner_summary": "Already happened — should rank below upcoming.",
            "description": "<p>Archive.</p>",
            "type": "movie",
            "venue": "AFS",
            "url": "https://example.org/past",
            "screenings": [{"date": "2025-01-15", "time": "19:00"}],
        },
        {
            "id": "mid-rated",
            "title": "Modest Matinee",
            "rating": 5,
            "one_liner_summary": "",
            "description": "<p>Midrange.</p>",
            "type": "movie",
            "venue": "AFS",
            "url": "https://example.org/mid",
            "dates": ["2026-06-01"],
            "times": ["14:00"],
        },
        {
            "id": "no-rating",
            "title": "Unrated Curiosity",
            "rating": None,
            "description": "<p>Rating TBD.</p>",
            "type": "other",
            "screenings": [{"date": "2026-07-01", "time": "18:00"}],
        },
        {
            "id": "low-upcoming",
            "title": "Gentle Sunday",
            "rating": 4,
            "description": "<p>Lightweight.</p>",
            "type": "book_club",
            "screenings": [{"date": "2026-05-05", "time": "10:00"}],
        },
    ]


@pytest.fixture
def events() -> list[dict]:
    return _sample_events()


def test_first_screening_datetime_prefers_screenings():
    dt = brf._first_screening_datetime(
        {
            "screenings": [
                {"date": "2026-05-02", "time": "15:00"},
                {"date": "2026-05-01", "time": "19:30"},
            ]
        }
    )
    assert dt is not None
    assert dt.year == 2026 and dt.month == 5 and dt.day == 1


def test_first_screening_datetime_falls_back_to_dates():
    dt = brf._first_screening_datetime({"dates": ["2026-07-01", "2026-06-01"]})
    assert dt is not None and dt.day == 1 and dt.month == 6


def test_first_screening_datetime_returns_none_when_missing():
    assert brf._first_screening_datetime({}) is None


def test_select_top_items_puts_upcoming_before_past_then_ranks_by_rating(events):
    items = brf.select_top_items(events, limit=10, now=NOW)
    ordered_ids = [i.event_id for i in items]
    # All four upcoming events precede the one past event.
    assert ordered_ids[:3] == ["upcoming-top", "mid-rated", "low-upcoming"]
    # Past-top has rating 10 but must rank below every upcoming event.
    assert ordered_ids[-1] == "past-top"
    # Within upcoming, higher rating wins (9 > 5 > 4).
    upcoming_ids = ordered_ids[: ordered_ids.index("past-top")]
    assert upcoming_ids.index("upcoming-top") < upcoming_ids.index("mid-rated")


def test_select_top_items_respects_limit(events):
    items = brf.select_top_items(events, limit=2, now=NOW)
    assert len(items) == 2


def test_select_top_items_skips_malformed_entries():
    events = [
        "not a dict",  # filtered: not a dict
        {"rating": 8},  # filtered: no title
        {"id": "good", "title": "Keep me", "rating": 7},
    ]
    items = brf.select_top_items(events, limit=5, now=NOW)
    assert [i.event_id for i in items] == ["good"]


def test_build_anchor_uses_event_id():
    # Anchors point at per-event shell pages (events/<slug>.html) so link-unfurl
    # bots reading the feed get rich OG/JSON-LD metadata; the shell auto-redirects
    # real users to the in-app #event=<slug> anchor.
    assert brf._build_anchor("abc") == brf.SITE_URL + "events/abc.html"
    assert brf._build_anchor("") == brf.SITE_URL


def test_build_anchor_slugifies_unsafe_chars():
    """Slashes, apostrophes, diacritics must not leak into the URL."""
    assert brf._build_anchor("8 1/2") == brf.SITE_URL + "events/8-1-2.html"
    assert brf._build_anchor("Don't Look Back") == brf.SITE_URL + "events/don-t-look-back.html"
    assert brf._build_anchor("Café") == brf.SITE_URL + "events/cafe.html"


def test_build_item_description_includes_anchor_and_review(events):
    item = brf.select_top_items(events, limit=1, now=NOW)[0]
    body = brf._build_item_description(item)
    assert item.site_anchor in body
    assert "events/upcoming-top.html" in body
    assert "<p>Full review body.</p>" in body
    assert "Rating: 9/10" in body


def test_build_rss_produces_valid_xml_round_trip(events, tmp_path):
    out = tmp_path / "feed.xml"
    count = brf.write_feed(events, out_path=out, limit=30, now=NOW)
    assert count == len(events)
    tree = ET.parse(out)
    root = tree.getroot()
    assert root.tag == "rss"
    assert root.attrib["version"] == "2.0"
    channel = root.find("channel")
    assert channel is not None
    assert channel.findtext("title") == brf.FEED_TITLE
    items = channel.findall("item")
    assert len(items) == len(events)
    first_link = items[0].findtext("link")
    assert first_link is not None and "events/upcoming-top.html" in first_link


def test_feed_items_have_required_rss_fields(events, tmp_path):
    out = tmp_path / "feed.xml"
    brf.write_feed(events, out_path=out, limit=30, now=NOW)
    root = ET.parse(out).getroot()
    for item in root.iter("item"):
        for tag in ("title", "link", "description", "pubDate", "guid"):
            assert item.find(tag) is not None, f"missing <{tag}>"


def test_main_writes_feed_from_data_file(tmp_path):
    data_path = tmp_path / "data.json"
    out = tmp_path / "feed.xml"
    data_path.write_text(json.dumps(_sample_events()))

    exit_code = brf.main(
        ["--data", str(data_path), "--out", str(out), "--quiet", "--limit", "3"]
    )
    assert exit_code == 0
    assert out.exists()
    root = ET.parse(out).getroot()
    assert len(root.findall("channel/item")) == 3


def test_load_events_rejects_non_list(tmp_path):
    bad = tmp_path / "data.json"
    bad.write_text(json.dumps({"not": "a list"}))
    with pytest.raises(ValueError):
        brf.load_events(bad)


def test_load_events_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        brf.load_events(tmp_path / "does-not-exist.json")


def test_atom_self_link_present(events, tmp_path):
    out = tmp_path / "feed.xml"
    brf.write_feed(events, out_path=out, now=NOW)
    root = ET.parse(out).getroot()
    atom_links = root.findall(
        "channel/{http://www.w3.org/2005/Atom}link"
    )
    assert any(l.attrib.get("rel") == "self" for l in atom_links)


def test_category_label_maps_known_types():
    assert brf._category_label("movie") == "Film"
    assert brf._category_label("visual_arts") == "Visual Arts"
    assert brf._category_label("unknown-type") == "Event"
