"""Shared URL slug helper used by feed / shell builders.

Centralises the diacritic-fold + ``[^a-z0-9]+ -> '-'`` logic so that
``scripts/build_event_shells.py`` (per-event shell pages) and
``scripts/build_rss_feed.py`` (RSS feed anchors) produce identical
slugs — the site JS uses the same shape for its ``#event=<slug>``
anchors, so a drifting implementation would silently break deep links.
"""
from __future__ import annotations

import re
import unicodedata

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_FALLBACK = "event"


def safe_slug(value: str) -> str:
    """Return a URL-safe slug; empty / symbol-only input yields ``event``.

    Steps: NFKD-normalise, ASCII-fold, lowercase, replace any run of
    non-alphanumerics with a single ``-``, strip edge hyphens.
    """
    if not value:
        return _FALLBACK
    normalised = (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    normalised = _SLUG_RE.sub("-", normalised).strip("-")
    return normalised or _FALLBACK
