"""Unit tests for the NowPlayingAustin visual-arts scraper."""

from __future__ import annotations

import re
from pathlib import Path
from typing import List

import pytest

from src.scrapers.now_playing_austin_visual_arts_scraper import (
    NowPlayingAustinVisualArtsScraper,
    Occurrence,
)


FIXTURE_DIR = Path(__file__).parent / "now_playing_austin_test_data"
FIXTURE = FIXTURE_DIR / "sample_listing.html"
EMPTY_FIXTURE = FIXTURE_DIR / "empty_listing.html"
SINGLE_FIXTURE = FIXTURE_DIR / "single_event.html"
MULTI_FIXTURE = FIXTURE_DIR / "multi_event_date_variants.html"


def _read_fixture(path: Path) -> str:
    assert path.exists(), f"Missing fixture: {path}"
    return path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def listing_html() -> str:
    return _read_fixture(FIXTURE)


@pytest.fixture(scope="module")
def empty_html() -> str:
    return _read_fixture(EMPTY_FIXTURE)


@pytest.fixture(scope="module")
def single_html() -> str:
    return _read_fixture(SINGLE_FIXTURE)


@pytest.fixture(scope="module")
def multi_html() -> str:
    return _read_fixture(MULTI_FIXTURE)


@pytest.fixture(scope="module")
def scraper() -> NowPlayingAustinVisualArtsScraper:
    return NowPlayingAustinVisualArtsScraper()


@pytest.fixture(scope="module")
def events(
    scraper: NowPlayingAustinVisualArtsScraper, listing_html: str
) -> List[dict]:
    return scraper.parse_listing(listing_html)


@pytest.mark.unit
def test_scraper_initializes_with_expected_identity(
    scraper: NowPlayingAustinVisualArtsScraper,
) -> None:
    assert scraper.base_url == "https://nowplayingaustin.com"
    assert scraper.venue_key == "now_playing_austin_visual_arts"
    assert scraper.get_target_urls() == [
        "https://nowplayingaustin.com/categories/visual-art/"
    ]


@pytest.mark.unit
def test_parse_listing_yields_events(events: List[dict]) -> None:
    assert len(events) > 0, "No events parsed from cached fixture"


@pytest.mark.unit
def test_every_event_is_tagged_visual_arts(events: List[dict]) -> None:
    assert events, "fixture produced zero events"
    for event in events:
        assert event["type"] == "visual_arts"
        assert event["event_category"] == "visual_arts"


@pytest.mark.unit
def test_every_event_has_required_fields(events: List[dict]) -> None:
    required_keys = {"title", "url", "venue", "dates", "times", "type"}
    for event in events:
        missing = required_keys - event.keys()
        assert not missing, f"Event missing fields {missing}: {event}"
        assert event["title"].strip(), f"Empty title: {event}"
        assert event["url"].startswith("https://"), f"Bad url: {event['url']}"


@pytest.mark.unit
def test_dates_and_times_are_parallel_arrays(events: List[dict]) -> None:
    date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    time_pattern = re.compile(r"^\d{2}:\d{2}$")
    for event in events:
        dates = event["dates"]
        times = event["times"]
        assert isinstance(dates, list) and isinstance(times, list)
        assert len(dates) == len(times) > 0, (
            f"dates/times length mismatch or empty: {event}"
        )
        for d in dates:
            assert date_pattern.match(d), f"Bad date format: {d}"
        for t in times:
            assert time_pattern.match(t), f"Bad time format: {t}"


@pytest.mark.unit
def test_known_event_is_extracted(events: List[dict]) -> None:
    """The cached fixture contains 'Build Me A Garden'; assert key fields."""
    target = next(
        (
            e
            for e in events
            if e["title"].startswith("Build Me A Garden")
        ),
        None,
    )
    assert target is not None, "Expected 'Build Me A Garden' event in fixture"
    assert "Dougherty Arts Center" in target["venue"]
    assert target["url"].endswith(
        "/event/build-me-a-garden-from-soil-to-surface-labor-lineage-and-living-materials/"
    )
    # The fixture lists Apr 17 and Apr 18 2026 occurrences.
    assert "2026-04-17" in target["dates"]
    assert "2026-04-18" in target["dates"]


