"""Unit tests for the generic config-driven WebLlmScraper.

No network and no LLM calls: the fetch layer and ``llm_service`` are both
stubbed, so these exercise the parts that decide whether a venue's events
survive - schema construction, HTML simplification, time normalization, the
past-event filter, and standardization.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import Mock

import pytest

from src.scrapers._web_llm_scraper import (
    _PIPELINE_DERIVED_FIELDS,
    WebLlmScraper,
    _as_list,
    _normalize_date,
    _normalize_time,
    _split_date_range,
)

# Dates in the fixtures below are anchored to this, never to the real clock.
FROZEN_TODAY = date(2026, 7, 15)


@pytest.fixture(autouse=True)
def _no_llm_keys(monkeypatch):
    """Guarantee no test can reach a live provider."""
    for var in ("PERPLEXITY_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(var, raising=False)


def _make(**overrides) -> WebLlmScraper:
    """Build a scraper with a stub config, matching the static-JSON test style."""
    config = Mock()
    config.get_assumed_event_category.return_value = "visual_arts"
    config.apply_default_values.side_effect = lambda event, _key: event
    config.get_extraction_schema.return_value = {
        "batch_description": "Exhibitions at the test gallery.",
        "fields": {
            "title": {"type": "string", "required": True, "description": "Title."},
            "dates": {"type": "array", "required": True, "description": "Dates."},
            "times": {"type": "array", "required": False, "description": "Times."},
            "end_date": {"type": "string", "required": False, "description": "Close."},
            "venue": {"type": "string", "required": True, "description": "Venue."},
            "rating": {"type": "float", "required": True, "description": "Rating."},
            "description": {"type": "string", "required": True, "description": "Desc."},
        },
    }

    params = dict(
        base_url="https://example-gallery.org",
        venue_name="TestGallery",
        urls=["/exhibitions/"],
        venue_key="test_gallery",
        config=config,
        today=FROZEN_TODAY,
    )
    params.update(overrides)
    return WebLlmScraper(**params)


# ---------------------------------------------------------------------------
# Construction / config validation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestConstruction:
    def test_rejects_unknown_fetch_mode(self):
        with pytest.raises(ValueError, match="Unknown fetch mode"):
            _make(fetch="carrier-pigeon")

    def test_rejects_empty_url_list(self):
        with pytest.raises(ValueError, match="declares no urls"):
            _make(urls=[])

    def test_relative_paths_resolve_against_base_url(self):
        scraper = _make(urls=["/exhibitions/", "/events/"])
        assert scraper.get_target_urls() == [
            "https://example-gallery.org/exhibitions/",
            "https://example-gallery.org/events/",
        ]

    def test_absolute_urls_pass_through(self):
        scraper = _make(urls=["https://other.example/shows"])
        assert scraper.get_target_urls() == ["https://other.example/shows"]


# ---------------------------------------------------------------------------
# Extraction schema
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLlmSchema:
    def test_wraps_fields_in_an_events_array(self):
        schema = _make()._llm_schema()
        assert schema["events"]["type"] == "array"
        assert schema["events"]["description"] == "Exhibitions at the test gallery."
        assert "title" in schema["events"]["items"]

    def test_omits_fields_the_pipeline_generates_later(self):
        """Asking an extractor for a rating invites an invented one."""
        items = _make()._llm_schema()["events"]["items"]
        for field in _PIPELINE_DERIVED_FIELDS:
            assert field not in items, f"{field} must not be asked of the extractor"

    def test_keeps_the_observable_fields(self):
        items = _make()._llm_schema()["events"]["items"]
        assert {"title", "dates", "times", "end_date", "venue"} <= set(items)

    def test_perplexity_prompt_asks_for_the_same_fields(self):
        """The no-fetch mode must not ask for a rating either."""
        scraper = _make(fetch="perplexity")
        prompt = scraper._perplexity_prompt()
        for field in _PIPELINE_DERIVED_FIELDS:
            assert f"- {field}:" not in prompt
        assert "- title:" in prompt and "- dates:" in prompt

    def test_perplexity_prompt_carries_the_venue_guidance(self):
        prompt = _make(fetch="perplexity")._perplexity_prompt()
        assert "Exhibitions at the test gallery." in prompt
        assert "example-gallery.org" in prompt


# ---------------------------------------------------------------------------
# HTML simplification
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSimplifyHtml:
    def test_strips_scripts_and_navigation(self):
        html = """
        <html><body>
          <nav>Home Exhibitions About</nav>
          <script>var tracking = 1;</script>
          <style>.x { color: red }</style>
          <main><h1>Gestures of Care</h1><p>August 14 - September 12, 2026</p></main>
          <footer>Copyright 2026</footer>
        </body></html>
        """
        out = _make()._simplify_html(html)
        assert "Gestures of Care" in out
        assert "August 14" in out
        assert "tracking" not in out
        assert "Copyright" not in out

    def test_truncates_to_the_configured_budget(self):
        html = "<body><main>" + ("word " * 5000) + "</main></body>"
        out = _make(max_content_chars=200)._simplify_html(html)
        assert len(out) <= 203  # budget plus the "..." marker

    def test_empty_html_yields_empty_string(self):
        assert _make()._simplify_html("") == ""


# ---------------------------------------------------------------------------
# Time normalization
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestNormalizeTime:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("18:00", "18:00"),
            ("2:00 PM", "14:00"),
            ("7:00 PM - 10:00 PM", "19:00"),  # range -> start
            ("6-8 pm", "18:00"),  # meridiem trails the range
            ("7pm", "19:00"),
            ("12:00 AM", "00:00"),
            ("12:00 PM", "12:00"),
            ("10 am", "10:00"),
        ],
    )
    def test_normalizes(self, raw, expected):
        assert _normalize_time(raw) == expected

    @pytest.mark.parametrize("raw", [None, "", "TBD", "by appointment", "2026-08-14"])
    def test_rejects_non_times(self, raw):
        """A date must never be read as a time - '2026-08-14' is not 20:00."""
        assert _normalize_time(raw) is None


@pytest.mark.unit
class TestSplitDateRange:
    """Year inference for feeds that print "Fri, Aug 14" and nothing more."""

    @pytest.mark.parametrize(
        "raw,today,expected",
        [
            ("Fri, Aug 14", date(2026, 7, 15), "2026-08-14"),
            ("Sat, Aug 15", date(2026, 8, 10), "2026-08-15"),
            # Read in December, "January 15" means the January that is coming.
            ("January 15", date(2026, 12, 20), "2027-01-15"),
            # Recently past stays put so the finished-event filter can drop it.
            ("July 11", date(2026, 7, 15), "2026-07-11"),
        ],
    )
    def test_infers_a_missing_year(self, raw, today, expected):
        start, _end = _split_date_range(raw, today)
        assert start == expected

    def test_explicit_year_still_wins(self):
        start, end = _split_date_range("July 18 - August 29, 2025", date(2026, 8, 10))
        assert (start, end) == ("2025-07-18", "2025-08-29")

    def test_year_less_range(self):
        start, end = _split_date_range("Aug 14 - Sep 12", date(2026, 8, 10))
        assert (start, end) == ("2026-08-14", "2026-09-12")


@pytest.mark.unit
class TestNormalizeDate:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("2026-08-14", "2026-08-14"),
            ("2022-09", "2022-09-01"),  # month precision -> first of month
            ("2021-04 to 2021-05", "2021-04-01"),  # range -> start
            ("2026-08-14T19:00:00", "2026-08-14"),
        ],
    )
    def test_normalizes(self, raw, expected):
        assert _normalize_date(raw) == expected

    @pytest.mark.parametrize("raw", [None, "", "TBD", "Fall 2026", "2026-13-01", "2026-02-30"])
    def test_rejects_non_dates(self, raw):
        assert _normalize_date(raw) is None


@pytest.mark.unit
class TestAsList:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            (None, []),
            ("2026-08-14", ["2026-08-14"]),
            (["a", "", None, "b"], ["a", "b"]),
            ([], []),
        ],
    )
    def test_coerces(self, raw, expected):
        assert _as_list(raw) == expected


# ---------------------------------------------------------------------------
# Past-event filtering
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHasFinished:
    def test_end_date_decides_for_a_running_exhibition(self):
        """A show that opened in June and closes in August is still on."""
        assert _make()._has_finished(["2026-06-01"], "2026-08-30") is False

    def test_closed_exhibition_is_finished(self):
        assert _make()._has_finished(["2026-03-01"], "2026-05-07") is True

    def test_falls_back_to_latest_date_without_end_date(self):
        assert _make()._has_finished(["2026-07-20"], None) is False
        assert _make()._has_finished(["2026-07-01"], None) is True

    def test_unparseable_date_is_kept(self):
        """Better a stray event than silently dropping a real one."""
        assert _make()._has_finished(["sometime in fall"], None) is False


# ---------------------------------------------------------------------------
# Standardization
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestStandardize:
    URL = "https://example-gallery.org/exhibitions/"

    def test_builds_a_valid_event(self):
        out = _make()._standardize(
            {
                "title": "  Gestures of Care  ",
                "dates": ["2026-08-14"],
                "times": ["7:00 PM - 10:00 PM"],
                "venue": "Some Other Name",
            },
            self.URL,
        )
        assert out["title"] == "Gestures of Care"
        assert out["dates"] == ["2026-08-14"]
        assert out["times"] == ["19:00"]
        assert out["type"] == "visual_arts"
        assert out["url"] == self.URL

    def test_accepts_singular_date_and_time_keys(self):
        """Extractors drift to `date`/`time` even when asked for arrays."""
        out = _make()._standardize(
            {"title": "Artist Talk", "date": "2026-09-05", "time": "2:00 PM"}, self.URL
        )
        assert out["dates"] == ["2026-09-05"]
        assert out["times"] == ["14:00"]
        assert "date" not in out and "time" not in out

    def test_accepts_start_date_for_an_exhibition_run(self):
        """A listing showing a range makes extractors emit start_date/end_date."""
        out = _make()._standardize(
            {
                "title": "2026 Summer Artist-in-Residence",
                "start_date": "2026-09-12",
                "end_date": "2026-10-11",
            },
            self.URL,
        )
        assert out["dates"] == ["2026-09-12"]
        assert "start_date" not in out

    def test_running_exhibition_survives_a_past_start(self):
        """Opened in July, closes in August: still on, must not be dropped."""
        out = _make()._standardize(
            {"title": "Aftertaste", "start_date": "2026-07-18", "end_date": "2026-08-29"},
            self.URL,
        )
        assert out is not None
        assert out["dates"] == ["2026-07-18"]

    def test_range_packed_into_the_dates_field_is_split(self):
        """Extractors often pack the run into `dates` and leave end_date empty.

        Reading only the leading date made a show currently on view look like
        it closed the day it opened.
        """
        out = _make(today=date(2026, 8, 10))._standardize(
            {"title": "Aftertaste", "dates": "2026-07-18 to 2026-08-29"}, self.URL
        )
        assert out is not None
        assert out["dates"] == ["2026-07-18"]
        assert out["end_date"] == "2026-08-29"

    def test_packed_range_that_has_closed_is_still_dropped(self):
        out = _make(today=date(2026, 8, 10))._standardize(
            {"title": "Onely", "dates": "2026-05-09 to 2026-06-06"}, self.URL
        )
        assert out is None

    @pytest.mark.parametrize(
        "raw,start,end",
        [
            ("July 18 - August 29, 2026", "2026-07-18", "2026-08-29"),
            ("June 12-July 11, 2026", "2026-06-12", "2026-07-11"),
            ("September 12, 2026", "2026-09-12", None),
            ("Sep 12 - Oct 11, 2026", "2026-09-12", "2026-10-11"),
            # Crosses New Year, so the end rolls into the following year.
            ("December 12 - January 15, 2026", "2026-12-12", "2027-01-15"),
        ],
    )
    def test_parses_prose_date_ranges(self, raw, start, end):
        """Gallery listings state dates in prose, and extractors copy the page
        rather than honoring the schema's ISO instruction."""
        out = _make(today=date(2026, 1, 1))._standardize(
            {"title": "Show", "dates": raw}, self.URL
        )
        assert out["dates"] == [start]
        assert out.get("end_date") == end

    def test_year_less_upcoming_date_is_kept(self):
        """Event feeds omit the year because it is obvious in context."""
        out = _make(today=date(2026, 8, 10))._standardize(
            {"title": "Sculpture Garden Tour", "dates": "Fri, Aug 14"}, self.URL
        )
        assert out is not None
        assert out["dates"] == ["2026-08-14"]

    def test_finds_dates_under_an_unexpected_key(self):
        """The same page yielded `dates`, then `start_date`, then `run_dates`."""
        out = _make()._standardize(
            {"title": "Aftertaste", "run_dates": "July 18 - August 29, 2026"}, self.URL
        )
        assert out is not None
        assert out["dates"] == ["2026-07-18"]
        assert out["end_date"] == "2026-08-29"

    def test_end_date_is_not_mistaken_for_the_start(self):
        out = _make()._standardize(
            {"title": "Show", "end_date": "2026-09-30"}, self.URL
        )
        assert out is None

    def test_explicit_end_date_wins_over_a_packed_range(self):
        out = _make()._standardize(
            {
                "title": "Show",
                "dates": "2026-07-01 to 2026-07-10",
                "end_date": "2026-09-30",
            },
            self.URL,
        )
        assert out["end_date"] == "2026-09-30"

    def test_pads_missing_times_with_the_venue_default(self):
        out = _make(default_time="10:00")._standardize(
            {"title": "Show", "dates": ["2026-08-14", "2026-08-15"]}, self.URL
        )
        assert out["times"] == ["10:00", "10:00"]

    def test_trims_surplus_times_to_match_dates(self):
        """format_event rejects a dates/times length mismatch outright."""
        out = _make()._standardize(
            {"title": "Show", "dates": ["2026-08-14"], "times": ["18:00", "20:00"]},
            self.URL,
        )
        assert len(out["times"]) == len(out["dates"]) == 1

    def test_stamps_venue_name_by_default(self):
        out = _make()._standardize(
            {"title": "Show", "dates": ["2026-08-14"], "venue": "Wrong"}, self.URL
        )
        assert out["venue"] == "TestGallery"

    def test_preserves_host_venue_when_configured(self):
        """Aggregators and artist pages cover many host galleries."""
        out = _make(preserve_venue_name=True)._standardize(
            {"title": "Show", "dates": ["2026-08-14"], "venue": "MASS Gallery"},
            self.URL,
        )
        assert out["venue"] == "MASS Gallery"

    def test_preserve_falls_back_to_venue_name_when_absent(self):
        out = _make(preserve_venue_name=True)._standardize(
            {"title": "Show", "dates": ["2026-08-14"]}, self.URL
        )
        assert out["venue"] == "TestGallery"

    @pytest.mark.parametrize(
        "event",
        [
            {"dates": ["2026-08-14"]},  # no title
            {"title": "   ", "dates": ["2026-08-14"]},  # blank title
            {"title": "Show"},  # no dates
            {"title": "Show", "dates": []},
            {"title": "Old Show", "dates": ["2025-01-01"]},  # already finished
            {"title": "Archive Show", "dates": ["2022-09"]},  # month-precision past
            {"title": "Archive Range", "dates": ["2021-04 to 2021-05"]},
            {"title": "No parseable date", "dates": ["Fall 2026"]},
        ],
    )
    def test_drops_unusable_events(self, event):
        assert _make()._standardize(event, self.URL) is None

    def test_month_precision_date_becomes_a_full_iso_date(self):
        """validate_event requires YYYY-MM-DD; archives hand back YYYY-MM."""
        out = _make()._standardize({"title": "Show", "dates": ["2026-09"]}, self.URL)
        assert out["dates"] == ["2026-09-01"]

    def test_normalizes_end_date_too(self):
        out = _make()._standardize(
            {"title": "Show", "start_date": "2026-07-18", "end_date": "2026-08"},
            self.URL,
        )
        assert out["end_date"] == "2026-08-01"


