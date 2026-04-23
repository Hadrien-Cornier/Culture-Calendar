"""Structural tests for task-T1.3 Google Calendar share-intent.

Background: the task adds three pieces of behavioral JS in
``docs/script.js`` — a ``_firstShowing`` fallback helper, a ``_gcalDates``
date-format helper, and a ``google-calendar`` entry in the ``PLATFORMS``
array consumed by ``buildPopover``. Plus ``trackPlatform`` is extended
to turn dashes in the platform id into underscores so Plausible events
keep a clean ``cc_share_google_calendar`` name.

The test strategy matches the existing structural approach used in
``tests/test_venue_card_rendering.py``: extract each JS function body by
brace-matching and assert the code paths are present. No JS runtime is
pulled in (no pyppeteer, no Node, no npm install). That keeps the fence
of "no new deps" from CLAUDE.md while covering every new behavior the
test-integrity-critic flagged in the T1.3 review.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "docs" / "script.js"


def _extract_function_body(source: str, signature: str) -> str:
    """Return the ``{...}`` body of the first function matching ``signature``.

    Shared style with ``tests/test_venue_card_rendering.py``; kept local to
    avoid a cross-test helper module.
    """
    idx = source.index(signature)
    open_brace = source.index("{", idx)
    depth = 0
    for i in range(open_brace, len(source)):
        ch = source[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return source[open_brace : i + 1]
    raise AssertionError(f"unterminated function body for {signature!r}")


def _extract_platform_entry(source: str, platform_id: str) -> str:
    """Return the object literal for a PLATFORMS entry with id=<platform_id>.

    Finds the opening brace of the entry and walks forward to the matching
    close brace. Uses the ``id:`` key as the anchor since every entry
    declares one.
    """
    needle = f'id: "{platform_id}"'
    idx = source.index(needle)
    # Walk backward to find the entry's opening brace.
    open_brace = source.rfind("{", 0, idx)
    depth = 0
    for i in range(open_brace, len(source)):
        ch = source[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return source[open_brace : i + 1]
    raise AssertionError(f"unterminated entry for id={platform_id!r}")


@pytest.fixture(scope="module")
def script_source() -> str:
    return SCRIPT_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def first_showing_body(script_source: str) -> str:
    return _extract_function_body(script_source, "function _firstShowing")


@pytest.fixture(scope="module")
def gcal_dates_body(script_source: str) -> str:
    return _extract_function_body(script_source, "function _gcalDates")


@pytest.fixture(scope="module")
def track_platform_body(script_source: str) -> str:
    return _extract_function_body(script_source, "function trackPlatform")


@pytest.fixture(scope="module")
def gcal_platform_entry(script_source: str) -> str:
    return _extract_platform_entry(script_source, "google-calendar")


# --- _firstShowing fallback logic ----------------------------------------


@pytest.mark.unit
def test_first_showing_handles_null_event(first_showing_body: str) -> None:
    """Must short-circuit when ev is null."""
    assert re.search(
        r"if\s*\(\s*!ev\s*\)\s*return\s+null", first_showing_body
    ), "_firstShowing must return null for null event"


@pytest.mark.unit
def test_first_showing_prefers_showings_array(first_showing_body: str) -> None:
    """Primary path: ev.showings[0] when the list is non-empty."""
    assert re.search(
        r"ev\.showings", first_showing_body
    ), "_firstShowing must consult ev.showings first"
    assert re.search(
        r"list\[0\]|showings\[0\]", first_showing_body
    ), "_firstShowing must return the first entry of the showings array"


@pytest.mark.unit
def test_first_showing_falls_back_to_dates_times(first_showing_body: str) -> None:
    """Fallback path: synthesize {date,time,venue,url} from ev.dates+ev.times."""
    assert re.search(
        r"ev\.dates", first_showing_body
    ), "_firstShowing must read ev.dates on fallback"
    assert re.search(
        r"ev\.times", first_showing_body
    ), "_firstShowing must read ev.times on fallback"
    assert re.search(
        r"date:\s*dates\[0\]", first_showing_body
    ), "_firstShowing fallback must return dates[0] as the date"


@pytest.mark.unit
def test_first_showing_returns_null_when_no_data(first_showing_body: str) -> None:
    """Final fallback: neither showings nor dates → return null."""
    # Two return statements: one for populated dates, one terminal null.
    null_returns = re.findall(r"return\s+null\b", first_showing_body)
    assert (
        len(null_returns) >= 2
    ), "_firstShowing must have both null short-circuit and terminal null return"


# --- _gcalDates format, rollover, and all-day handling ---------------------


@pytest.mark.unit
def test_gcal_dates_short_circuits_on_missing_date(gcal_dates_body: str) -> None:
    """No date → empty string (not a malformed Google URL)."""
    assert re.search(
        r'if\s*\(\s*!date\s*\)\s*return\s+""', gcal_dates_body
    ), "_gcalDates must return empty string when date is missing"


@pytest.mark.unit
def test_gcal_dates_strips_hyphens_from_date(gcal_dates_body: str) -> None:
    """YYYY-MM-DD must become YYYYMMDD for Google's URL format."""
    assert re.search(
        r'replace\s*\(\s*/-/g\s*,\s*""\s*\)', gcal_dates_body
    ), "_gcalDates must strip hyphens from ISO dates (YYYY-MM-DD → YYYYMMDD)"


