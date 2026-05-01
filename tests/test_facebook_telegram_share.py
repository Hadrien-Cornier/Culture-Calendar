"""Structural tests for the Facebook + Telegram share-intent entries.

Mirrors the brace-matching approach in ``tests/test_google_calendar_share.py``
so no JS runtime (no pyppeteer, no Node) is required. Asserts both new
PLATFORMS entries are present with the correct share URL shapes, and that
the Plausible analytics catalog comments include both new event names so
the T5.1 grep validator won't silently miss them.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "docs" / "script.js"
INVENTORY_PATH = REPO_ROOT / "config" / "feature-inventory.json"


def _extract_platform_entry(source: str, platform_id: str) -> str:
    needle = f'id: "{platform_id}"'
    idx = source.index(needle)
    open_brace = source.rfind("{", 0, idx)
    depth = 0
    for i in range(open_brace, len(source)):
        ch = source[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return source[open_brace : i + 1]
    raise AssertionError(f"unterminated entry for id={platform_id!r}")


@pytest.fixture(scope="module")
def script_source() -> str:
    return SCRIPT_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def facebook_entry(script_source: str) -> str:
    return _extract_platform_entry(script_source, "facebook")


@pytest.fixture(scope="module")
def telegram_entry(script_source: str) -> str:
    return _extract_platform_entry(script_source, "telegram")


# --- Facebook PLATFORMS entry --------------------------------------------


@pytest.mark.unit
def test_facebook_platform_has_correct_id(facebook_entry: str) -> None:
    assert 'id: "facebook"' in facebook_entry


@pytest.mark.unit
def test_facebook_platform_has_label(facebook_entry: str) -> None:
    assert re.search(
        r'label:\s*"[^"]*Facebook"', facebook_entry
    ), "facebook platform must carry a 'Facebook' label"


@pytest.mark.unit
def test_facebook_platform_uses_sharer_endpoint(facebook_entry: str) -> None:
    """Canonical Facebook sharer intent: facebook.com/sharer/sharer.php.

    Works from mobile browsers and auto-routes to the installed app on iOS
    and Android when available. Any other endpoint (like share.php or a
    mobile subdomain) is wrong.
    """
    assert "facebook.com/sharer/sharer.php" in facebook_entry


@pytest.mark.unit
def test_facebook_platform_passes_url_through_builder(facebook_entry: str) -> None:
    """u= must be the shareable URL, url-encoded."""
    assert re.search(
        r'"https://www\.facebook\.com/sharer/sharer\.php\?u="\s*\+\s*enc\s*\(\s*[a-zA-Z_]+\.url\s*\)',
        facebook_entry,
    ), "facebook URL must include encoded u= param pointing at shareable.url"


# --- Telegram PLATFORMS entry ---------------------------------------------


@pytest.mark.unit
def test_telegram_platform_has_correct_id(telegram_entry: str) -> None:
    assert 'id: "telegram"' in telegram_entry


@pytest.mark.unit
def test_telegram_platform_has_label(telegram_entry: str) -> None:
    assert re.search(
        r'label:\s*"[^"]*Telegram"', telegram_entry
    ), "telegram platform must carry a 'Telegram' label"


@pytest.mark.unit
def test_telegram_platform_uses_share_url_endpoint(telegram_entry: str) -> None:
    """Canonical Telegram share intent: t.me/share/url.

    Auto-routes to the Telegram app on mobile, falls back to Telegram Web
    on desktop. Older endpoints (telegram.me, or bot-style deep links) are
    wrong for generic link-share.
    """
    assert "t.me/share/url" in telegram_entry


@pytest.mark.unit
def test_telegram_platform_passes_url_and_text(telegram_entry: str) -> None:
    """Telegram expects url= and text= params, both encoded."""
    assert re.search(
        r'"https://t\.me/share/url\?url="\s*\+\s*enc\s*\(\s*[a-zA-Z_]+\.url\s*\)',
        telegram_entry,
    ), "telegram URL must start with ?url= pointing at shareable.url"
    assert re.search(
        r'"&text="\s*\+\s*enc\s*\(\s*[a-zA-Z_]+\.text\s*\)', telegram_entry
    ), "telegram URL must include encoded &text= param"


# --- Greppable analytics catalog -------------------------------------------


@pytest.mark.unit
def test_analytics_catalog_lists_new_events(script_source: str) -> None:
    """T5.1 analytics catalog comment must keep both new events greppable so
    silent removals fail CI. trackPlatform() auto-converts dashes to
    underscores; facebook and telegram IDs have no dashes, so the resulting
    Plausible event names are exactly cc_share_facebook and cc_share_telegram.
    """
    assert "cc_share_facebook" in script_source, (
        "cc_share_facebook must appear in the T5.1 greppable catalog"
    )
    assert "cc_share_telegram" in script_source, (
        "cc_share_telegram must appear in the T5.1 greppable catalog"
    )


# --- Feature inventory ----------------------------------------------------


@pytest.mark.unit
def test_feature_inventory_has_facebook_entry() -> None:
    """share-facebook must be appended so the continuity-user persona's
    future assertion sweep sees it. Selector is recorded even though no
    persona currently enforces share-menu entries — matches the existing
    share-google-calendar pattern.
    """
    text = INVENTORY_PATH.read_text(encoding="utf-8")
    assert '"id": "share-facebook"' in text
    assert '[data-share-platform=\\"facebook\\"]' in text


@pytest.mark.unit
def test_feature_inventory_has_telegram_entry() -> None:
    text = INVENTORY_PATH.read_text(encoding="utf-8")
    assert '"id": "share-telegram"' in text
    assert '[data-share-platform=\\"telegram\\"]' in text
