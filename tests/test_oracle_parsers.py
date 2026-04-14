"""Validate the oracle parsers against the provided markdown fixtures.

If these tests fail, either the fixture changed or the parsers drifted — both
are signals the overnight loop needs to investigate before running scrapers.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.oracle_afs import (  # noqa: E402
    FilmScreening,
    is_film_title,
    parse_afs_schedule,
)
from scripts.oracle_hyperreal import (  # noqa: E402
    HyperrealEntry,
    films_only,
    parse_hyperreal_schedule,
)


AFS_FIXTURE = ROOT / "tests" / "april-may-2026-schedule-afs.md"
HYPERREAL_FIXTURE = ROOT / "tests" / "april-2026-hyperreal.md"


@pytest.fixture(scope="session")
def afs_screenings() -> list[FilmScreening]:
    return parse_afs_schedule(AFS_FIXTURE)


@pytest.fixture(scope="session")
def hyperreal_entries() -> list[HyperrealEntry]:
    return parse_hyperreal_schedule(HYPERREAL_FIXTURE)


class TestAFSOracle:
    def test_film_classifier_accepts_all_caps(self):
        assert is_film_title("MIROIRS NO. 3")
        assert is_film_title("PALESTINE '36")
        assert is_film_title("CHIME + SERPENT'S PATH")
        assert is_film_title("A SERIOUS MAN")
        assert is_film_title("DEAD MOUNTAINEER'S HOTEL")

    def test_film_classifier_accepts_numeric_titles(self):
        """'8 1/2' has no alphabetic characters — treat as film."""
        assert is_film_title("8 1/2")

    def test_film_classifier_rejects_title_case(self):
        assert not is_film_title("Producer Program Info Session")
        assert not is_film_title("Intro to Blackmagic Pocket Camera 6K Pro")
        assert not is_film_title("Studio 3 Training")
        assert not is_film_title("Screenwriting 101")

    def test_parser_yields_expected_film_count(self, afs_screenings):
        assert len(afs_screenings) >= 80, \
            f"Expected ≥80 film screenings, got {len(afs_screenings)}"
        unique = {s.title for s in afs_screenings}
        assert len(unique) >= 40, \
            f"Expected ≥40 unique film titles, got {len(unique)}"

    def test_all_dates_in_yyyy_mm_dd(self, afs_screenings):
        import re
        for s in afs_screenings:
            assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", s.date), f"Bad date: {s.date}"

    def test_all_times_in_24h(self, afs_screenings):
        import re
        for s in afs_screenings:
            assert re.fullmatch(r"\d{2}:\d{2}", s.time_24h), f"Bad time_24h: {s.time_24h}"

    def test_parser_handles_multi_time_rows(self, afs_screenings):
        """'PALESTINE '36 — 12:30 PM, 6:15 PM' → 2 screenings on 2026-04-19."""
        palestine = [s for s in afs_screenings if "PALESTINE" in s.title and s.date == "2026-04-19"]
        assert len(palestine) == 2, f"Expected 2 PALESTINE screenings on 2026-04-19, got {len(palestine)}"
        times = {s.time_24h for s in palestine}
        assert times == {"12:30", "18:15"}, f"Wrong times: {times}"

    def test_known_films_present(self, afs_screenings):
        titles = {s.title for s in afs_screenings}
        expected = {
            "MIROIRS NO. 3",
            "PALESTINE '36",
            "WERCKMEISTER HARMONIES",
            "A SERIOUS MAN",
            "AMADEUS",
            "DAYS AND NIGHTS IN THE FOREST",
        }
        missing = expected - titles
        assert not missing, f"Missing expected films: {missing}"


class TestHyperrealOracle:
    def test_parser_yields_expected_entry_count(self, hyperreal_entries):
        assert len(hyperreal_entries) == 22, \
            f"Expected 22 Hyperreal entries in April 2026, got {len(hyperreal_entries)}"

    def test_film_count(self, hyperreal_entries):
        films = films_only(hyperreal_entries)
        assert len(films) >= 14, f"Expected ≥14 Hyperreal films, got {len(films)}"

    def test_all_dates_in_april_2026(self, hyperreal_entries):
        for e in hyperreal_entries:
            assert e.date.startswith("2026-04"), f"Non-April date: {e.date}"

    def test_all_times_are_19_30(self, hyperreal_entries):
        for e in hyperreal_entries:
            assert e.time_24h == "19:30", f"Unexpected time: {e.time_24h}"
            assert e.time_12h == "7:30 PM"

    def test_live_event_detection(self, hyperreal_entries):
        by_title = {e.title: e for e in hyperreal_entries}
        # Positive: these are live events
        for live_title_substr in (
            "PowerPoint Night",
            "Hack the Planet",
            "Ethereal Resurrection",
        ):
            matches = [e for title, e in by_title.items() if live_title_substr in title]
            assert matches, f"Expected a Hyperreal live event matching {live_title_substr!r}"
            for e in matches:
                assert e.is_live_event, f"{e.title} should be is_live_event=True"
        # Negative: regular screenings are not live events
        for film_title in ("The Mummy (1999)", "Burlesque", "Dumb and Dumber"):
            if film_title in by_title:
                assert not by_title[film_title].is_live_event, \
                    f"{film_title} should not be is_live_event"
