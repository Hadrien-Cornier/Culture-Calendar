"""Tests for the distribution.buttondown_endpoint key in master_config.yaml."""

import os
import textwrap

import pytest
import yaml

from src.config_loader import ConfigLoader


@pytest.fixture(scope="module")
def config() -> ConfigLoader:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(project_root, "config", "master_config.yaml")
    return ConfigLoader(config_path=config_path)


@pytest.mark.unit
def test_distribution_section_present(config: ConfigLoader) -> None:
    assert "distribution" in config.get_config()


@pytest.mark.unit
def test_buttondown_endpoint_defaults_to_empty_string(config: ConfigLoader) -> None:
    endpoint = config.get_buttondown_endpoint()
    assert isinstance(endpoint, str)
    assert endpoint == ""


@pytest.mark.unit
def test_distribution_config_returns_dict(config: ConfigLoader) -> None:
    distribution = config.get_distribution_config()
    assert isinstance(distribution, dict)
    assert "buttondown_endpoint" in distribution


@pytest.mark.unit
def test_buttondown_endpoint_round_trips(tmp_path) -> None:
    """Write a config with a non-empty endpoint and verify the loader reads it back."""
    sample = textwrap.dedent(
        """
        version: 1
        style:
          field_naming: snake_case
        date_time_spec:
          date_field: dates
          time_field: times
          date_format: "YYYY-MM-DD"
          time_format: "HH:mm"
          zip_rule: pairwise_equal_length
          timezone: local
        ontology:
          labels:
            - movie
            - other
        templates:
          movie:
            grouping: by_title
            fields:
              - title
            required_on_publish:
              - title
          other:
            grouping: unique
            fields:
              - title
            required_on_publish:
              - title
        distribution:
          buttondown_endpoint: "https://buttondown.email/api/emails/embed-subscribe/hadrien"
        venues:
          afs:
            display_name: Austin Film Society
            scrape:
              enabled: true
              frequency: monthly
            classification:
              enabled: false
              assumed_event_category: movie
        """
    ).strip()

    config_file = tmp_path / "sample_master_config.yaml"
    config_file.write_text(sample, encoding="utf-8")

    loader = ConfigLoader(config_path=str(config_file))

    # Round-trip: value that went in comes back out intact.
    expected = "https://buttondown.email/api/emails/embed-subscribe/hadrien"
    assert loader.get_buttondown_endpoint() == expected
    assert loader.get_distribution_config() == {"buttondown_endpoint": expected}

    # Sanity check the raw YAML parse agrees with the loader.
    with open(config_file, "r") as fh:
        raw = yaml.safe_load(fh)
    assert raw["distribution"]["buttondown_endpoint"] == expected


@pytest.mark.unit
def test_buttondown_endpoint_empty_when_section_missing(tmp_path) -> None:
    """Loader returns empty string when the distribution section is absent."""
    sample = textwrap.dedent(
        """
        version: 1
        style:
          field_naming: snake_case
        date_time_spec:
          date_field: dates
          time_field: times
          date_format: "YYYY-MM-DD"
          time_format: "HH:mm"
          zip_rule: pairwise_equal_length
          timezone: local
        ontology:
          labels:
            - movie
        templates:
          movie:
            grouping: by_title
            fields:
              - title
            required_on_publish:
              - title
        venues:
          afs:
            display_name: Austin Film Society
            scrape:
              enabled: true
              frequency: monthly
            classification:
              enabled: false
              assumed_event_category: movie
        """
    ).strip()

    config_file = tmp_path / "sample_no_distribution.yaml"
    config_file.write_text(sample, encoding="utf-8")

    loader = ConfigLoader(config_path=str(config_file))
    assert loader.get_buttondown_endpoint() == ""
    assert loader.get_distribution_config() == {}