# ---------------------------------------------------------------------------
# scrape_events across fetch modes
# ---------------------------------------------------------------------------


def _stub_llm(scraper, events):
    scraper.llm_service = Mock()
    scraper.llm_service.provider = "stub"
    scraper.llm_service.extract_data.return_value = {
        "success": True,
        "data": {"events": events},
    }
    scraper.llm_service.call_perplexity.return_value = {"events": events}
    return scraper


@pytest.mark.unit
class TestScrapeEvents:
    def test_http_mode_fetches_then_extracts(self, monkeypatch):
        scraper = _make()
        monkeypatch.setattr(
            scraper, "_fetch_http", lambda url: "<body><main>listing</main></body>"
        )
        _stub_llm(scraper, [{"title": "Show", "dates": ["2026-08-14"]}])

        events = scraper.scrape_events()
        assert len(events) == 1
        assert events[0]["title"] == "Show"

    def test_perplexity_mode_never_fetches(self, monkeypatch):
        """The 403 escape hatch must not touch the site at all."""
        scraper = _make(fetch="perplexity")

        def _boom(url):
            raise AssertionError("perplexity mode must not fetch the page")

        monkeypatch.setattr(scraper, "_fetch_http", _boom)
        monkeypatch.setattr(scraper, "_render_with_playwright", _boom)
        _stub_llm(scraper, [{"title": "Show", "dates": ["2026-08-14"]}])

        assert len(scraper.scrape_events()) == 1
        assert scraper.llm_service.call_perplexity.called

    def test_playwright_mode_renders(self, monkeypatch):
        scraper = _make(fetch="playwright")
        rendered = []
        monkeypatch.setattr(
            scraper,
            "_render_with_playwright",
            lambda url: rendered.append(url) or "<body><main>x</main></body>",
        )
        _stub_llm(scraper, [{"title": "Show", "dates": ["2026-08-14"]}])

        scraper.scrape_events()
        assert rendered == ["https://example-gallery.org/exhibitions/"]

    def test_dedupes_the_same_show_across_two_listing_pages(self, monkeypatch):
        """One exhibition often appears on both /exhibitions and /events."""
        scraper = _make(urls=["/exhibitions/", "/events/"])
        monkeypatch.setattr(scraper, "_fetch_http", lambda url: "<body><main>x</main></body>")
        _stub_llm(scraper, [{"title": "Show", "dates": ["2026-08-14"]}])

        assert len(scraper.scrape_events()) == 1

    def test_returns_empty_without_a_provider(self, monkeypatch):
        scraper = _make()
        scraper.llm_service = Mock()
        scraper.llm_service.provider = None
        assert scraper.scrape_events() == []

    def test_failed_extraction_yields_no_events(self, monkeypatch):
        scraper = _make()
        monkeypatch.setattr(scraper, "_fetch_http", lambda url: "<body><main>x</main></body>")
        scraper.llm_service = Mock()
        scraper.llm_service.provider = "stub"
        scraper.llm_service.extract_data.return_value = {
            "success": False,
            "error": "JSON parsing error",
        }
        assert scraper.scrape_events() == []

    def test_one_dead_url_does_not_lose_the_other(self, monkeypatch):
        scraper = _make(urls=["/dead/", "/live/"])
        monkeypatch.setattr(
            scraper,
            "_fetch_http",
            lambda url: "" if "dead" in url else "<body><main>x</main></body>",
        )
        _stub_llm(scraper, [{"title": "Show", "dates": ["2026-08-14"]}])
        assert len(scraper.scrape_events()) == 1
