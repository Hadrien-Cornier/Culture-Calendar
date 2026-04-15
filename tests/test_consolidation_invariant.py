"""Regression test: every event's dates[] must cover all screening dates."""

import json
import pathlib

import pytest

DATA_JSON = pathlib.Path(__file__).resolve().parent.parent / "docs" / "data.json"


def _load_events():
    with open(DATA_JSON) as f:
        return json.load(f)


def _find_stranger(events):
    for evt in events:
        if "STRANGER" in evt.get("title", "").upper():
            return evt
    pytest.fail("THE STRANGER (L'ETRANGER) not found in docs/data.json")


def test_the_stranger_6_dates():
    """THE STRANGER must have dates == set of unique screening dates."""
    events = _load_events()
    stranger = _find_stranger(events)

    screening_dates = sorted({s["date"] for s in stranger.get("screenings", [])})
    assert len(screening_dates) >= 6, f"Expected >=6 screening dates, got {screening_dates}"

    event_dates = sorted(stranger.get("dates", []))
    assert event_dates == screening_dates, (
        f"dates field {event_dates} != screening dates {screening_dates}"
    )


def test_all_events_dates_match_screenings():
    """For every event with screenings, dates[] must equal the unique screening dates."""
    events = _load_events()
    mismatches = []
    for evt in events:
        screenings = evt.get("screenings", [])
        if not screenings:
            continue
        screening_dates = sorted({s["date"] for s in screenings})
        event_dates = sorted(evt.get("dates", []))
        if event_dates != screening_dates:
            mismatches.append(
                f"{evt.get('title', '???')}: dates={event_dates}, screenings={screening_dates}"
            )
    assert not mismatches, f"Date/screening mismatches:\n" + "\n".join(mismatches)
