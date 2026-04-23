"""Build per-event HTML shells at ``docs/events/<slug>.html``.

Each shell is a tiny static page that carries *per-event* Open Graph,
Twitter-card, and JSON-LD ``Event`` metadata pointing to the matching
SVG card under ``docs/og/``. Crawlers, link-unfurl bots, and search
engines read these without executing JavaScript; users land on a
readable fallback that links back to the in-app anchor ``/#event=<id>``.

This closes two P0 gaps from the post-run critique:

1. ``sitemap.xml`` had zero event URLs — 229 events invisible to Google.
2. The 229 SVG OG cards under ``docs/og/`` were orphaned — crawlers
   fetching ``/#event=<id>`` saw the site-default card, not the per-event one.

Stdlib only. Reads ``docs/data.json`` and writes ``docs/events/<slug>.html``
(one file per event) plus a ``.gitkeep`` for empty-directory preservation.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime
from html import escape
from pathlib import Path
from typing import Iterable, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts._slug_util import safe_slug  # noqa: E402

DATA_PATH = REPO_ROOT / "docs" / "data.json"
OUT_DIR = REPO_ROOT / "docs" / "events"
CONFIG_PATH = REPO_ROOT / "config" / "master_config.yaml"
SITE_BASE_URL = "https://hadrien-cornier.github.io/Culture-Calendar/"

# Venue *code* (stamped on events by ``MultiVenueScraper``) → config key under
# ``venues:`` in ``config/master_config.yaml``. Mirrors the mapping in
# ``update_website_data.py`` so this script can fall back to the master config
# when events in ``docs/data.json`` predate the T0.2 enrichment step.
_VENUE_CODE_TO_CONFIG_KEY: dict[str, str] = {
    "AFS": "afs",
    "Hyperreal": "hyperreal",
    "Paramount": "paramount",
    "AlienatedMajesty": "alienated_majesty",
    "FirstLight": "first_light",
    "Symphony": "austin_symphony",
    "Opera": "austin_opera",
    "Chamber Music": "austin_chamber_music",
    "EarlyMusic": "early_music_austin",
    "LaFollia": "la_follia",
    "BalletAustin": "ballet_austin",
    "ArtsOnAlexander": "arts_on_alexander",
    "NowPlayingAustinVisualArts": "now_playing_austin_visual_arts",
    "LivraBooks": "libra_books",
}

LOG = logging.getLogger("build_event_shells")


@dataclass(frozen=True)
class EventShell:
    """A single per-event shell page."""

    slug: str
    title: str
    rating: Optional[int]
    one_liner: str
    description_plain: str
    venue: str
    type_: str
    first_date: Optional[str]
    og_image: str
    canonical_url: str
    anchor_url: str
    ticket_url: str
    venue_display_name: str = ""
    venue_address: str = ""


# Matches "Austin, TX 78702" or "Austin, TX 78701-1234" at the end of the
# string. The postal code is optional because a few aggregator venues (e.g.
# NowPlayingAustin) only carry "Austin, TX". The leading comma is also
# optional so a bare "Austin, TX" string (no street prefix) still parses
# into locality + region. The parser never raises; it returns empty strings
# for fields it cannot locate.
_ADDRESS_TAIL_RE = re.compile(
    r"(?:^|,)\s*(?P<locality>[^,]+?)\s*,\s*(?P<region>[A-Z]{2})"
    r"(?:\s+(?P<postal>\d{5}(?:-\d{4})?))?\s*$"
)


def _parse_postal_address(raw: str) -> dict[str, str]:
    """Split a free-form US address into schema.org ``PostalAddress`` fields.

    Expected shape: ``"<street>, <city>, <ST> <ZIP>"``. When only the tail is
    present (e.g. ``"Austin, TX"``) the street becomes empty. The return dict
    always carries all four keys so the JSON-LD builder can omit blanks with a
    simple truthiness check.
    """
    text = (raw or "").strip()
    out = {
        "streetAddress": "",
        "addressLocality": "",
        "addressRegion": "",
        "postalCode": "",
    }
    if not text:
        return out
    match = _ADDRESS_TAIL_RE.search(text)
    if match:
        head = text[: match.start()].strip(", ").strip()
        out["streetAddress"] = head
        out["addressLocality"] = match.group("locality").strip()
        out["addressRegion"] = match.group("region").strip()
        out["postalCode"] = (match.group("postal") or "").strip()
    else:
        # No region/postal tail matched — treat the whole string as street.
        out["streetAddress"] = text
    return out


def _load_venue_metadata_from_config(
    config_path: Path = CONFIG_PATH,
) -> dict[str, dict]:
    """Return ``{venue_code: {display_name, address}}`` from master config.

    Falls back to an empty dict when the file is missing or PyYAML is not
    importable — shell generation never hard-requires the config, it just
    enriches JSON-LD when available.
    """
    try:
        import yaml  # PyYAML; installed as part of the project requirements.
    except Exception:  # pragma: no cover - defensive guard
        return {}
    if not config_path.is_file():
        return {}
    try:
        with config_path.open("r", encoding="utf-8") as handle:
            parsed = yaml.safe_load(handle) or {}
    except Exception:  # pragma: no cover - config must be readable in CI
        return {}
    venues_cfg = parsed.get("venues") or {}
    out: dict[str, dict] = {}
    for code, key in _VENUE_CODE_TO_CONFIG_KEY.items():
        entry = venues_cfg.get(key)
        if not isinstance(entry, dict):
            continue
        out[code] = {
            "display_name": str(entry.get("display_name") or "").strip(),
            "address": str(entry.get("address") or "").strip(),
        }
    return out


_slugify = safe_slug  # back-compat alias; uses shared scripts._slug_util.safe_slug


def _plain_text(html_or_text: str, *, max_len: int = 260) -> str:
    """Strip HTML tags and collapse whitespace into a single-line summary."""
    if not html_or_text:
        return ""
    text = re.sub(r"<[^>]+>", " ", html_or_text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_len:
        text = text[: max_len - 1].rstrip() + "…"
    return text


def _first_screening_date(event: dict) -> Optional[str]:
    """Return ISO-8601 date of the first screening, or None."""
    screenings = event.get("screenings") or []
    if not screenings:
        dates = event.get("dates") or []
        return dates[0] if dates else None
    first = screenings[0]
    return first.get("date")


def _og_image_url(slug: str, *, base_url: str) -> str:
    """Point at the pre-rendered SVG card if present; fall back to site default."""
    card_path = OUT_DIR.parent / "og" / f"{slug}.svg"
    if card_path.is_file():
        return f"{base_url}og/{slug}.svg"
    return f"{base_url}og/site-default.svg"


def _ticket_url(event: dict, *, fallback: str) -> str:
    """Pick the best ticket/event URL for ``offers.url``.

    Prefers the first screening's ``url`` (the per-date ticket link),
    then the event-level ``url``, then ``fallback`` (the in-app anchor).
    """
    screenings = event.get("screenings") or []
    if screenings:
        first = screenings[0]
        if isinstance(first, dict):
            url = str(first.get("url") or "").strip()
            if url:
                return url
    event_url = str(event.get("url") or "").strip()
    if event_url:
        return event_url
    return fallback


def _shell_from_event(
    event: dict,
    *,
    base_url: str = SITE_BASE_URL,
    venue_metadata: Optional[dict[str, dict]] = None,
) -> Optional[EventShell]:
    """Build an :class:`EventShell` from a raw event dict, or ``None`` to skip.

    ``venue_metadata`` maps a venue *code* to ``{display_name, address}`` and
    is used to backfill ``venue_display_name`` / ``venue_address`` when the
    event itself lacks them (e.g. a ``docs/data.json`` that predates T0.2).
    """
    raw_id = event.get("id") or event.get("title") or ""
    if not raw_id:
        return None
    slug = _slugify(raw_id)
    if slug == "event" and not event.get("id") and not event.get("title"):
        return None
    title = event.get("title") or slug.replace("-", " ").title()
    rating = event.get("rating")
    try:
        rating_int = int(rating) if rating is not None else None
    except (TypeError, ValueError):
        rating_int = None
    one_liner = _plain_text(event.get("oneLiner") or "", max_len=180)
    desc_plain = _plain_text(event.get("description") or "", max_len=260)
    venue = str(event.get("venue") or "").strip()
    type_ = str(event.get("type") or "").strip()
    first_date = _first_screening_date(event)

    display_name = str(event.get("venue_display_name") or "").strip()
    address = str(event.get("venue_address") or "").strip()
    if (not display_name or not address) and venue_metadata and venue in venue_metadata:
        fallback = venue_metadata[venue]
        if not display_name:
            display_name = fallback.get("display_name", "")
        if not address:
            address = fallback.get("address", "")

    base = base_url if base_url.endswith("/") else base_url + "/"
    canonical = f"{base}events/{slug}.html"
    anchor = f"{base}#event={slug}"
    og_image = _og_image_url(slug, base_url=base)
    ticket_url = _ticket_url(event, fallback=anchor)

    return EventShell(
        slug=slug,
        title=title,
        rating=rating_int,
        one_liner=one_liner,
        description_plain=desc_plain,
        venue=venue,
        type_=type_,
        first_date=first_date,
        og_image=og_image,
        canonical_url=canonical,
        anchor_url=anchor,
        ticket_url=ticket_url,
        venue_display_name=display_name,
        venue_address=address,
    )


def _json_ld(shell: EventShell) -> str:
    """Return a JSON-LD ``Event`` snippet for schema.org rich results."""
    payload = {
        "@context": "https://schema.org",
        "@type": "Event",
        "name": shell.title,
        "description": shell.one_liner or shell.description_plain or shell.title,
        "url": shell.canonical_url,
        "image": shell.og_image,
    }
    if shell.first_date:
        payload["startDate"] = shell.first_date
    if shell.venue:
        place_name = shell.venue_display_name or shell.venue
        # ``PostalAddress`` gains ``streetAddress`` + ``postalCode`` whenever
        # ``venue_address`` parses cleanly — closes the T0.4 gap flagged by
        # the persona council (Google rich-result linter demands both).
        address: dict[str, str] = {
            "@type": "PostalAddress",
            "addressLocality": "Austin",
            "addressRegion": "TX",
        }
        if shell.venue_address:
            parsed = _parse_postal_address(shell.venue_address)
            if parsed["streetAddress"]:
                address["streetAddress"] = parsed["streetAddress"]
            if parsed["addressLocality"]:
                address["addressLocality"] = parsed["addressLocality"]
            if parsed["addressRegion"]:
                address["addressRegion"] = parsed["addressRegion"]
            if parsed["postalCode"]:
                address["postalCode"] = parsed["postalCode"]
        payload["location"] = {
            "@type": "Place",
            "name": place_name,
            "address": address,
        }
    # offers.url points to the ticket/venue page so search crawlers link
    # directly to purchase, falling back to the in-app anchor when the
    # scraper did not capture a ticket URL.
    payload["offers"] = {
        "@type": "Offer",
        "url": shell.ticket_url,
        "availability": "https://schema.org/InStock",
    }
    # aggregateRating exposes our editorial 0-10 score as a single-count
    # rating so Google can surface the stars in rich results.
    if shell.rating is not None:
        payload["aggregateRating"] = {
            "@type": "AggregateRating",
            "ratingValue": shell.rating,
            "bestRating": 10,
            "worstRating": 0,
            "ratingCount": 1,
        }
    raw = json.dumps(payload, ensure_ascii=False)
    # Prevent a stray ``</script>`` inside a string from terminating the
    # enclosing JSON-LD <script> block (standard escaping per HTML5 spec).
    return raw.replace("</", "<\\/")


def _breadcrumb_ld(shell: EventShell, *, base_url: str = SITE_BASE_URL) -> str:
    """Return a JSON-LD ``BreadcrumbList`` snippet for this shell page.

    Emits Home > Events > <title> so search crawlers can surface the
    shell page's position in the site hierarchy. Tags are stripped from
    ``shell.title`` so hostile markup cannot leak into the payload.
    """
    base = base_url if base_url.endswith("/") else base_url + "/"
    name = _plain_text(shell.title, max_len=200) or shell.slug
    payload = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Culture Calendar", "item": base},
            {"@type": "ListItem", "position": 2, "name": "Events", "item": f"{base}events/"},
            {"@type": "ListItem", "position": 3, "name": name, "item": shell.canonical_url},
        ],
    }
    raw = json.dumps(payload, ensure_ascii=False)
    return raw.replace("</", "<\\/")


def render_shell_html(shell: EventShell) -> str:
    """Return the full HTML document for this shell page."""
    rating_tag = f"[{shell.rating}/10] " if shell.rating is not None else ""
    page_title = f"{rating_tag}{shell.title} — Culture Calendar"
    description = shell.one_liner or shell.description_plain or f"{shell.title} at {shell.venue}"

    body_parts = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{escape(page_title)}</title>",
        f'<meta name="description" content="{escape(description)}">',
        f'<link rel="canonical" href="{escape(shell.canonical_url)}">',
        '<meta property="og:type" content="article">',
        f'<meta property="og:title" content="{escape(page_title)}">',
        f'<meta property="og:description" content="{escape(description)}">',
        f'<meta property="og:url" content="{escape(shell.canonical_url)}">',
        f'<meta property="og:image" content="{escape(shell.og_image)}">',
        '<meta property="og:site_name" content="Culture Calendar">',
        '<meta name="twitter:card" content="summary_large_image">',
        f'<meta name="twitter:title" content="{escape(page_title)}">',
        f'<meta name="twitter:description" content="{escape(description)}">',
        f'<meta name="twitter:image" content="{escape(shell.og_image)}">',
        '<link rel="stylesheet" href="../styles.css">',
        '<link rel="alternate" type="application/rss+xml" title="Culture Calendar" '
        f'href="{escape(SITE_BASE_URL)}feed.xml">',
        f'<script type="application/ld+json">{_json_ld(shell)}</script>',
        f'<script type="application/ld+json">{_breadcrumb_ld(shell)}</script>',
        # Redirect after the meta is fetched so link-unfurl bots (which skip JS
        # and <meta refresh>) still see the tags above; real users bounce to the
        # in-app anchor where the live modal exists.
        f'<script>window.addEventListener("DOMContentLoaded",function(){{window.location.replace("{escape(shell.anchor_url)}");}});</script>',
        "</head>",
        '<body class="event-shell">',
        f'<header class="event-shell-header"><h1>{escape(shell.title)}</h1>',
        f'<p class="event-shell-sub">{escape(shell.venue)} · {escape(shell.type_.title() or "Event")}'
        + (f' · {escape(shell.first_date)}' if shell.first_date else '')
        + "</p></header>",
    ]
    if shell.one_liner:
        body_parts.append(
            f'<p class="event-shell-oneliner">{escape(shell.one_liner)}</p>'
        )
    if shell.description_plain:
        body_parts.append(
            f'<p class="event-shell-desc">{escape(shell.description_plain)}</p>'
        )
    body_parts.extend(
        [
            f'<p><a class="event-shell-cta" href="{escape(shell.anchor_url)}">Open this pick in Culture Calendar →</a></p>',
            '<p><a href="../">← Back to all events</a></p>',
            "</body>",
            "</html>",
            "",
        ]
    )
    return "\n".join(body_parts)


def load_events(data_path: Path = DATA_PATH) -> list[dict]:
    """Load the raw event array from ``docs/data.json``."""
    if not data_path.exists():
        raise FileNotFoundError(f"Missing data file: {data_path}")
    with data_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, list):
        raise ValueError(f"{data_path} is not a JSON array")
    return payload


def build_shells(
    events: Iterable[dict],
    *,
    base_url: str = SITE_BASE_URL,
    venue_metadata: Optional[dict[str, dict]] = None,
) -> list[EventShell]:
    """Build one :class:`EventShell` per event, de-duplicating by slug.

    When ``venue_metadata`` is ``None`` the mapping is loaded lazily from
    ``config/master_config.yaml`` so a shipped ``docs/data.json`` that lacks
    ``venue_address`` still produces structured PostalAddress JSON-LD.
    """
    if venue_metadata is None:
        venue_metadata = _load_venue_metadata_from_config()
    seen: set[str] = set()
    shells: list[EventShell] = []
    for event in events:
        shell = _shell_from_event(
            event, base_url=base_url, venue_metadata=venue_metadata
        )
        if shell is None or shell.slug in seen:
            continue
        seen.add(shell.slug)
        shells.append(shell)
    return shells


def write_shells(shells: Sequence[EventShell], *, out_dir: Path = OUT_DIR) -> int:
    """Write every shell; return count. Clears stale shells first."""
    out_dir.mkdir(parents=True, exist_ok=True)
    # Remove stale shells from prior runs; preserves .gitkeep.
    for stale in out_dir.glob("*.html"):
        stale.unlink()
    (out_dir / ".gitkeep").touch(exist_ok=True)
    for shell in shells:
        (out_dir / f"{shell.slug}.html").write_text(render_shell_html(shell), encoding="utf-8")
    return len(shells)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--data",
        type=Path,
        default=DATA_PATH,
        help="Path to docs/data.json.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=OUT_DIR,
        help="Output directory for per-event shell pages.",
    )
    parser.add_argument(
        "--base-url",
        default=SITE_BASE_URL,
        help="Absolute site base URL for canonical + social meta.",
    )
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    events = load_events(args.data)
    shells = build_shells(events, base_url=args.base_url)
    count = write_shells(shells, out_dir=args.out)
    if not args.quiet:
        print(f"Wrote {count} event shell pages to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