@pytest.mark.unit
def test_gcal_dates_emits_all_day_range_when_no_time(gcal_dates_body: str) -> None:
    """Missing time → all-day entry (YYYYMMDD/YYYYMMDD) with +1 day end."""
    # The all-day branch is gated on !time and increments the date by 1.
    assert re.search(
        r"if\s*\(\s*!time\s*\)", gcal_dates_body
    ), "_gcalDates must branch on missing time"
    assert re.search(
        r"setDate\s*\(\s*next\.getDate\(\)\s*\+\s*1\s*\)", gcal_dates_body
    ), "_gcalDates all-day branch must increment end date by 1 day"


@pytest.mark.unit
def test_gcal_dates_emits_timed_range_with_two_hour_duration(
    gcal_dates_body: str,
) -> None:
    """Timed event: end = start + 2h (matches ICS generator default)."""
    assert re.search(
        r"2\s*\*\s*60\s*\*\s*60\s*\*\s*1000", gcal_dates_body
    ), "_gcalDates must compute end time as start + 2 hours"


@pytest.mark.unit
def test_gcal_dates_midnight_rollover_uses_date_object(
    gcal_dates_body: str,
) -> None:
    """23:30 start + 2h must roll to next day — relies on Date arithmetic
    rather than string splicing. If someone ever rewrites the math to
    splice hours, this guard flags the regression.
    """
    assert re.search(
        r"new\s+Date\s*\(.*startMs\s*\+", gcal_dates_body
    ), "_gcalDates must use Date arithmetic for end-time (so midnight rolls over correctly)"
    assert re.search(
        r"endDate\.getFullYear\(\)", gcal_dates_body
    ), "_gcalDates must read end components from the rolled Date object"
    assert re.search(
        r"endDate\.getMonth\(\)\s*\+\s*1", gcal_dates_body
    ), "_gcalDates must format end month with +1 offset (JS 0-indexed months)"


@pytest.mark.unit
def test_gcal_dates_timed_format_includes_T_separator(
    gcal_dates_body: str,
) -> None:
    """Timed output must match YYYYMMDDTHHMMSS/YYYYMMDDTHHMMSS per Google spec."""
    # Start side: 'd + "T" + hh + mm + "00"'.
    assert re.search(
        r'd\s*\+\s*"T"\s*\+\s*hh\s*\+\s*mm\s*\+\s*"00"', gcal_dates_body
    ), "_gcalDates must emit start as YYYYMMDDTHHMMSS"
    # End side: 'ed + "T" + eh + emin + "00"' — whitespace tolerant.
    assert re.search(
        r'ed\s*\+\s*"T"\s*\+\s*eh\s*\+\s*emin\s*\+\s*"00"', gcal_dates_body
    ), "_gcalDates must emit end as YYYYMMDDTHHMMSS"


@pytest.mark.unit
def test_gcal_dates_pads_hours_and_minutes(gcal_dates_body: str) -> None:
    """Single-digit hh/mm must be zero-padded ("07:05" not "7:5")."""
    pad_start_count = len(re.findall(r'padStart\s*\(\s*2\s*,\s*"0"\s*\)', gcal_dates_body))
    assert (
        pad_start_count >= 4
    ), "_gcalDates must pad hour + minute for both start and end (4+ padStart calls)"


# --- google-calendar PLATFORMS entry --------------------------------------


@pytest.mark.unit
def test_gcal_platform_has_correct_id(gcal_platform_entry: str) -> None:
    """Platform id is the exact string 'google-calendar' used by appliesTo
    filter and trackPlatform name-building logic.
    """
    assert 'id: "google-calendar"' in gcal_platform_entry


@pytest.mark.unit
def test_gcal_platform_has_label_with_emoji(gcal_platform_entry: str) -> None:
    """UI label includes the calendar emoji for visual parity with others."""
    assert re.search(
        r'label:\s*"[^"]*Google Calendar"', gcal_platform_entry
    ), "google-calendar platform must carry a 'Google Calendar' label"


