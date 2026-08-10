"""Invariants for the config-driven scraper registries.

These are deliberately written against the config rather than a fixed list of
venues, so a venue added tomorrow is covered without touching this file. That
is the whole point of the registries: adding a venue is a YAML edit, and these
tests are what keep a malformed YAML edit from reaching the pipeline.
"""

from __future__ import annotations

import os

import pytest
import yaml

from src.config_loader import build_venue_code_map
from src.scrapers._web_llm_scraper import FETCH_MODES


@pytest.fixture(scope="module")
def config() -> dict:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "config", "master_config.yaml"), encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@pytest.fixture(scope="module")
def web_scrapers(config: dict) -> dict:
    return config.get("web_llm_scrapers", {})


@pytest.mark.unit
def test_registry_is_not_empty(web_scrapers: dict) -> None:
    assert web_scrapers, "web_llm_scrapers registry should not be empty"


@pytest.mark.unit
def test_every_registry_entry_has_a_venues_entry(web_scrapers: dict, config: dict) -> None:
    """Without this the scraper cannot resolve its category, address, or policy."""
    venues = config["venues"]
    missing = [key for key in web_scrapers if key not in venues]
    assert not missing, f"web_llm_scrapers keys with no venues: entry: {missing}"


@pytest.mark.unit
def test_required_registry_fields_present(web_scrapers: dict) -> None:
    for key, entry in web_scrapers.items():
        for field in ("base_url", "venue_name", "urls"):
            assert entry.get(field), f"{key} is missing required field {field!r}"
        assert isinstance(entry["urls"], list) and entry["urls"], f"{key} urls must be a non-empty list"


@pytest.mark.unit
def test_fetch_modes_are_known(web_scrapers: dict) -> None:
    for key, entry in web_scrapers.items():
        mode = entry.get("fetch", "http")
        assert mode in FETCH_MODES, f"{key} declares unknown fetch mode {mode!r}"


@pytest.mark.unit
def test_base_urls_are_absolute(web_scrapers: dict) -> None:
    for key, entry in web_scrapers.items():
        assert entry["base_url"].startswith(("http://", "https://")), (
            f"{key} base_url must be absolute, got {entry['base_url']!r}"
        )


@pytest.mark.unit
def test_event_types_are_in_the_ontology(web_scrapers: dict, config: dict) -> None:
    allowed = set(config["ontology"]["labels"])
    for key, entry in web_scrapers.items():
        event_type = entry.get("default_event_type", "visual_arts")
        assert event_type in allowed, f"{key} default_event_type {event_type!r} not in ontology"


@pytest.mark.unit
def test_venue_names_are_unique_across_registries(config: dict) -> None:
    """venue_name doubles as the venue code, so a collision would merge venues."""
    seen: dict[str, str] = {}
    for block in ("static_json_scrapers", "web_llm_scrapers"):
        for key, entry in (config.get(block) or {}).items():
            name = entry.get("venue_name")
            assert name not in seen, f"venue_name {name!r} used by both {seen.get(name)} and {key}"
            seen[name] = key


@pytest.mark.unit
def test_every_registry_venue_resolves_through_the_code_map(config: dict) -> None:
    """Regression: the two hardcoded copies of this map both lost venues,
    shipping those events with an empty venue_address."""
    code_map = build_venue_code_map(config)
    for block in ("static_json_scrapers", "web_llm_scrapers"):
        for key, entry in (config.get(block) or {}).items():
            code = entry["venue_name"]
            assert code_map.get(code) == key, f"{code!r} does not map back to {key!r}"


@pytest.mark.unit
def test_code_map_aliases_point_at_real_venues(config: dict) -> None:
    venues = config["venues"]
    for code, key in build_venue_code_map(config).items():
        assert key in venues, f"venue code {code!r} maps to unknown venue key {key!r}"


@pytest.mark.unit
def test_previously_missing_venues_are_covered(config: dict) -> None:
    """ArtAustin and IshidaDance were absent from both hardcoded copies."""
    code_map = build_venue_code_map(config)
    assert code_map.get("ArtAustin") == "artaustin"
    assert code_map.get("IshidaDance") == "ishida_dance"


@pytest.mark.unit
def test_visual_arts_template_defines_every_field_it_lists(config: dict) -> None:
    """`fields` without a matching `field_definitions` entry is invisible to
    get_extraction_schema - which is how every extracted exhibition arrived
    undated."""
    template = config["templates"]["visual_arts"]
    listed = set(template["fields"])
    defined = set(template["field_definitions"])
    assert not (listed - defined), f"visual_arts fields with no definition: {sorted(listed - defined)}"


@pytest.mark.unit
def test_visual_arts_template_can_express_an_exhibition_run(config: dict) -> None:
    definitions = config["templates"]["visual_arts"]["field_definitions"]
    for field in ("dates", "times", "end_date"):
        assert field in definitions, f"visual_arts must define {field!r}"
