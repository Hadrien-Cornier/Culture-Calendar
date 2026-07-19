"""Unit tests for the Art Austin scraper (Perplexity-based extraction).

Tests the date/time parser, Perplexity response formatting, and event
schema compliance without making live API calls.
"""

from datetime import date
from unittest.mock import Mock

import pytest

from src.scrapers.art_austin_scraper import ArtAustinScraper


@pytest.fixture
def scraper():
    return ArtAustinScraper()


# ---------------------------------------------------------------------------
# Date/time parsing
# ---------------------------------------------------------------------------


class TestParseDateTime:
    def test_basic_range(self, scraper):
        dates, times = scraper._parse_date_time("Saturday, July 18, 2-4 pm")
        assert dates == ["2026-07-18"]
        assert times == ["14:00"]

    def test_evening_range(self, scraper):
        dates, times = scraper._parse_date_time("Friday, July 24, 5-7 pm")
        assert dates == ["2026-07-24"]
        assert times == ["17:00"]

    def test_afternoon_range(self, scraper):
        dates, times = scraper._parse_date_time("Sunday, July 26, 1-4 pm")
        assert dates == ["2026-07-26"]
        assert times == ["13:00"]

    def test_with_year(self, scraper):
        dates, times = scraper._parse_date_time("Sunday, July 26, 2026, 1-4 pm")
        assert dates == ["2026-07-26"]
        assert times == ["13:00"]

    def test_single_time(self, scraper):
        dates, times = scraper._parse_date_time("Sunday, July 19, 2026, 3 pm")
        assert dates == ["2026-07-19"]
        assert times == ["15:00"]

    def test_no_day_of_week(self, scraper):
        dates, times = scraper._parse_date_time("July 18, 6-8 pm")
        assert dates == ["2026-07-18"]
        assert times == ["18:00"]

    def test_en_dash_normalized(self, scraper):
        dates, times = scraper._parse_date_time("Saturday, July 18, 2\u20134 pm")
        assert dates == ["2026-07-18"]
        assert times == ["14:00"]

    def test_date_range_uses_start(self, scraper):
        dates, times = scraper._parse_date_time("July 16, 2026 - September 13, 2026")
        assert dates == ["2026-07-16"]
        assert times == ["10:00"]

    def test_invalid_returns_empty(self, scraper):
        dates, times = scraper._parse_date_time("no date here")
        assert dates == []
        assert times == []

    def test_september_event(self, scraper):
        dates, times = scraper._parse_date_time("Thursday, September 17, 7-9 pm")
        assert dates == ["2026-09-17"]
        assert times == ["19:00"]


# ---------------------------------------------------------------------------
# Perplexity event formatting
# ---------------------------------------------------------------------------


class TestFormatPerplexityEvent:
    def test_basic_event(self, scraper):
        evt = {
            "type": "closing reception",
            "title": "you should eat a burger",
            "date": "Friday, July 24, 5-7 pm",
            "venue": "Unchained.Art Contemporary Gallery",
            "url": "https://artaustin.org/events/",
        }
        result = scraper._format_perplexity_event(evt)
        assert result is not None
        assert "Closing Reception" in result["title"]
        assert result["venue"] == "Unchained.Art Contemporary Gallery"
        assert result["dates"] == ["2026-07-24"]
        assert result["times"] == ["17:00"]
        assert result["type"] == "visual_arts"

    def test_date_str_field(self, scraper):
        """Perplexity may use 'date_str' instead of 'date'."""
        evt = {
            "type": "opening reception",
            "title": "Summer Break",
            "date_str": "Saturday, July 25, 6-8 pm",
            "venue": "Ivester Contemporary",
            "url": "https://example.com",
        }
        result = scraper._format_perplexity_event(evt)
        assert result is not None
        assert result["dates"] == ["2026-07-25"]

    def test_past_event_filtered(self, scraper):
        evt = {
            "type": "",
            "title": "Old Event",
            "date": "Saturday, July 11, 10 am-8 pm",
            "venue": "Blanton Museum",
            "url": "",
        }
        result = scraper._format_perplexity_event(evt)
        assert result is None  # past event

    def test_missing_title_returns_none(self, scraper):
        evt = {"type": "reception", "date": "July 20, 6-8 pm", "venue": "Gallery"}
        assert scraper._format_perplexity_event(evt) is None

    def test_missing_date_returns_none(self, scraper):
        evt = {"type": "reception", "title": "Show", "venue": "Gallery"}
        assert scraper._format_perplexity_event(evt) is None

    def test_unparseable_date_returns_none(self, scraper):
        evt = {"title": "Show", "date": "TBD", "venue": "Gallery"}
        assert scraper._format_perplexity_event(evt) is None

    def test_type_not_duplicated_in_title(self, scraper):
        """If the title already contains the type, don't double it."""
        evt = {
            "type": "exhibition",
            "title": "Exhibition: Red Dot Art Spree",
            "date": "Thursday, September 17, 7-9 pm",
            "venue": "Women & Their Work",
            "url": "",
        }
        result = scraper._format_perplexity_event(evt)
        assert result is not None
        assert result["title"].count("Exhibition") == 1

    def test_default_url_fallback(self, scraper):
        evt = {
            "title": "Show",
            "date": "Saturday, July 25, 6-8 pm",
            "venue": "Gallery",
        }
        result = scraper._format_perplexity_event(evt)
        assert result["url"] == "https://artaustin.org/events/"


# ---------------------------------------------------------------------------
# Scrape integration (mocked LLM)
# ---------------------------------------------------------------------------


class TestScrapeEvents:
    def test_scrape_returns_formatted_events(self, scraper):
        mock_result = {
            "events": [
                {
                    "type": "closing reception",
                    "title": "you should eat a burger",
                    "date": "Friday, July 24, 5-7 pm",
                    "venue": "Unchained.Art",
                    "url": "",
                },
                {
                    "type": "public reception",
                    "title": "Where Memory Becomes Land",
                    "date": "Sunday, July 26, 1-4 pm",
                    "venue": "Central Library Gallery",
                    "url": "",
                },
            ]
        }
        scraper.llm_service = Mock()
        scraper.llm_service.call_perplexity = Mock(return_value=mock_result)

        events = scraper.scrape_events()
        assert len(events) == 2
        assert events[0]["venue"] == "Unchained.Art"
        assert events[1]["venue"] == "Central Library Gallery"

    def test_scrape_handles_empty_response(self, scraper):
        scraper.llm_service = Mock()
        scraper.llm_service.call_perplexity = Mock(return_value={"events": []})
        assert scraper.scrape_events() == []

    def test_scrape_handles_none_response(self, scraper):
        scraper.llm_service = Mock()
        scraper.llm_service.call_perplexity = Mock(return_value=None)
        assert scraper.scrape_events() == []

    def test_scrape_handles_api_error(self, scraper):
        scraper.llm_service = Mock()
        scraper.llm_service.call_perplexity = Mock(side_effect=Exception("API down"))
        assert scraper.scrape_events() == []
