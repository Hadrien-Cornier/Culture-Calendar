"""Unit tests for scripts/build_ics_feed.py.

Covers screening flattening, datetime parsing, top-picks filtering, and
that the emitted ICS bytes parse back through ``icalendar.Calendar``.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path

import icalendar
import pytest
import pytz

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_ics_feed.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("build_ics_feed", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["build_ics_feed"] = mod
    spec.loader.exec_module(mod)
    return mod


bif = _load_module()


def _sample_events() -> list[dict]:
    return [
        {
            "id": "sample-concert-1",
            "title": "La Follia Baroque Night",
            "rating": 8,
            "one_liner_summary": "Bold early-baroque recital.",
            "description": "<p>Great stuff</p>",
            "type": "concert",
            "venue": "LaFollia",
            "url": "https://example.org/concert",
            "screenings": [
                {
                    "date": "2026-05-01",
                    "time": "19:30",
                    "venue": "LaFollia Hall",
                    "url": "https://example.org/concert",
                },
                {
                    "date": "2026-05-02",
                    "time": "15:00",
                    "venue": "LaFollia Hall",
                    "url": "https://example.org/concert",
                },
            ],
        },
        {
            "id": "sample-movie-1",
            "title": "Low-rated Matinee",
            "rating": 3,
            "one_liner_summary": "",
            "description": "",
            "type": "movie",
            "venue": "AFS",
            "url": "https://example.org/movie",
            "screenings": [
                {
                    "date": "2026-05-03",
                    "time": "7:30 PM",
                    "venue": "AFS Cinema",
                    "url": "https://example.org/movie",
                }
            ],
        },
        {
            "id": "sample-visual-1",
            "title": "Garden Installation",
            "rating": 7,
            "one_liner_summary": "Soil and lineage.",
            "description": "<p>Exhibit</p>",
            "type": "visual_arts",
            "venue": "Contemporary Austin",
            "url": "https://example.org/exhibit",
            "dates": ["2026-06-01"],
            "times": ["10:00"],
        },
        {
            "id": "rating-missing",
            "title": "Rating Missing",
            "rating": None,
            "type": "other",
            "screenings": [{"date": "2026-05-04", "time": "18:00"}],
        },
    ]


def _event_count(cal: icalendar.Calendar) -> int:
    return sum(1 for c in cal.subcomponents if c.name == "VEVENT")


def _summaries(cal: icalendar.Calendar) -> list[str]:
    return [str(c["summary"]) for c in cal.subcomponents if c.name == "VEVENT"]


@pytest.fixture
def events() -> list[dict]:
    return _sample_events()


def test_iter_screenings_flattens_screenings_and_dates_pairs(events):
    rows = list(bif._iter_screenings(events))
    # 2 + 1 + 1 (dates/times fallback) + 1 = 5 screenings total
    assert len(rows) == 5
    # screening-based events keep their per-screening venue
    concert_rows = [r for r in rows if r.event_id == "sample-concert-1"]
    assert all(r.venue == "LaFollia Hall" for r in concert_rows)
    # dates/times fallback inherits event-level venue/url
    visual_row = next(r for r in rows if r.event_id == "sample-visual-1")
    assert visual_row.venue == "Contemporary Austin"
    assert visual_row.url == "https://example.org/exhibit"


def test_parse_datetime_handles_24h_and_12h_and_austin_tz():
    dt_24h = bif._parse_datetime("2026-05-01", "19:30")
    dt_12h = bif._parse_datetime("2026-05-01", "7:30 PM")
    assert dt_24h == dt_12h
    assert dt_24h.tzinfo is not None
    # America/Chicago is UTC-5 (CDT) in May
    utc = dt_24h.astimezone(pytz.UTC)
    assert utc.hour == 0 and utc.day == 2


@pytest.mark.parametrize("bad", ["not-a-time", "25:00", "", ":30"])
def test_parse_datetime_returns_none_for_invalid_times(bad):
    assert bif._parse_datetime("2026-05-01", bad) is None


def test_parse_datetime_returns_none_for_invalid_date():
    assert bif._parse_datetime("2026/05/01", "19:30") is None


def test_build_calendar_emits_one_vevent_per_screening(events):
    screenings = list(bif._iter_screenings(events))
    cal = bif.build_calendar(
        screenings,
        cal_name="Test",
        cal_desc="Test",
        stamp=datetime(2026, 4, 20, tzinfo=pytz.UTC),
    )
    # 5 screenings but 1 of them (rating-missing: no date fallback issues) is valid;
    # every screening with a valid date+time becomes a VEVENT
    assert _event_count(cal) == 5
    # Round-trips through from_ical
    round_trip = icalendar.Calendar.from_ical(cal.to_ical())
    assert _event_count(round_trip) == 5


def test_top_picks_filter_excludes_low_rated(tmp_path, events):
    all_out = tmp_path / "calendar.ics"
    top_out = tmp_path / "top-picks.ics"

    all_count, top_count = bif.write_feeds(
        events,
        all_out=all_out,
        top_out=top_out,
        min_rating=7,
        stamp=datetime(2026, 4, 20, tzinfo=pytz.UTC),
    )
    # 2 concert screenings + 1 movie + 1 visual-arts fallback + 1 null-rating = 5
    assert all_count == 5
    # rating >= 7: 2 concerts (rating 8) + 1 visual_arts (rating 7) = 3
    assert top_count == 3

    top_cal = icalendar.Calendar.from_ical(top_out.read_bytes())
    titles = " ".join(_summaries(top_cal))
    assert "Low-rated Matinee" not in titles
    assert "Rating Missing" not in titles
    assert "La Follia Baroque Night" in titles
    assert "Garden Installation" in titles


def test_write_feeds_output_is_valid_ical(tmp_path, events):
    all_out = tmp_path / "calendar.ics"
    top_out = tmp_path / "top-picks.ics"
    bif.write_feeds(events, all_out=all_out, top_out=top_out)

    for path in (all_out, top_out):
        # Round-trip: parsing back with from_ical must not raise
        cal = icalendar.Calendar.from_ical(path.read_bytes())
        assert str(cal["version"]) == "2.0"
        assert "PRODID" in cal


def test_uid_is_stable_per_screening():
    s = bif.Screening(
        event_id="stable-id",
        title="x",
        rating=7,
        one_liner="",
        description_html="",
        type_="movie",
        venue="",
        date="2026-05-01",
        time="19:30",
        url="",
    )
    assert bif._build_uid(s) == "stable-id-2026-05-01-1930@culturecalendar.local"


def test_main_writes_both_feeds_via_data_file(tmp_path):
    # Build a tiny data.json and run main() against it
    data_path = tmp_path / "data.json"
    all_out = tmp_path / "calendar.ics"
    top_out = tmp_path / "top-picks.ics"
    data_path.write_text(json.dumps(_sample_events()))

    exit_code = bif.main(
        [
            "--data",
            str(data_path),
            "--all-out",
            str(all_out),
            "--top-out",
            str(top_out),
            "--quiet",
        ]
    )
    assert exit_code == 0
    assert all_out.exists()
    assert top_out.exists()
    # Both round-trip through icalendar
    assert icalendar.Calendar.from_ical(all_out.read_bytes())
    assert icalendar.Calendar.from_ical(top_out.read_bytes())


def test_load_events_rejects_non_list(tmp_path):
    bad = tmp_path / "data.json"
    bad.write_text(json.dumps({"not": "a list"}))
    with pytest.raises(ValueError):
        bif.load_events(bad)


def test_load_events_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        bif.load_events(tmp_path / "does-not-exist.json")
