"""The feature inventory must actually parse.

CLAUDE.md makes config/feature-inventory.json the canonical list of
user-visible features, appended to before every UI change and asserted against
the live site by the continuity persona. None of that works if the file is not
valid JSON - and it silently was not: a stray "}," sat mid-file through many
commits because nothing in the suite ever loaded it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

INVENTORY_PATH = Path(__file__).resolve().parents[1] / "config" / "feature-inventory.json"

REQUIRED_FIELDS = ("id", "name", "selector", "since_commit", "smoke_assertion")

# CLAUDE.md documents three forms, but the file has grown several more that the
# persona runner understands. Pinned as observed rather than as documented, so
# this catches a typo without rejecting entries that already work.
VALID_ASSERTION_PREFIXES = (
    "selector_exists",  # also covers selector_exists_after_expand and the
                        # selector_exists_if_* conditional variants
    "contains_text:",
    "js_truthy:",
    "selector_min_count",
    "click_then_visible",
)


@pytest.fixture(scope="module")
def entries() -> list:
    return json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))


@pytest.mark.unit
def test_inventory_is_valid_json(entries: list) -> None:
    assert isinstance(entries, list) and entries


@pytest.mark.unit
def test_every_entry_has_the_required_fields(entries: list) -> None:
    for entry in entries:
        missing = [f for f in REQUIRED_FIELDS if not entry.get(f)]
        assert not missing, f"{entry.get('id', '<no id>')} missing {missing}"


@pytest.mark.unit
def test_ids_are_unique(entries: list) -> None:
    ids = [e["id"] for e in entries]
    dupes = {i for i in ids if ids.count(i) > 1}
    assert not dupes, f"duplicate feature ids: {sorted(dupes)}"


@pytest.mark.unit
def test_smoke_assertions_use_a_known_form(entries: list) -> None:
    """Guards against a typo'd assertion that the persona would silently skip."""
    for entry in entries:
        assertion = entry["smoke_assertion"]
        assert assertion.startswith(VALID_ASSERTION_PREFIXES), (
            f"{entry['id']} has an unrecognised smoke_assertion: {assertion!r}"
        )
