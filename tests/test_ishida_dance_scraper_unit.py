"""Unit tests for the ISHIDA Dance Company scraper.

Network is fully mocked: ``scraper.session.get`` is patched to serve saved
HTML fixtures (the company homepage + the two ThunderTix event pages captured
2026-06), so the test runs offline as a unit (``-m "not live"``).

The contracts under test:

* the homepage's ThunderTix links are discovered dynamically (no hard-coded
  event IDs);
* per-show dates/times come from the ThunderTix ``#performances`` table
  (all three Austin shows at 8:00 PM → normalized to 20:00 by ``format_event``);
* the **Houston** stop is filtered out by ``addressLocality`` so only the
  Austin run lands on this Austin-focused calendar;
* every emitted event is ``type=dance`` and survives ``format_event`` /
  ``validate_event`` against the real ``dance`` config template.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List
from unittest.mock import MagicMock

import pytest

from src.config_loader import ConfigLoader
from src.scrapers.ishida_dance_scraper import IshidaDanceScraper

FIXTURE_DIR = Path(__file__).parent / "ishida_test_data"

_URL_TO_FIXTURE = {
    "https://www.ishidadance.org/": "home.html",
    "https://ishida.thundertix.com/events/263899": "thundertix_austin_263899.html",
    "https://ishida.thundertix.com/events/263785": "thundertix_houston_263785.html",
}


def _response(text: str, status: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.text = text
    return resp


@pytest.fixture(autouse=True)
def _no_llm_keys(monkeypatch):
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


@pytest.fixture
def scraper() -> IshidaDanceScraper:
    s = IshidaDanceScraper(config=ConfigLoader(), venue_key="ishida_dance")

    def fake_get(url, *args, **kwargs):
        fixture = _URL_TO_FIXTURE.get(url)
        if fixture is None:
            return _response("", status=404)
        return _response((FIXTURE_DIR / fixture).read_text(encoding="utf-8"))

    s.session.get = MagicMock(side_effect=fake_get)
    return s


@pytest.fixture
def events(scraper: IshidaDanceScraper) -> List[Dict]:
    return scraper.scrape_events()


@pytest.mark.unit
def test_scraper_identity(scraper: IshidaDanceScraper):
    assert scraper.base_url == "https://www.ishidadance.org"
    assert scraper.venue_key == "ishida_dance"
    assert scraper.venue_name == "ISHIDA Dance Company"


@pytest.mark.unit
def test_finds_both_thundertix_links_from_homepage(scraper: IshidaDanceScraper):
    home = (FIXTURE_DIR / "home.html").read_text(encoding="utf-8")
    links = scraper._find_thundertix_links(home)
    assert "https://ishida.thundertix.com/events/263899" in links
    assert "https://ishida.thundertix.com/events/263785" in links


@pytest.mark.unit
def test_only_austin_run_is_returned(events: List[Dict]):
    # Houston (June 11-14, Asia Society Texas Center) must be filtered out.
    assert len(events) == 1
    [event] = events
    assert event["title"] == "waiting / REX"
    assert event["type"] == "dance"
    assert "Dell Fine Arts Center" in event["location"]
    assert event["url"] == "https://ishida.thundertix.com/events/263899"
    # No Houston dates leaked in.
    assert all(d.startswith("2026-06-1") or d == "2026-06-20" for d in event["dates"])
    assert "2026-06-11" not in event["dates"]


@pytest.mark.unit
def test_austin_dates_and_times_parsed_from_performances_table(events: List[Dict]):
    [event] = events
    assert event["dates"] == ["2026-06-18", "2026-06-19", "2026-06-20"]
    assert event["times"] == ["8:00 PM", "8:00 PM", "8:00 PM"]


@pytest.mark.unit
def test_program_description_is_cleaned(events: List[Dict]):
    [event] = events
    assert event["program"]
    assert " " not in event["program"]  # &nbsp; stripped
    assert "Beckett" in event["program"]


@pytest.mark.unit
def test_event_survives_format_and_validate(scraper: IshidaDanceScraper, events):
    [raw] = events
    formatted = scraper.format_event(raw)
    scraper.validate_event(formatted)  # raises ValueError if invalid
    assert formatted["dates"] == ["2026-06-18", "2026-06-19", "2026-06-20"]
    assert formatted["times"] == ["20:00", "20:00", "20:00"]
    assert formatted["event_category"] == "dance"


@pytest.mark.unit
def test_empty_homepage_yields_no_events(scraper: IshidaDanceScraper):
    scraper.session.get = MagicMock(side_effect=lambda url, *a, **k: _response(""))
    assert scraper.scrape_events() == []