@pytest.mark.unit
def test_parse_show_event_item_24h_conversion(
    scraper: NowPlayingAustinVisualArtsScraper,
) -> None:
    assert scraper._parse_show_event_item(
        "Apr 17, 2026 at 10:00am - 6:00pm  (Fri)"
    ) == Occurrence(date="2026-04-17", time="10:00")
    assert scraper._parse_show_event_item(
        "May 2, 2026 at 6:00pm - 9:00pm  (Sat)"
    ) == Occurrence(date="2026-05-02", time="18:00")
    assert scraper._parse_show_event_item(
        "Dec 31, 2026 at 12:00am - 2:00am  (Thu)"
    ) == Occurrence(date="2026-12-31", time="00:00")
    assert scraper._parse_show_event_item(
        "Jan 1, 2027 at 12:00pm - 1:00pm  (Fri)"
    ) == Occurrence(date="2027-01-01", time="12:00")


@pytest.mark.unit
def test_parse_show_event_item_rejects_garbage(
    scraper: NowPlayingAustinVisualArtsScraper,
) -> None:
    assert scraper._parse_show_event_item("no date here") is None
    assert scraper._parse_show_event_item("") is None


@pytest.mark.unit
def test_parse_listing_skips_anchor_without_title() -> None:
    html = """
    <ul>
      <li>
        <a class="event-slug-on-date" href="https://nowplayingaustin.com/event/foo/">
          <div class="left-event-time">
            <div class="month"><span>Apr</span><span>17</span><span>2026</span></div>
          </div>
        </a>
      </li>
    </ul>
    """
    scraper = NowPlayingAustinVisualArtsScraper()
    events = scraper.parse_listing(html)
    assert events == []


# ---------- Minimal-fixture scenarios ----------


@pytest.mark.unit
def test_parse_listing_with_empty_listing_returns_no_events(
    scraper: NowPlayingAustinVisualArtsScraper, empty_html: str
) -> None:
    # Arrange
    html = empty_html

    # Act
    events = scraper.parse_listing(html)

    # Assert
    assert events == []


@pytest.mark.unit
def test_parse_listing_with_single_event_extracts_expected_fields(
    scraper: NowPlayingAustinVisualArtsScraper, single_html: str
) -> None:
    # Arrange
    html = single_html

    # Act
    events = scraper.parse_listing(html)

    # Assert
    assert len(events) == 1
    event = events[0]
    assert event["title"] == "Solo Single Opening Reception"
    assert event["url"] == (
        "https://nowplayingaustin.com/event/solo-single-opening/"
    )
    assert "Example Gallery" in event["venue"]
    assert event["type"] == "visual_arts"
    assert event["event_category"] == "visual_arts"
    assert event["dates"] == ["2026-05-02"]
    assert event["times"] == ["18:00"]


@pytest.mark.unit
def test_parse_listing_with_multi_event_covers_date_variants(
    scraper: NowPlayingAustinVisualArtsScraper, multi_html: str
) -> None:
    # Arrange
    html = multi_html

    # Act
    events = scraper.parse_listing(html)

    # Assert
    assert len(events) == 3
    by_title = {e["title"]: e for e in events}

    exhibition = by_title["Light and Time Exhibition"]
    assert exhibition["dates"] == ["2026-04-17", "2026-04-18", "2026-04-19"]
    assert exhibition["times"] == ["10:00", "10:00", "12:00"]

    midnight = by_title["Midnight Reception"]
    assert midnight["dates"] == ["2026-12-31"]
    assert midnight["times"] == ["00:00"]

    fallback = by_title["Ongoing Installation"]
    assert fallback["dates"] == ["2026-06-05"]
    assert fallback["times"] == ["00:00"]

    for event in events:
        assert event["type"] == "visual_arts"
        assert event["event_category"] == "visual_arts"
        assert len(event["dates"]) == len(event["times"]) > 0
