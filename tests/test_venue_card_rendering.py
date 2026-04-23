"""Structural tests for task-T3.1 venue rendering on card faces.

Background: the task adds two user-visible surfaces to every card:

* ``venue_display_name`` is used as the primary venue label in both
  ``buildPickCard`` and ``buildListingCard``, with a fallback to the raw
  ``venue`` field (keeps existing data rendering correctly while letting
  richer display-names override it).
* A new ``.event-venue-address`` line is appended to the card face when
  ``event.venue_address`` is truthy, surfacing the street address without
  requiring a click-through to the expanded review panel.

A no-dependency structural-assertion strategy is used here: the two card
builders are extracted from ``docs/script.js`` by brace-matching and
asserted against. This gives us fixture-driven behavioral coverage
without pulling in a browser runtime (no pyppeteer, no headless Chrome,
no npm install). Both builders are checked independently so a regression
in either one fails a dedicated test.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "docs" / "script.js"
STYLES_PATH = REPO_ROOT / "docs" / "styles.css"


def _extract_function_body(source: str, signature: str) -> str:
    """Return the ``{...}`` body of the first function matching ``signature``.

    ``signature`` is matched as a literal (e.g. ``"function buildPickCard"``).
    Brace depth is counted character-by-character; this is resilient to
    string literals and comments inside the body since the JS in scope here
    does not contain escaped braces that would confuse the depth counter.
    """
    idx = source.index(signature)
    open_brace = source.index("{", idx)
    depth = 0
    for i in range(open_brace, len(source)):
        ch = source[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return source[open_brace : i + 1]
    raise AssertionError(f"unterminated function body for {signature!r}")


@pytest.fixture(scope="module")
def script_source() -> str:
    return SCRIPT_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def pick_card_body(script_source: str) -> str:
    return _extract_function_body(script_source, "function buildPickCard")


@pytest.fixture(scope="module")
def listing_card_body(script_source: str) -> str:
    return _extract_function_body(script_source, "function buildListingCard")


# --- venue_display_name primary label with fallback ----------------------


@pytest.mark.unit
def test_pick_card_uses_venue_display_name_with_fallback(pick_card_body: str) -> None:
    """buildPickCard prefers venue_display_name, falls back to raw venue."""
    assert re.search(
        r"ev\.venue_display_name\s*\|\|\s*ev\.venue", pick_card_body
    ), "buildPickCard must use venue_display_name with a fallback to venue"


@pytest.mark.unit
def test_listing_card_uses_venue_display_name_with_fallback(
    listing_card_body: str,
) -> None:
    """buildListingCard prefers venue_display_name, falls back to raw venue."""
    assert re.search(
        r"ev\.venue_display_name\s*\|\|\s*ev\.venue", listing_card_body
    ), "buildListingCard must use venue_display_name with a fallback to venue"


# --- conditional .event-venue-address rendering --------------------------


@pytest.mark.unit
def test_pick_card_renders_venue_address_when_present(pick_card_body: str) -> None:
    """When venue_address is truthy, buildPickCard appends a .event-venue-address node."""
    assert "ev.venue_address" in pick_card_body, (
        "buildPickCard must gate the address node on ev.venue_address"
    )
    assert '"event-venue-address"' in pick_card_body, (
        "buildPickCard must assign the .event-venue-address class"
    )
    assert re.search(
        r'className\s*=\s*"event-venue-address"[\s\S]{0,400}?'
        r"textContent\s*=\s*ev\.venue_address",
        pick_card_body,
    ), "buildPickCard must set the address element's textContent to ev.venue_address"


@pytest.mark.unit
def test_listing_card_renders_venue_address_when_present(
    listing_card_body: str,
) -> None:
    """When venue_address is truthy, buildListingCard appends a .event-venue-address node."""
    assert "ev.venue_address" in listing_card_body, (
        "buildListingCard must gate the address node on ev.venue_address"
    )
    assert '"event-venue-address"' in listing_card_body, (
        "buildListingCard must assign the .event-venue-address class"
    )
    assert re.search(
        r'className\s*=\s*"event-venue-address"[\s\S]{0,400}?'
        r"textContent\s*=\s*ev\.venue_address",
        listing_card_body,
    ), "buildListingCard must set the address element's textContent to ev.venue_address"


# --- absence guard: no unconditional address render ----------------------


@pytest.mark.unit
def test_pick_card_address_render_is_conditional(pick_card_body: str) -> None:
    """The address element must live inside an ``if (ev.venue_address)`` block.

    Guards against a future refactor that renders an empty
    ``.event-venue-address`` node when the field is missing — which would
    leak an empty italic line onto every card.
    """
    assert re.search(
        r"if\s*\(\s*ev\.venue_address\s*\)\s*\{[\s\S]{0,400}?"
        r'"event-venue-address"',
        pick_card_body,
    ), "buildPickCard must only render .event-venue-address when the field is truthy"


@pytest.mark.unit
def test_listing_card_address_render_is_conditional(listing_card_body: str) -> None:
    """The address element must live inside an ``if (ev.venue_address)`` block."""
    assert re.search(
        r"if\s*\(\s*ev\.venue_address\s*\)\s*\{[\s\S]{0,400}?"
        r'"event-venue-address"',
        listing_card_body,
    ), "buildListingCard must only render .event-venue-address when the field is truthy"


# --- stylesheet coverage -------------------------------------------------


@pytest.mark.unit
def test_stylesheet_defines_event_venue_address_rule() -> None:
    """docs/styles.css must carry a rule for .event-venue-address so the
    secondary line renders with the intended typographic treatment."""
    css = STYLES_PATH.read_text(encoding="utf-8")
    assert re.search(
        r"\.event-venue-address\s*\{[^}]+\}", css
    ), "styles.css must define a .event-venue-address rule"
