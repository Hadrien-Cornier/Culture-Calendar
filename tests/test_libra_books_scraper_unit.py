"""Unit tests for the Livra Books scraper."""

from __future__ import annotations

import re
from pathlib import Path
from typing import List

import pytest

from src.scrapers.libra_books_scraper import LibraBooksScraper


FIXTURE_DIR = Path(__file__).parent / "libra_books_test_data"
SAMPLE = FIXTURE_DIR / "sample_listing.html"
EMPTY = FIXTURE_DIR / "empty_listing.html"


def _read(path: Path) -> str:
    assert path.exists(), f"Missing fixture: {path}"
    return path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def sample_html() -> str:
    return _read(SAMPLE)


@pytest.fixture(scope="module")
def empty_html() -> str:
    return _read(EMPTY)


@pytest.fixture(scope="module")
def scraper() -> LibraBooksScraper:
    return LibraBooksScraper()


@pytest.fixture(scope="module")
def events(scraper: LibraBooksScraper, sample_html: str) -> List[dict]:
    return scraper.parse_listing(sample_html)


@pytest.mark.unit
def test_scraper_identity(scraper: LibraBooksScraper) -> None:
    assert scraper.base_url == "https://www.livrabooks.com"
    assert scraper.venue_key == "libra_books"
    assert scraper.venue_name == "Livra Books"
    assert scraper.get_target_urls() == ["https://www.livrabooks.com/events"]


@pytest.mark.unit
def test_parse_listing_yields_events(events: List[dict]) -> None:
    assert len(events) == 4, f"expected 4 fixture events, got {len(events)}"


@pytest.mark.unit
def test_every_event_has_required_fields(events: List[dict]) -> None:
    required = {"title", "url", "venue", "dates", "times", "type", "description"}
    for event in events:
        missing = required - event.keys()
        assert not missing, f"missing {missing} in {event}"
        assert event["title"].strip(), f"empty title: {event}"
        assert event["url"].startswith("https://www.livrabooks.com/events/"), event["url"]
        assert event["venue"] == "Livra Books"


@pytest.mark.unit
def test_dates_and_times_are_parallel_arrays(events: List[dict]) -> None:
    date_re = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    time_re = re.compile(r"^\d{2}:\d{2}$")
    for event in events:
        assert isinstance(event["dates"], list)
        assert isinstance(event["times"], list)
        assert len(event["dates"]) == len(event["times"]) == 1
        assert date_re.match(event["dates"][0]), event["dates"]
        assert time_re.match(event["times"][0]), event["times"]


@pytest.mark.unit
def test_book_club_event_is_classified_as_book_club(events: List[dict]) -> None:
    dracula = next(
        (e for e in events if "Dracula" in e["title"]), None
    )
    assert dracula is not None
    assert dracula["type"] == "book_club"
    assert dracula["dates"] == ["2025-11-02"]
    assert dracula["times"] == ["19:00"]
    assert dracula["series"] == "Livra Book Club"
    assert "outdoor bookclub" in dracula["description"].lower()


@pytest.mark.unit
def test_pop_up_event_is_classified_as_other(events: List[dict]) -> None:
    popup = next(
        (e for e in events if e["title"].lower().startswith("pop-up")), None
    )
    assert popup is not None
    assert popup["type"] == "other"
    assert popup["dates"] == ["2025-10-18"]
    assert popup["times"] == ["10:00"]
    assert "series" not in popup


@pytest.mark.unit
def test_theory_night_event_is_classified_as_other(events: List[dict]) -> None:
    theory = next(
        (e for e in events if "THEORY NIGHT" in e["title"]), None
    )
    assert theory is not None
    assert theory["type"] == "other"
    assert theory["dates"] == ["2026-03-17"]
    assert theory["times"] == ["19:00"]


@pytest.mark.unit
def test_nature_book_club_without_description(events: List[dict]) -> None:
    nature = next(
        (e for e in events if e["title"] == "Livra Nature Book Club"), None
    )
    assert nature is not None
    assert nature["type"] == "book_club"
    assert nature["description"] == ""
    assert nature["series"] == "Livra Nature Book Club"


@pytest.mark.unit
def test_empty_listing_returns_no_events(
    scraper: LibraBooksScraper, empty_html: str
) -> None:
    assert scraper.parse_listing(empty_html) == []


@pytest.mark.unit
def test_parse_listing_skips_event_without_date(scraper: LibraBooksScraper) -> None:
    html = """
    <div class="eventlist eventlist--upcoming">
      <article class="eventlist-event">
        <div class="eventlist-column-info">
          <h1 class="eventlist-title">
            <a href="/events/no-date" class="eventlist-title-link">No Date Event</a>
          </h1>
          <ul class="eventlist-meta event-meta"></ul>
        </div>
      </article>
    </div>
    """
    assert scraper.parse_listing(html) == []


@pytest.mark.unit
def test_parse_listing_skips_event_without_title(scraper: LibraBooksScraper) -> None:
    html = """
    <div class="eventlist eventlist--upcoming">
      <article class="eventlist-event">
        <div class="eventlist-column-info">
          <ul class="eventlist-meta event-meta">
            <li><time class="event-date" datetime="2026-05-01">May 1, 2026</time></li>
            <li><time class="event-time-localized-start">7:00 PM</time></li>
          </ul>
        </div>
      </article>
    </div>
    """
    assert scraper.parse_listing(html) == []


@pytest.mark.unit
def test_normalize_time_covers_common_formats(
    scraper: LibraBooksScraper,
) -> None:
    assert scraper._normalize_time("7:00 PM") == "19:00"
    assert scraper._normalize_time("10:00 AM") == "10:00"
    assert scraper._normalize_time("12:00 AM") == "00:00"
    assert scraper._normalize_time("12:00 PM") == "12:00"
    assert scraper._normalize_time("not a time") is None


@pytest.mark.unit
def test_parse_long_date_fallback(scraper: LibraBooksScraper) -> None:
    assert scraper._parse_long_date("Tuesday, March 17, 2026") == "2026-03-17"
    assert scraper._parse_long_date("March 17, 2026") == "2026-03-17"
    assert scraper._parse_long_date("not a date") is None


@pytest.mark.unit
def test_absolute_url_is_preserved(scraper: LibraBooksScraper) -> None:
    html = """
    <div class="eventlist eventlist--upcoming">
      <article class="eventlist-event">
        <div class="eventlist-column-info">
          <h1 class="eventlist-title">
            <a href="https://other.example.com/events/abs"
               class="eventlist-title-link">Absolute Link</a>
          </h1>
          <ul class="eventlist-meta event-meta">
            <li><time class="event-date" datetime="2026-05-01">May 1, 2026</time></li>
            <li><time class="event-time-localized-start">7:00 PM</time></li>
          </ul>
        </div>
      </article>
    </div>
    """
    events = scraper.parse_listing(html)
    assert len(events) == 1
    assert events[0]["url"] == "https://other.example.com/events/abs"