@pytest.mark.unit
def test_gcal_platform_applies_only_when_gcal_dates_present(
    gcal_platform_entry: str,
) -> None:
    """Digest shares have no single event datetime — the platform must opt
    out via appliesTo(shareable) returning false when shareable.gcalDates
    is empty. This prevents a broken URL with dates=.
    """
    assert re.search(
        r"appliesTo:\s*function\s*\([^)]*\)\s*\{[^}]*!!\s*\w+\.gcalDates",
        gcal_platform_entry,
    ), "google-calendar must have appliesTo() returning !!shareable.gcalDates"


@pytest.mark.unit
def test_gcal_platform_uses_render_endpoint_with_template_action(
    gcal_platform_entry: str,
) -> None:
    """The URL must hit calendar.google.com/calendar/render?action=TEMPLATE —
    that's the documented quick-add endpoint. Any other path (like
    /event or /eventedit) is wrong.
    """
    assert "calendar.google.com/calendar/render" in gcal_platform_entry
    assert "action=TEMPLATE" in gcal_platform_entry


@pytest.mark.unit
def test_gcal_platform_passes_required_params_through_builder(
    gcal_platform_entry: str,
) -> None:
    """URL must include text, dates, details as core params — these match the
    Google Calendar quick-add template.
    """
    assert re.search(
        r'"&text="\s*\+\s*enc\s*\(\s*[a-zA-Z_]+\.title\s*\)', gcal_platform_entry
    ), "google-calendar URL must include encoded text= param"
    assert re.search(
        r'"&dates="\s*\+\s*[a-zA-Z_]+\.gcalDates', gcal_platform_entry
    ), "google-calendar URL must include raw dates= param (already formatted)"
    assert re.search(
        r'"&details="\s*\+\s*enc\s*\(\s*[a-zA-Z_]+\.body\s*\)', gcal_platform_entry
    ), "google-calendar URL must include encoded details= param"


@pytest.mark.unit
def test_gcal_platform_location_is_conditional(gcal_platform_entry: str) -> None:
    """location is optional — the builder must guard on s.location truthiness
    so an event missing its address doesn't emit 'location=' with no value.
    """
    assert re.search(
        r"\?\s*\"&location=\"\s*\+\s*enc\s*\(\s*[a-zA-Z_]+\.location\s*\)",
        gcal_platform_entry,
    ), "google-calendar URL must conditionally include location= (ternary guard)"


# --- trackPlatform dash-to-underscore transform ----------------------------


@pytest.mark.unit
def test_track_platform_converts_dashes_to_underscores(
    track_platform_body: str,
) -> None:
    """trackPlatform must turn 'google-calendar' into 'google_calendar' so the
    emitted Plausible event name becomes 'cc_share_google_calendar' — a
    clean grep target that won't collide with dashed IDs in Plausible's
    URL parser.
    """
    assert re.search(
        r'replace\s*\(\s*/-/g\s*,\s*"_"\s*\)', track_platform_body
    ), "trackPlatform must replace dashes with underscores in platform id"


@pytest.mark.unit
def test_track_platform_emits_cc_share_prefix(track_platform_body: str) -> None:
    """The Plausible event name must be namespaced 'cc_share_' + slug so the
    analytics catalog (cc_share_twitter, cc_share_bluesky, …) stays
    consistent and the grep that T5.1 depends on keeps working.
    """
    assert re.search(
        r'"cc_share_"\s*\+', track_platform_body
    ), "trackPlatform must emit 'cc_share_' + slug as the Plausible event name"
    assert "window.plausible" in track_platform_body, (
        "trackPlatform must call window.plausible(...)"
    )


@pytest.mark.unit
def test_track_platform_is_crash_safe(track_platform_body: str) -> None:
    """Plausible may be blocked by ad-blockers; the tracking call must be
    wrapped in try/catch so a share still works with no analytics loaded.
    """
    assert (
        "try" in track_platform_body and "catch" in track_platform_body
    ), "trackPlatform must be crash-safe (try/catch around window.plausible)"


# --- shareable plumbing: _firstShowing + _gcalDates wired into eventShareable


@pytest.mark.unit
def test_event_shareable_plumbs_gcal_dates(script_source: str) -> None:
    """eventShareable must compute gcalDates from the first showing so the
    google-calendar appliesTo() filter evaluates correctly downstream.
    """
    body = _extract_function_body(script_source, "function eventShareable")
    assert "_firstShowing" in body, (
        "eventShareable must call _firstShowing to get the datetime source"
    )
    assert "_gcalDates" in body, (
        "eventShareable must call _gcalDates to build the google-calendar dates param"
    )
    assert re.search(r"gcalDates\s*:", body), (
        "eventShareable return value must carry a gcalDates field"
    )
    assert re.search(r"location\s*:", body), (
        "eventShareable return value must carry a location field (used by gcal URL)"
    )
