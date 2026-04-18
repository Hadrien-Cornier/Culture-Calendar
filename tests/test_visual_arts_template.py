"""Tests for the visual_arts template in master_config.yaml."""

import os

import pytest

from src.config_loader import ConfigLoader


@pytest.fixture(scope="module")
def config() -> ConfigLoader:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(project_root, "config", "master_config.yaml")
    return ConfigLoader(config_path=config_path)


@pytest.fixture(scope="module")
def visual_arts_template(config: ConfigLoader) -> dict:
    return config.get_template("visual_arts")


@pytest.mark.unit
def test_visual_arts_is_in_ontology_labels(config: ConfigLoader) -> None:
    assert "visual_arts" in config.get_allowed_event_categories()


@pytest.mark.unit
def test_visual_arts_template_exists(config: ConfigLoader) -> None:
    templates = config.get_config()["templates"]
    assert "visual_arts" in templates, "visual_arts template missing from templates"


@pytest.mark.unit
def test_visual_arts_grouping_is_unique(visual_arts_template: dict) -> None:
    assert visual_arts_template.get("grouping") == "unique"


@pytest.mark.unit
def test_visual_arts_required_fields(visual_arts_template: dict) -> None:
    required = set(visual_arts_template.get("required_on_publish", []))
    expected = {
        "dates",
        "times",
        "title",
        "venue",
        "url",
        "rating",
        "description",
        "one_liner_summary",
        "screenings",
    }
    missing = expected - required
    assert not missing, f"visual_arts missing required fields: {missing}"


@pytest.mark.unit
def test_visual_arts_optional_fields_declared(visual_arts_template: dict) -> None:
    fields = set(visual_arts_template.get("fields", []))
    for optional_field in ("artist", "artists", "medium", "series"):
        assert optional_field in fields, (
            f"visual_arts template is missing optional field '{optional_field}'"
        )


@pytest.mark.unit
def test_visual_arts_optional_fields_not_required(visual_arts_template: dict) -> None:
    required = set(visual_arts_template.get("required_on_publish", []))
    for optional_field in ("artist", "artists", "medium", "series"):
        assert optional_field not in required, (
            f"'{optional_field}' should be optional, not required_on_publish"
        )


@pytest.mark.unit
def test_visual_arts_screenings_field_definition(visual_arts_template: dict) -> None:
    field_defs = visual_arts_template.get("field_definitions", {})
    assert "screenings" in field_defs, "screenings field_definition missing"
    screenings = field_defs["screenings"]
    assert screenings.get("type") == "array"
    item_schema = screenings.get("item_schema", {})
    required_item_fields = set(item_schema.get("required", []))
    assert {"date", "time", "url", "venue"}.issubset(required_item_fields)


@pytest.mark.unit
def test_visual_arts_grouping_via_helper(config: ConfigLoader) -> None:
    assert config.get_grouping_behavior("visual_arts") == "unique"
    assert config.should_group_by_title("visual_arts") is False


@pytest.mark.unit
def test_visual_arts_artists_field_is_list_type(visual_arts_template: dict) -> None:
    field_defs = visual_arts_template.get("field_definitions", {})
    if "artists" in field_defs:
        assert field_defs["artists"].get("type") == "array", (
            "artists field should be declared as array type"
        )
