"""Unit tests for ``src/scrapers/_static_json_scraper.py``.

The class is the future home for the five classical-music scrapers and
Ballet Austin (task-6.6b will migrate them). The two contracts the
council and the migration depend on are:

1. The event ``type`` is never baked into Python — it comes from the
   source JSON, the venue's ``master_config.yaml`` policy, or a
   constructor default, in that order. (Direct regression guard for
   the Ballet Austin ``type=concert`` bug from task-2.1.)
2. Both per-date fan-out (Ballet / Opera / Early Music / La Follia /
   Chamber Music) and arrays-preserved (Austin Symphony) layouts are
   supported via ``expand_dates``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

import pytest

from src.scrapers._static_json_scraper import StaticJsonScraper


@pytest.fixture(autouse=True)
def _no_llm_keys(monkeypatch):
    """BaseScraper tolerates missing API keys with a printed warning."""
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def _write_json(path: Path, payload: Dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _make(
    tmp_path: Path,
    *,
    payload: Dict,
    top_level_key: str,
    default_event_type: str,
    venue_key: str = "test_venue",
    default_time: str = "7:30 PM",
    default_location: str = "Test Hall",
    expand_dates: bool = True,
    config=None,
    file_name: str = "data.json",
) -> StaticJsonScraper:
    data_file = _write_json(tmp_path / file_name, payload)
    return StaticJsonScraper(
        base_url="https://example.test",
        venue_name="TestVenue",
        data_file=str(data_file),
        top_level_key=top_level_key,
        default_event_type=default_event_type,
        venue_key=venue_key,
        default_time=default_time,
        default_location=default_location,
        expand_dates=expand_dates,
        config=config,
    )


# ---------------------------------------------------------------------------
# Type resolution ladder — the contract that pinned the bug from task-2.1.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_per_event_type_in_source_json_wins(tmp_path: Path):
    """Tier 1: when the JSON event carries ``type``, it is authoritative."""
    payload = {
        "things": [
            {"title": "T", "dates": ["2026-09-01"], "times": ["19:30"], "type": "opera"}
        ]
    }
    scraper = _make(
        tmp_path,
        payload=payload,
        top_level_key="things",
        default_event_type="concert",
    )
    [event] = scraper.scrape_events()
    assert event["type"] == "opera"


@pytest.mark.unit
def test_falls_back_to_venue_config_when_event_type_missing(tmp_path: Path):
    """Tier 2: per-event ``type`` absent → venue config supplies it."""

    class FakeConfig:
        def get_assumed_event_category(self, venue_key):
            assert venue_key == "ballet_austin"
            return "dance"

    payload = {"things": [{"title": "T", "dates": ["2026-09-01"], "times": ["19:30"]}]}
    scraper = _make(
        tmp_path,
        payload=payload,
        top_level_key="things",
        default_event_type="concert",
        venue_key="ballet_austin",
        config=FakeConfig(),
    )
    [event] = scraper.scrape_events()
    assert event["type"] == "dance"


@pytest.mark.unit
def test_falls_back_to_constructor_default_when_no_config(tmp_path: Path):
    """Tier 3: nothing else available → ``default_event_type`` wins."""
    payload = {"things": [{"title": "T", "dates": ["2026-09-01"], "times": ["19:30"]}]}
    scraper = _make(
        tmp_path,
        payload=payload,
        top_level_key="things",
        default_event_type="concert",
        config=None,
    )
    [event] = scraper.scrape_events()
    assert event["type"] == "concert"


@pytest.mark.unit
def test_dance_venue_never_emits_concert(tmp_path: Path):
    """Direct regression for the original Ballet Austin bug.

    A venue declared ``assumed_event_category: dance`` in
    ``master_config.yaml`` whose JSON omits per-event ``type`` must
    never produce ``type=concert``, no matter what the constructor
    default is.
    """

    class DanceConfig:
        def get_assumed_event_category(self, venue_key):
            return "dance"

    payload = {
        "balletAustin": [
            {
                "title": "GRIMM TALES",
                "program": "Reimagined fairy tales",
                "dates": ["2026-09-26", "2026-09-27"],
                "times": ["7:30 PM", "3:00 PM"],
            }
        ]
    }
    scraper = _make(
        tmp_path,
        payload=payload,
        top_level_key="balletAustin",
        default_event_type="concert",  # deliberately wrong default
        venue_key="ballet_austin",
        config=DanceConfig(),
    )
    events = scraper.scrape_events()
    types = {e["type"] for e in events}
    assert types == {"dance"}
    assert "concert" not in types


@pytest.mark.unit
def test_per_event_type_overrides_venue_config(tmp_path: Path):
    """Tier 1 beats Tier 2 — concrete JSON overrides the venue default."""

    class ConcertConfig:
        def get_assumed_event_category(self, venue_key):
            return "concert"

    payload = {"things": [{"title": "T", "dates": ["2026-09-01"], "type": "opera"}]}
    scraper = _make(
        tmp_path,
        payload=payload,
        top_level_key="things",
        default_event_type="concert",
        config=ConcertConfig(),
    )
    [event] = scraper.scrape_events()
    assert event["type"] == "opera"


# ---------------------------------------------------------------------------
# Layout: expand_dates — per-date fan-out (Ballet / Opera / Early Music…).
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_expand_dates_fans_each_date_into_its_own_event(tmp_path: Path):
    payload = {
        "things": [
            {
                "title": "Run",
                "dates": ["2026-09-26", "2026-09-27"],
                "times": ["7:30 PM", "3:00 PM"],
            }
        ]
    }
    scraper = _make(
        tmp_path, payload=payload, top_level_key="things", default_event_type="dance"
    )
    events = scraper.scrape_events()
    assert [e["date"] for e in events] == ["2026-09-26", "2026-09-27"]
    assert [e["time"] for e in events] == ["7:30 PM", "3:00 PM"]
    # Arrays must NOT be exposed in expand-dates mode — downstream code
    # branches on the presence of ``date`` vs ``dates``.
    assert "dates" not in events[0]
    assert "times" not in events[0]


@pytest.mark.unit
def test_expand_dates_pads_missing_times_with_default(tmp_path: Path):
    payload = {"things": [{"title": "T", "dates": ["2026-09-26", "2026-09-27"]}]}
    scraper = _make(
        tmp_path,
        payload=payload,
        top_level_key="things",
        default_event_type="dance",
        default_time="8:00 PM",
    )
    events = scraper.scrape_events()
    assert [e["time"] for e in events] == ["8:00 PM", "8:00 PM"]


@pytest.mark.unit
def test_expand_dates_reuses_first_time_when_one_provided(tmp_path: Path):
    payload = {
        "things": [
            {"title": "T", "dates": ["2026-09-26", "2026-09-27"], "times": ["7:30 PM"]}
        ]
    }
    scraper = _make(
        tmp_path, payload=payload, top_level_key="things", default_event_type="dance"
    )
    events = scraper.scrape_events()
    assert [e["time"] for e in events] == ["7:30 PM", "7:30 PM"]


# ---------------------------------------------------------------------------
# Layout: arrays preserved (Austin Symphony pattern).
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_expand_dates_false_preserves_dates_and_times_arrays(tmp_path: Path):
    payload = {
        "austinSymphony": [
            {
                "title": "Masterworks 1",
                "dates": ["2026-09-12", "2026-09-13"],
                "times": ["8:00 PM", "8:00 PM"],
                "type": "concert",
            }
        ]
    }
    scraper = _make(
        tmp_path,
        payload=payload,
        top_level_key="austinSymphony",
        default_event_type="concert",
        expand_dates=False,
    )
    [event] = scraper.scrape_events()
    assert event["dates"] == ["2026-09-12", "2026-09-13"]
    assert event["times"] == ["8:00 PM", "8:00 PM"]
    # Scalar ``date`` / ``time`` must NOT be added — Symphony's pipeline
    # iterates the arrays itself.
    assert "date" not in event
    assert "time" not in event


@pytest.mark.unit
def test_expand_dates_false_pads_missing_times_array(tmp_path: Path):
    payload = {
        "austinSymphony": [{"title": "T", "dates": ["2026-09-12", "2026-09-13"]}]
    }
    scraper = _make(
        tmp_path,
        payload=payload,
        top_level_key="austinSymphony",
        default_event_type="concert",
        default_time="8:00 PM",
        expand_dates=False,
    )
    [event] = scraper.scrape_events()
    assert event["times"] == ["8:00 PM", "8:00 PM"]


# ---------------------------------------------------------------------------
# Standardized field shape — what migration target depends on.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_standard_fields_carry_through(tmp_path: Path):
    payload = {
        "things": [
            {
                "title": "Masterworks 1: Stefan Jackiw",
                "program": "Ortiz | Prokofiev | Saint-Saëns",
                "featured_artist": "Stefan Jackiw (violin)",
                "composers": ["Gabriela Ortiz", "Sergei Prokofiev"],
                "works": ["Kauyumari", "Violin Concerto No. 2"],
                "series": "Masterworks",
                "venue_name": "Dell Hall at Long Center",
                "dates": ["2026-09-12"],
                "times": ["8:00 PM"],
            }
        ]
    }
    scraper = _make(
        tmp_path,
        payload=payload,
        top_level_key="things",
        default_event_type="concert",
        default_location="DEFAULT FALLBACK",
    )
    [event] = scraper.scrape_events()
    assert event["title"] == "Masterworks 1: Stefan Jackiw"
    assert event["program"] == "Ortiz | Prokofiev | Saint-Saëns"
    assert event["featured_artist"] == "Stefan Jackiw (violin)"
    assert event["composers"] == ["Gabriela Ortiz", "Sergei Prokofiev"]
    assert event["works"] == ["Kauyumari", "Violin Concerto No. 2"]
    assert event["series"] == "Masterworks"
    assert event["venue"] == "TestVenue"
    assert event["location"] == "Dell Hall at Long Center"
    assert event["url"] == "https://example.test"


@pytest.mark.unit
def test_default_location_used_when_venue_name_absent(tmp_path: Path):
    payload = {"things": [{"title": "T", "dates": ["2026-09-12"], "times": ["8:00 PM"]}]}
    scraper = _make(
        tmp_path,
        payload=payload,
        top_level_key="things",
        default_event_type="concert",
        default_location="The Long Center",
    )
    [event] = scraper.scrape_events()
    assert event["location"] == "The Long Center"


# ---------------------------------------------------------------------------
# Graceful failure — match the existing per-venue scraper behaviour.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_missing_data_file_returns_empty_list(tmp_path: Path):
    scraper = StaticJsonScraper(
        base_url="https://example.test",
        venue_name="TestVenue",
        data_file=str(tmp_path / "does_not_exist.json"),
        top_level_key="things",
        default_event_type="concert",
    )
    assert scraper.scrape_events() == []


@pytest.mark.unit
def test_malformed_json_returns_empty_list(tmp_path: Path):
    bad = tmp_path / "broken.json"
    bad.write_text("{not valid json", encoding="utf-8")
    scraper = StaticJsonScraper(
        base_url="https://example.test",
        venue_name="TestVenue",
        data_file=str(bad),
        top_level_key="things",
        default_event_type="concert",
    )
    assert scraper.scrape_events() == []


@pytest.mark.unit
def test_missing_top_level_key_returns_empty_list(tmp_path: Path):
    payload = {"some_other_key": [{"title": "T"}]}
    scraper = _make(
        tmp_path, payload=payload, top_level_key="things", default_event_type="concert"
    )
    assert scraper.scrape_events() == []


@pytest.mark.unit
def test_event_with_no_dates_yields_no_events_in_expand_mode(tmp_path: Path):
    """Without dates there is nothing to fan out — silently skip."""
    payload = {"things": [{"title": "T"}]}
    scraper = _make(
        tmp_path, payload=payload, top_level_key="things", default_event_type="concert"
    )
    assert scraper.scrape_events() == []


@pytest.mark.unit
def test_get_target_urls_is_empty(tmp_path: Path):
    """Static-JSON scrapers never hit the network — empty URL list."""
    payload = {"things": []}
    scraper = _make(
        tmp_path, payload=payload, top_level_key="things", default_event_type="concert"
    )
    assert scraper.get_target_urls() == []
