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
SITE_BASE_URL = "https://hadrien-cornier.github.io/Culture-Calendar/"

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


def _shell_from_event(event: dict, *, base_url: str = SITE_BASE_URL) -> Optional[EventShell]:
    """Build an :class:`EventShell` from a raw event dict, or ``None`` to skip."""
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

    base = base_url if base_url.endswith("/") else base_url + "/"
    canonical = f"{base}events/{slug}.html"
    anchor = f"{base}#event={slug}"
    og_image = _og_image_url(slug, base_url=base)

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
        payload["location"] = {
            "@type": "Place",
            "name": shell.venue,
            "address": {"@type": "PostalAddress", "addressLocality": "Austin", "addressRegion": "TX"},
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
    events: Iterable[dict], *, base_url: str = SITE_BASE_URL
) -> list[EventShell]:
    """Build one :class:`EventShell` per event, de-duplicating by slug."""
    seen: set[str] = set()
    shells: list[EventShell] = []
    for event in events:
        shell = _shell_from_event(event, base_url=base_url)
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
