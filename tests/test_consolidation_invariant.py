"""Regression test: every event's dates[] must cover all screening dates."""

import json
import pathlib

import pytest

DATA_JSON = pathlib.Path(__file__).resolve().parent.parent / "docs" / "data.json"


def _load_events():
    with open(DATA_JSON) as f:
        return json.load(f)


def test_the_stranger_dates_match_screenings():
    """If THE STRANGER is in the data, its dates[] must equal its unique
    screening dates (the movie-consolidation invariant).

    The exact number of screenings depends on what AFS happens to be showing,
    so don't hardcode a count; skip when the film isn't currently scheduled.
    The generic invariant for all events is covered by the test below.
    """
    events = _load_events()
    stranger = next(
        (e for e in events if "STRANGER" in e.get("title", "").upper()), None
    )
    if stranger is None:
        pytest.skip("THE STRANGER not in current docs/data.json (not playing)")

    screening_dates = sorted({s["date"] for s in stranger.get("screenings", [])})
    event_dates = sorted(stranger.get("dates", []))
    assert (
        event_dates == screening_dates
    ), f"dates field {event_dates} != screening dates {screening_dates}"


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
