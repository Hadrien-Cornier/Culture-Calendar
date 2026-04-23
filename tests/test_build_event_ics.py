"""Unit tests for scripts/build_event_ics.py.

Exercises slug→.ics emission, iCalendar round-trip, multi-screening
events collapsing into one file with N VEVENTs, skipping of
unidentifiable or un-dated events, and the CLI entry point.
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
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_event_ics.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("build_event_ics", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["build_event_ics"] = mod
    spec.loader.exec_module(mod)
    return mod


bei = _load_module()


def _stamp() -> datetime:
    return datetime(2026, 4, 22, 12, 0, tzinfo=pytz.UTC)


def _sample_events() -> list[dict]:
    return [
        {
            "id": "baroque-night",
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
                    "url": "https://example.org/concert/1",
                },
                {
                    "date": "2026-05-02",
                    "time": "15:00",
                    "venue": "LaFollia Hall",
                    "url": "https://example.org/concert/2",
                },
            ],
        },
        {
            "id": "matinee-screen",
            "title": "Matinee Screening",
            "rating": 6,
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
            "id": "garden-installation",
            "title": "Garden Installation",
            "rating": 7,
            "type": "visual_arts",
            "venue": "Contemporary Austin",
            "url": "https://example.org/exhibit",
            "dates": ["2026-06-01"],
            "times": ["10:00"],
        },
        {
            # Identifiable but every screening has no parseable time →
            # no VEVENTs; should be skipped entirely (no empty .ics).
            "id": "mystery-screening",
            "title": "Mystery",
            "type": "movie",
            "screenings": [{"date": "2026-05-04", "time": ""}],
        },
        {
            # No id and no title — cannot form a slug; must be skipped.
            "type": "other",
            "screenings": [{"date": "2026-05-04", "time": "18:00"}],
        },
    ]


@pytest.fixture
def events() -> list[dict]:
    return _sample_events()


def _event_count(cal: icalendar.Calendar) -> int:
    return sum(1 for c in cal.subcomponents if c.name == "VEVENT")


def test_event_slug_matches_safe_slug(events):
    # The baroque event's slug matches the shared safe_slug helper so
    # docs/events/<slug>.html and docs/events/<slug>.ics line up.
    from scripts._slug_util import safe_slug

    assert bei._event_slug(events[0]) == safe_slug("baroque-night")


def test_event_slug_returns_none_for_unidentifiable():
    assert bei._event_slug({}) is None
    assert bei._event_slug({"id": "", "title": ""}) is None


def test_build_event_calendar_fans_screenings_into_vevents(events):
    cal = bei._build_event_calendar(events[0], stamp=_stamp())
    assert cal is not None
    assert _event_count(cal) == 2
    # Round-trip stays valid.
    parsed = icalendar.Calendar.from_ical(cal.to_ical())
    assert str(parsed["version"]) == "2.0"
    assert _event_count(parsed) == 2


def test_build_event_calendar_dates_times_fallback(events):
    # Visual-arts event uses the dates[]/times[] fallback path.
    cal = bei._build_event_calendar(events[2], stamp=_stamp())
    assert cal is not None
    assert _event_count(cal) == 1


def test_build_event_calendar_returns_none_when_no_parseable_times(events):
    # Mystery screening has empty times → no VEVENTs → no .ics file.
    assert bei._build_event_calendar(events[3], stamp=_stamp()) is None


def test_build_event_calendars_skips_unidentifiable_and_dedupes(events):
    doubled = events + [events[0]]  # duplicate slug should not double-write
    calendars = bei.build_event_calendars(doubled, stamp=_stamp())
    # 3 writable events: baroque-night, matinee-screen, garden-installation.
    # mystery-screening has no parseable times; the untitled event has no slug.
    assert set(calendars.keys()) == {
        "baroque-night",
        "matinee-screen",
        "garden-installation",
    }


def test_write_event_ics_emits_one_file_per_event(tmp_path, events):
    out = tmp_path / "events"
    count = bei.write_event_ics(events, out_dir=out, stamp=_stamp())
    assert count == 3
    produced = sorted(p.name for p in out.glob("*.ics"))
    assert produced == [
        "baroque-night.ics",
        "garden-installation.ics",
        "matinee-screen.ics",
    ]


def test_emitted_ics_is_valid_icalendar(tmp_path, events):
    out = tmp_path / "events"
    bei.write_event_ics(events, out_dir=out, stamp=_stamp())
    for path in out.glob("*.ics"):
        body = path.read_bytes()
        assert b"BEGIN:VCALENDAR" in body
        assert b"SUMMARY:" in body
        cal = icalendar.Calendar.from_ical(body)
        assert str(cal["version"]) == "2.0"
        assert _event_count(cal) >= 1


def test_write_event_ics_clears_stale_ics(tmp_path, events):
    out = tmp_path / "events"
    out.mkdir()
    stale = out / "ghost-event.ics"
    stale.write_text("BEGIN:VCALENDAR\nEND:VCALENDAR\n")
    companion = out / "ghost-event.html"
    companion.write_text("<!-- kept -->")

    bei.write_event_ics(events, out_dir=out, stamp=_stamp())
    # Stale .ics swept away, companion formats untouched.
    assert not stale.exists()
    assert companion.exists()


def test_main_writes_ics_from_data_json(tmp_path):
    data_path = tmp_path / "data.json"
    out = tmp_path / "events"
    data_path.write_text(json.dumps(_sample_events()))

    exit_code = bei.main(["--data", str(data_path), "--out", str(out), "--quiet"])
    assert exit_code == 0
    ics_files = list(out.glob("*.ics"))
    assert len(ics_files) == 3
    for path in ics_files:
        icalendar.Calendar.from_ical(path.read_bytes())


def test_main_respects_default_data_path_structure(tmp_path, monkeypatch):
    # main() must not crash on a well-formed but empty data.json — it should
    # simply produce zero files and exit 0.
    data_path = tmp_path / "data.json"
    out = tmp_path / "events"
    data_path.write_text("[]")
    exit_code = bei.main(["--data", str(data_path), "--out", str(out), "--quiet"])
    assert exit_code == 0
    assert list(out.glob("*.ics")) == []
