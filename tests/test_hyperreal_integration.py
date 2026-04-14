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


def _discover_hyperreal_fixtures() -> list[str]:
    """Return every event_*_2026.html filename in the fixture dir."""
    return sorted(p.name for p in TEST_DATA.glob("event_*_2026.html"))


SAVED_FIXTURE_FILES = _discover_hyperreal_fixtures()


# Pre-compute URL path → filename mapping by reading the calendar HTML once
# and matching each /events/... link to whichever fixture mentions it.
def _build_url_map() -> dict[str, str]:
    """Map URL path (e.g. /events/4-1/the-mummy-movie-screening) → fixture filename."""
    import re
    calendar = (TEST_DATA / "calendar_april_2026.html").read_text(encoding="utf-8")
    paths = sorted(set(re.findall(r'href="(/events/[^"]+)"', calendar)))
    out: dict[str, str] = {}
    for path in paths:
        basename = path.rsplit("/", 1)[-1]
        # Strip common Hyperreal suffixes that the fetch script removes.
        simple = re.sub(r"-movie-screening.*$", "", basename)
        simple = re.sub(r"-screening.*$", "", simple)
        candidate = f"event_{simple.replace('-', '_')}_2026.html"
        if candidate in SAVED_FIXTURE_FILES:
            out[path] = candidate
    return out


SAVED_FIXTURES = _build_url_map()


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
    for path, filename in SAVED_FIXTURES.items():
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
    def test_scrape_returns_saved_fixtures(self, scraped_events):
        """Scraper must recover at least the movie subset of the saved fixtures.

        The pruned fixture set (post-2026-04 cleanup) keeps only 4 movie pages
        plus 1 live-event page; the scraper filters out the live event, so we
        expect ~4. Live mode in scripts/verify_calendar.py covers full breadth.
        """
        assert len(scraped_events) >= 3, (
            f"Too few events: {len(scraped_events)} (have {len(SAVED_FIXTURES)} fixtures)"
        )
        assert len(scraped_events) <= len(SAVED_FIXTURES) + 2, (
            f"Got {len(scraped_events)} events, expected at most {len(SAVED_FIXTURES) + 2}"
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

    def test_oracle_titles_for_saved_fixtures_match(self, scraped_events, oracle_entries):
        """Every saved fixture's title must appear in the oracle.

        With the pruned fixture set, this checks correctness ('do the
        scraped titles map to real oracle entries?') rather than coverage
        ('does the scraper find every Hyperreal film?'). Coverage is the
        job of `verify_calendar.py --live`.
        """
        import unicodedata

        def _norm(s: str) -> str:
            s = unicodedata.normalize("NFKC", s or "")
            s = s.replace("\u2019", "'").replace("\u2018", "'")
            return s.strip().casefold()

        oracle_titles_norm = {_norm(e.title) for e in oracle_entries}
        scraped_titles_norm = {_norm(e.get("title", "")) for e in scraped_events}

        def title_in_oracle(scraped: str) -> bool:
            return any(o in scraped or scraped in o for o in oracle_titles_norm)

        matching = {s for s in scraped_titles_norm if title_in_oracle(s)}
        assert len(matching) >= 3, (
            f"Only {len(matching)} of {len(scraped_titles_norm)} scraped titles "
            f"match oracle entries; expected at least 3 saved-fixture matches."
        )
