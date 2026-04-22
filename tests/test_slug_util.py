"""Unit tests for ``scripts._slug_util.safe_slug``.

Guards the shared slug contract consumed by ``build_event_shells`` and
``build_rss_feed`` — both must emit the same slug shape as the site JS
so that ``#event=<slug>`` deep links resolve consistently across feed
subscribers, crawlers, and in-app navigation.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts._slug_util import safe_slug  # noqa: E402


def test_strips_diacritics():
    assert safe_slug("Camille Saint-Saëns") == "camille-saint-saens"


def test_lowercases_and_hyphenates_mixed_punctuation():
    assert safe_slug("8 1/2") == "8-1-2"


def test_apostrophes_become_hyphens():
    assert safe_slug("Don't Look Back") == "don-t-look-back"


def test_empty_string_returns_fallback():
    assert safe_slug("") == "event"


def test_symbol_only_returns_fallback():
    assert safe_slug("!!!") == "event"


def test_collapses_runs_of_non_alnum():
    assert safe_slug("a -- b") == "a-b"


def test_strips_leading_and_trailing_separators():
    assert safe_slug("--Hello, World!--") == "hello-world"


def test_unicode_whitespace_collapses():
    assert safe_slug("Naïve Café") == "naive-cafe"


def test_preserves_digits():
    assert safe_slug("2001: A Space Odyssey") == "2001-a-space-odyssey"


def test_idempotent_on_existing_slug():
    assert safe_slug("already-a-slug") == "already-a-slug"
