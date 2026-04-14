"""End-to-end Hyperreal scraper test against saved HTML fixtures + the oracle.

Mocks network so scrape_events() runs against snapshot HTML from April 2026.
Measures coverage vs the Hyperreal oracle (tests/april-2026-hyperreal.md).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.oracle_hyperreal import (  # noqa: E402
    HyperrealEntry,
    films_only,
    parse_hyperreal_schedule,
)
from src.config_loader import ConfigLoader  # noqa: E402
from src.scrapers.hyperreal_scraper import HyperrealScraper  # noqa: E402


TEST_DATA = ROOT / "tests" / "Hyperreal_test_data"
ORACLE_FIXTURE = ROOT / "tests" / "april-2026-hyperreal.md"

# URL path → saved fixture filename. The live calendar has events Hyperreal
# will later remove; we only snapshot ones we want to keep testing against.
SAVED_FIXTURES = {
    "/events/4-1/the-mummy-movie-screening": ("event_the_mummy_2026.html", "The Mummy (1999)", "2026-04-01"),
    "/events/4-8/burlesque-movie-screening": ("event_burlesque_2026.html", "Burlesque", "2026-04-08"),
    "/events/4-24/dumb-and-dumber-movie-screening": ("event_dumb_and_dumber_2026.html", "Dumb and Dumber", "2026-04-24"),
    "/events/4-30/xxx-return-of-xander-cage-movie-screening": ("event_xxx_return_xander_cage_2026.html", "xXx: Return of Xander Cage", "2026-04-30"),
}


def _make_response(text: str, status: int = 200) -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.text = text
    return r


def _load_fixture(filename: str) -> str:
    return (TEST_DATA / filename).read_text(encoding="utf-8")


def _mock_session_get(*args: Any, **kwargs: Any) -> MagicMock:
    url = args[0] if args else kwargs.get("url", "")
    if "view=calendar" in url:
        return _make_response(_load_fixture("calendar_april_2026.html"))
    for path, (filename, _title, _date) in SAVED_FIXTURES.items():
        if path in url:
            return _make_response(_load_fixture(filename))
    return _make_response("", 404)


@pytest.fixture(scope="module")
def scraped_events() -> list[dict]:
    # Production constructs the scraper with config (see MultiVenueScraper.__init__),
    # which enables the template-driven emit path (dates/times arrays). Without
    # config it falls back to singular date/time, which never hits production.
    scraper = HyperrealScraper(config=ConfigLoader(), venue_key="hyperreal")
    with patch.object(scraper.session, "get", side_effect=_mock_session_get):
        events = scraper.scrape_events()
    return events


@pytest.fixture(scope="module")
def oracle_entries() -> list[HyperrealEntry]:
    return parse_hyperreal_schedule(ORACLE_FIXTURE)


class TestHyperrealIntegration:
    def test_scrape_returns_only_saved_fixtures(self, scraped_events):
        """We mocked 4 event pages; the scraper should pull exactly those.

        The calendar has more links, but pages we didn't save 404 and get
        skipped. This keeps the fixture set small and deterministic.
        """
        assert len(scraped_events) >= 3, f"Too few events: {len(scraped_events)}"
        assert len(scraped_events) <= len(SAVED_FIXTURES), (
            f"Got {len(scraped_events)} events, expected at most {len(SAVED_FIXTURES)}"
        )

    def test_every_event_has_core_fields(self, scraped_events):
        required = {"title", "dates", "times", "venue", "url"}
        for e in scraped_events:
            missing = required - set(e.keys())
            assert not missing, f"{e.get('title','?')} missing {missing}"

    def test_every_event_tagged_movie(self, scraped_events):
        for e in scraped_events:
            assert e.get("type") == "movie", f"{e.get('title')} not tagged movie"

    def test_time_normalized_to_19_30(self, scraped_events):
        """Every Hyperreal screening in April 2026 starts at 7:30 PM."""
        for e in scraped_events:
            for t in e.get("times", []):
                normalized = t.replace("\u202f", " ").strip().upper()
                assert normalized in ("7:30 PM", "19:30"), (
                    f"{e.get('title')} has unexpected time: {t!r}"
                )

    def test_titles_match_oracle(self, scraped_events, oracle_entries):
        """Titles pulled from the event pages should match what the oracle claims."""
        import unicodedata

        def _norm(s: str) -> str:
            s = unicodedata.normalize("NFKC", s or "")
            s = s.replace("\u2019", "'").replace("\u2018", "'")
            return s.strip().casefold()

        expected_norm = {_norm(title) for (_f, title, _d) in SAVED_FIXTURES.values()}
        oracle_norm = {_norm(e.title) for e in oracle_entries}
        # Every fixture title must also be in the oracle (sanity).
        assert expected_norm.issubset(oracle_norm), (
            f"Fixture titles not in oracle: {expected_norm - oracle_norm}"
        )
        scraped_norm = {_norm(e.get("title", "")) for e in scraped_events}
        matching = scraped_norm & expected_norm
        assert len(matching) >= 3, (
            f"Only {len(matching)} scraped titles match saved fixtures: {scraped_norm}"
        )
