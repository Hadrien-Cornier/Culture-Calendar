"""Build a subscribable RSS 2.0 feed from ``docs/data.json``.

Publishes ``docs/feed.xml`` — the top ``FEED_LIMIT`` (30) events ranked by
rating, each item carrying the full AI review HTML and a deep-link
anchor back to the live site (``#event=<id>``).

Stdlib only (``xml.etree.ElementTree``) — no new dependencies. See
``scripts/build_ics_feed.py`` for the companion ICS generator that
shares the ``docs/data.json`` loader and screening-flatten logic.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from typing import Iterable, Optional, Sequence
from xml.etree import ElementTree as ET

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = REPO_ROOT / "docs" / "data.json"
OUT_FEED = REPO_ROOT / "docs" / "feed.xml"

SITE_URL = "https://hadrien-cornier.github.io/Culture-Calendar/"
FEED_URL = SITE_URL + "feed.xml"
FEED_TITLE = "Culture Calendar — Top Picks"
FEED_DESCRIPTION = (
    "AI-curated Austin cultural events: films, concerts, opera, dance, "
    "book clubs, and visual arts. Top-rated picks first."
)
FEED_LANG = "en-us"
FEED_LIMIT = 30
ATOM_NS = "http://www.w3.org/2005/Atom"
CONTENT_NS = "http://purl.org/rss/1.0/modules/content/"

LOG = logging.getLogger("build_rss_feed")


@dataclass(frozen=True)
class FeedItem:
    """One event distilled into the fields the RSS <item> needs."""

    event_id: str
    title: str
    rating: Optional[int]
    one_liner: str
    description_html: str
    type_: str
    venue: str
    url: str
    pub_date: datetime
    site_anchor: str


def _first_screening_datetime(event: dict) -> Optional[datetime]:
    """Return the earliest screening as an aware UTC datetime, if any."""
    screenings = event.get("screenings") or []
    dates: list[str] = []
    if screenings:
        for s in screenings:
            if isinstance(s, dict) and s.get("date"):
                dates.append(str(s["date"]))
    if not dates and event.get("dates"):
        dates = [str(d) for d in event["dates"] if d]
    if not dates:
        return None
    dates.sort()
    try:
        base = datetime.strptime(dates[0], "%Y-%m-%d")
    except ValueError:
        return None
    return base.replace(tzinfo=timezone.utc)


def _rank_key(event: dict, now: datetime) -> tuple:
    """Sort key: upcoming first, then higher rating, then soonest date."""
    first = _first_screening_datetime(event)
    if first is None:
        bucket = 2
        date_sort = 0.0
    elif first >= now:
        bucket = 0
        date_sort = first.timestamp()
    else:
        bucket = 1
        date_sort = -first.timestamp()

    rating = event.get("rating")
    rating_sort = -rating if isinstance(rating, (int, float)) else 1

    return (bucket, rating_sort, date_sort)


def _build_anchor(event_id: str) -> str:
    """Return the shell-page URL if a slug exists, else the site root.

    Shell pages at ``events/<slug>.html`` carry per-event OG and JSON-LD
    and auto-redirect to ``/#event=<slug>``; using them as feed links
    gives link-unfurl bots rich previews that the bare hash anchor
    cannot provide.
    """
    if not event_id:
        return SITE_URL
    safe = _safe_slug(event_id)
    return f"{SITE_URL}events/{safe}.html"


_SLUG_SAFE = re.compile(r"[^a-z0-9-]+")


def _safe_slug(raw: str) -> str:
    """Lower, ASCII-fold, replace non-alnum with ``-``; mirrors shell builder."""
    normalised = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii")
    normalised = normalised.lower()
    normalised = _SLUG_SAFE.sub("-", normalised).strip("-")
    return normalised or "event"


def _to_feed_item(event: dict, *, fallback_pub: datetime) -> Optional[FeedItem]:
    if not isinstance(event, dict):
        return None
    title = event.get("title")
    if not title:
        return None
    event_id = event.get("id") or ""
    pub_dt = _first_screening_datetime(event) or fallback_pub
    return FeedItem(
        event_id=str(event_id),
        title=str(title),
        rating=event.get("rating") if isinstance(event.get("rating"), (int, float)) else None,
        one_liner=str(event.get("one_liner_summary") or ""),
        description_html=str(event.get("description") or ""),
        type_=str(event.get("type") or "other"),
        venue=str(event.get("venue") or ""),
        url=str(event.get("url") or ""),
        pub_date=pub_dt,
        site_anchor=_build_anchor(str(event_id)),
    )


def select_top_items(
    events: Sequence[dict],
    *,
    limit: int = FEED_LIMIT,
    now: Optional[datetime] = None,
) -> list[FeedItem]:
    """Rank events and materialise the top ``limit`` as :class:`FeedItem`s."""
    reference_now = now or datetime.now(tz=timezone.utc)
    ranked = sorted(
        (e for e in events if isinstance(e, dict)),
        key=lambda e: _rank_key(e, reference_now),
    )
    items: list[FeedItem] = []
    for event in ranked:
        item = _to_feed_item(event, fallback_pub=reference_now)
        if item is None:
            continue
        items.append(item)
        if len(items) >= limit:
            break
    return items


def _category_label(type_: str) -> str:
    mapping = {
        "movie": "Film",
        "concert": "Concert",
        "opera": "Opera",
        "dance": "Dance",
        "book_club": "Books",
        "visual_arts": "Visual Arts",
        "other": "Event",
    }
    return mapping.get(type_, "Event")


def _build_item_description(item: FeedItem) -> str:
    """Compose the HTML body shown in an RSS reader for an item."""
    segments: list[str] = []
    if item.rating is not None:
        segments.append(f"<p><strong>Rating: {item.rating}/10</strong></p>")
    if item.one_liner:
        safe_liner = item.one_liner.strip()
        if safe_liner:
            segments.append(f"<p><em>{safe_liner}</em></p>")
    if item.description_html:
        segments.append(item.description_html)
    if item.venue:
        segments.append(f"<p><strong>Venue:</strong> {item.venue}</p>")
    segments.append(
        f'<p><a href="{item.site_anchor}">Open on Culture Calendar</a></p>'
    )
    if item.url and item.url != item.site_anchor:
        segments.append(f'<p><a href="{item.url}">Official page</a></p>')
    return "\n".join(segments)


def _format_rfc822(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return format_datetime(dt)


def build_rss(
    items: Iterable[FeedItem],
    *,
    now: Optional[datetime] = None,
) -> ET.ElementTree:
    """Assemble the RSS 2.0 ElementTree for the given items."""
    build_time = now or datetime.now(tz=timezone.utc)

    ET.register_namespace("atom", ATOM_NS)
    ET.register_namespace("content", CONTENT_NS)

    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = FEED_TITLE
    ET.SubElement(channel, "link").text = SITE_URL
    ET.SubElement(channel, "description").text = FEED_DESCRIPTION
    ET.SubElement(channel, "language").text = FEED_LANG
    ET.SubElement(channel, "lastBuildDate").text = _format_rfc822(build_time)
    ET.SubElement(channel, "generator").text = "Culture Calendar build_rss_feed.py"
    ET.SubElement(
        channel,
        "{%s}link" % ATOM_NS,
        {"href": FEED_URL, "rel": "self", "type": "application/rss+xml"},
    )

    for item in items:
        entry = ET.SubElement(channel, "item")
        display_title = item.title
        if item.rating is not None:
            display_title = f"[{item.rating}/10] {display_title}"
        ET.SubElement(entry, "title").text = display_title
        ET.SubElement(entry, "link").text = item.site_anchor
        guid = ET.SubElement(entry, "guid", {"isPermaLink": "false"})
        guid.text = item.event_id or item.site_anchor
        ET.SubElement(entry, "pubDate").text = _format_rfc822(item.pub_date)
        ET.SubElement(entry, "category").text = _category_label(item.type_)
        body = _build_item_description(item)
        ET.SubElement(entry, "description").text = body
        ET.SubElement(entry, "{%s}encoded" % CONTENT_NS).text = body

    return ET.ElementTree(rss)


def load_events(data_path: Path = DATA_PATH) -> list[dict]:
    if not data_path.exists():
        raise FileNotFoundError(f"Missing data file: {data_path}")
    with data_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, list):
        raise ValueError(f"{data_path} is not a JSON array")
    return payload


def write_feed(
    events: Sequence[dict],
    *,
    out_path: Path = OUT_FEED,
    limit: int = FEED_LIMIT,
    now: Optional[datetime] = None,
) -> int:
    """Select items, build XML, and write ``out_path``. Returns item count."""
    items = select_top_items(events, limit=limit, now=now)
    tree = build_rss(items, now=now)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(out_path, encoding="utf-8", xml_declaration=True)
    return len(items)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--data",
        type=Path,
        default=DATA_PATH,
        help="Path to docs/data.json (default: %(default)s).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=OUT_FEED,
        help="Output path for the RSS feed (default: %(default)s).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=FEED_LIMIT,
        help="Maximum item count (default: %(default)s).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress the summary line on stdout.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    events = load_events(args.data)
    count = write_feed(events, out_path=args.out, limit=args.limit)

    if not args.quiet:
        print(f"Wrote {args.out} ({count} items)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
