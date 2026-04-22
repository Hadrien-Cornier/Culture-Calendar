"""Tests for per-venue address + display_name in master_config.yaml.

T0.1 of long-run 20260422-203219 seeds a street address on every venue so
downstream builders (data.json, api/venues.json, event-shell JSON-LD) can
render street addresses in card faces and schema.org Place blocks instead
of falling back to a generic "Austin, TX" locality.
"""

from __future__ import annotations

import os

import pytest
import yaml


@pytest.fixture(scope="module")
def venues() -> dict:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(project_root, "config", "master_config.yaml")
    with open(config_path, "r", encoding="utf-8") as fh:
        config = yaml.safe_load(fh)
    return config["venues"]


@pytest.mark.unit
def test_every_venue_has_display_name(venues: dict) -> None:
    missing = [key for key, cfg in venues.items() if not cfg.get("display_name")]
    assert not missing, f"Venues missing display_name: {missing}"


@pytest.mark.unit
def test_every_venue_has_address(venues: dict) -> None:
    missing = [key for key, cfg in venues.items() if not cfg.get("address")]
    assert not missing, f"Venues missing address: {missing}"


@pytest.mark.unit
def test_addresses_are_non_empty_strings(venues: dict) -> None:
    for key, cfg in venues.items():
        address = cfg.get("address")
        assert isinstance(address, str), f"{key} address must be a string, got {type(address)!r}"
        assert address.strip(), f"{key} address must not be empty/whitespace"


@pytest.mark.unit
def test_display_names_are_non_empty_strings(venues: dict) -> None:
    for key, cfg in venues.items():
        name = cfg.get("display_name")
        assert isinstance(name, str), f"{key} display_name must be a string, got {type(name)!r}"
        assert name.strip(), f"{key} display_name must not be empty/whitespace"


@pytest.mark.unit
def test_austin_addresses_reference_austin_or_tx(venues: dict) -> None:
    """Sanity check that addresses look like Austin-area locations.

    All venues are Austin cultural institutions, so every address string
    should mention either 'Austin' or 'TX' (the two all-mention aggregators
    that would be acceptable placeholders for region-level venues).
    """
    for key, cfg in venues.items():
        address = cfg["address"]
        assert "Austin" in address or "TX" in address, (
            f"{key} address {address!r} does not reference Austin or TX"
        )
