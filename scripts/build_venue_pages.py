"""Build per-venue deep-dive pages under ``docs/venues/<slug>.html``.

One page per distinct venue in ``docs/data.json``: a one-paragraph
venue description and a chronologically-ordered list of upcoming
events that deep-link back to the main site (``#event=<id>``).

Known venues get a curated description; unknown venues fall back to a
generic one-liner derived from the dominant event category. See
``scripts/build_weekly_digest.py`` for the sibling ISO-week digest and
``scripts/build_ics_feed.py`` for the webcal feed linked from each
venue page.

Stdlib only.
"""

from __future__ import annotations

import argparse
import html
import json
import logging
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = REPO_ROOT / "docs" / "data.json"
OUT_DIR = REPO_ROOT / "docs" / "venues"

SITE_HOST = "hadrien-cornier.github.io"
SITE_PATH = "/Culture-Calendar/"
SITE_URL = f"https://{SITE_HOST}{SITE_PATH}"
RSS_URL = f"{SITE_URL}feed.xml"
TOP_PICKS_WEBCAL = f"webcal://{SITE_HOST}{SITE_PATH}top-picks.ics"

DEFAULT_UPCOMING_LIMIT = 40

CATEGORY_LABELS = {
    "movie": "Film",
    "concert": "Concert",
    "opera": "Opera",
    "dance": "Dance",
    "book_club": "Books",
    "visual_arts": "Visual Arts",
    "other": "Event",
}

MONTHS_SHORT = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]
WEEKDAY_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Curated one-paragraph descriptions for well-known venues. Keys match
# the ``venue`` field in ``docs/data.json`` exactly.
VENUE_DESCRIPTIONS: dict[str, str] = {
    "AFS": (
        "Austin Film Society runs the city's most consistent programming "
        "of international arthouse, repertory and director-focused series "
        "at AFS Cinema. Expect new foreign-language releases alongside "
        "retrospectives, often with guest filmmakers in attendance."
    ),
    "Hyperreal": (
        "Hyperreal Film Club is a member-driven cinephile collective "
        "screening cult, experimental and under-seen titles. Programming "
        "leans toward themed series and genre deep-dives that you are "
        "unlikely to catch on the multiplex circuit."
    ),
    "Paramount": (
        "The Paramount Theatre is Austin's landmark 1915 downtown venue, "
        "hosting classic-film revivals under its Summer Classics series as "
        "well as touring comedians, talks and live performances in a "
        "restored historic house."
    ),
    "Symphony": (
        "The Austin Symphony Orchestra is the city's flagship classical "
        "ensemble, performing a subscription season of canonical "
        "symphonic repertoire, pops concerts and new-music premieres at "
        "The Long Center for the Performing Arts."
    ),
    "EarlyMusic": (
        "Early Music Austin presents period-instrument performances of "
        "medieval, Renaissance and Baroque repertoire, often featuring "
        "touring specialists and scholarly programme notes."
    ),
    "LaFollia": (
        "La Follia Austin Baroque programs historically informed "
        "performances of 17th- and 18th-century music, pairing familiar "
        "masters with obscure composers from the same period."
    ),
    "Chamber Music": (
        "The Austin Chamber Music Center presents intimate small-ensemble "
        "concerts across the classical and contemporary repertoire, "
        "spotlighting visiting quartets and local artists."
    ),
    "Opera": (
        "Austin Opera produces a mainstage season of grand opera at The "
        "Long Center, alongside smaller recital and educational "
        "programming across the year."
    ),
    "BalletAustin": (
        "Ballet Austin is the city's resident professional ballet company, "
        "performing a full season of classical and contemporary work at "
        "The Long Center, including perennial holiday productions."
    ),
    "AlienatedMajesty": (
        "Alienated Majesty Books is an independent bookstore whose "
        "in-store author readings, panels and themed reading clubs form a "
        "running conversation about contemporary literature."
    ),
    "FirstLight": (
        "First Light Austin is an independent bookstore that hosts author "
        "readings, spotlight book clubs and literary discussion groups as "
        "part of its regular programming."
    ),
    "NewYorkerMeetup": (
        "The New Yorker Short Story Meetup is a weekly literary discussion "
        "group that reads and debates the magazine's current short fiction "
        "together."
    ),
    "Bee Cave Art Foundation": (
        "The Bee Cave Art Foundation is a Texas Hill Country arts nonprofit "
        "running rotating visual-arts exhibitions, artist talks and "
        "workshops in a community gallery setting."
    ),
    "Blanton Museum of Art, Austin": (
        "The Blanton Museum of Art, on the UT Austin campus, is one of the "
        "largest university art museums in the U.S., with a permanent "
        "collection spanning European, Latin American and contemporary "
        "American art alongside rotating special exhibitions."
    ),
    "Dougherty Arts Center, Austin": (
        "The Dougherty Arts Center, run by the City of Austin, presents "
        "visual-arts exhibitions, theatre productions and community arts "
        "programming in its South Austin gallery and black-box theatre."
    ),
    "Laura Rathe Fine Art, Austin": (
        "Laura Rathe Fine Art is a contemporary gallery with a downtown "
        "Austin outpost representing mid-career and established painters "
        "and sculptors through rotating solo and group exhibitions."
    ),
    "The Cathedral, Austin": (
        "The Cathedral is an Austin event space that hosts concerts, "
        "readings and cross-disciplinary cultural programming in a "
        "distinctive historic building."
    ),
}

# Generic fallback templates keyed by dominant event category.
GENERIC_DESCRIPTIONS: dict[str, str] = {
    "movie": (
        "{name} is an Austin venue that programs film screenings for the "
        "local moviegoing community."
    ),
    "concert": (
        "{name} is an Austin venue that hosts live concert programming."
    ),
    "opera": (
        "{name} is an Austin venue that presents opera productions."
    ),
    "dance": (
        "{name} is an Austin venue that presents dance productions."
    ),
    "book_club": (
        "{name} hosts book-club discussions and literary events in Austin."
    ),
    "visual_arts": (
        "{name} is an Austin venue that presents rotating visual-arts "
        "exhibitions and related programming."
    ),
    "other": (
        "{name} is an Austin cultural venue whose programming is tracked "
        "by Culture Calendar."
    ),
}

LOG = logging.getLogger("build_venue_pages")

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    """Lowercase, hyphen-separated slug.

    ``"Blanton Museum of Art, Austin"`` → ``"blanton-museum-of-art-austin"``.
    """
    lowered = (name or "").strip().lower()
    slug = _SLUG_STRIP.sub("-", lowered)
    return slug.strip("-")


@dataclass(frozen=True)
class UpcomingScreening:
    """One upcoming screening attached to a venue event."""

    date: str
    time: str
    url: str


@dataclass(frozen=True)
class VenueEvent:
    """One event rolled up into the data the venue page needs."""

    event_id: str
    title: str
    rating: Optional[int]
    one_liner: str
    category_label: str
    url: str
    screenings: tuple[UpcomingScreening, ...]

    @property
    def first_screening(self) -> Optional[UpcomingScreening]:
        return self.screenings[0] if self.screenings else None


@dataclass(frozen=True)
class VenuePage:
    """Rendered data for one venue."""

    venue_name: str
    slug: str
    description: str
    events: tuple[VenueEvent, ...]
    total_events: int
    dominant_category: str


def _parse_iso_date(value: str) -> Optional[date]:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _event_screenings(event: dict) -> list[dict]:
    screenings = event.get("screenings") or []
    if screenings:
        return [s for s in screenings if isinstance(s, dict) and s.get("date")]
    dates = event.get("dates") or []
    times = event.get("times") or []
    default_url = event.get("url") or ""
    if dates and times and len(dates) == len(times):
        return [
            {"date": d, "time": t, "url": default_url}
            for d, t in zip(dates, times)
        ]
    if dates:
        return [{"date": d, "time": "", "url": default_url} for d in dates]
    return []


def _upcoming_screenings(event: dict, today: date) -> list[UpcomingScreening]:
    out: list[UpcomingScreening] = []
    for raw in _event_screenings(event):
        sd = _parse_iso_date(str(raw.get("date", "")))
        if sd is None or sd < today:
            continue
        out.append(
            UpcomingScreening(
                date=str(raw.get("date") or ""),
                time=str(raw.get("time") or ""),
                url=str(raw.get("url") or event.get("url") or ""),
            )
        )
    out.sort(key=lambda s: (s.date, s.time))
    return out


def _dominant_category(events: Sequence[dict]) -> str:
    counts: dict[str, int] = {}
    for e in events:
        t = str(e.get("type") or "other")
        counts[t] = counts.get(t, 0) + 1
    if not counts:
        return "other"
    return max(counts.items(), key=lambda kv: (kv[1], kv[0]))[0]


def _venue_description(name: str, dominant: str) -> str:
    curated = VENUE_DESCRIPTIONS.get(name)
    if curated:
        return curated
    template = GENERIC_DESCRIPTIONS.get(dominant, GENERIC_DESCRIPTIONS["other"])
    return template.format(name=name)


def group_by_venue(
    events: Sequence[dict],
    *,
    today: date,
    limit: int = DEFAULT_UPCOMING_LIMIT,
) -> list[VenuePage]:
    """Group events by venue and build renderable ``VenuePage`` records.

    Every distinct venue produces one page, even if it has no upcoming
    screenings — the page then shows an empty-state message.
    """
    buckets: dict[str, list[dict]] = {}
    for event in events:
        if not isinstance(event, dict):
            continue
        name = str(event.get("venue") or "").strip()
        if not name:
            continue
        buckets.setdefault(name, []).append(event)

    pages: list[VenuePage] = []
    for name, bucket in sorted(buckets.items(), key=lambda kv: kv[0].lower()):
        venue_events: list[VenueEvent] = []
        for event in bucket:
            title = str(event.get("title") or "").strip()
            if not title:
                continue
            upcoming = _upcoming_screenings(event, today)
            if not upcoming:
                continue
            rating = event.get("rating")
            type_ = str(event.get("type") or "other")
            venue_events.append(
                VenueEvent(
                    event_id=str(event.get("id") or ""),
                    title=title,
                    rating=int(rating) if isinstance(rating, (int, float)) else None,
                    one_liner=str(event.get("one_liner_summary") or ""),
                    category_label=CATEGORY_LABELS.get(
                        type_, type_.replace("_", " ").title()
                    ),
                    url=str(event.get("url") or ""),
                    screenings=tuple(upcoming),
                )
            )
        venue_events.sort(
            key=lambda v: (
                v.first_screening.date if v.first_screening else "9999-99-99",
                v.first_screening.time if v.first_screening else "",
                v.title.lower(),
            )
        )
        capped = venue_events[:limit] if limit > 0 else venue_events
        dominant = _dominant_category(bucket)
        pages.append(
            VenuePage(
                venue_name=name,
                slug=slugify(name),
                description=_venue_description(name, dominant),
                events=tuple(capped),
                total_events=len(bucket),
                dominant_category=dominant,
            )
        )
    return pages


def _esc(value: str) -> str:
    return html.escape(value or "", quote=True)


def _format_time(t: str) -> str:
    m = re.match(r"^(\d{1,2}):(\d{2})$", t or "")
    if not m:
        return t or ""
    hh = int(m.group(1))
    mm = m.group(2)
    ampm = "PM" if hh >= 12 else "AM"
    h12 = hh % 12 or 12
    return f"{h12}:{mm} {ampm}"


def _format_when(s: UpcomingScreening) -> str:
    sd = _parse_iso_date(s.date)
    if sd is None:
        base = s.date or ""
    else:
        base = f"{WEEKDAY_SHORT[sd.weekday()]}, {MONTHS_SHORT[sd.month - 1]} {sd.day}"
    tpart = _format_time(s.time)
    return f"{base} · {tpart}" if tpart else base


def _anchor(event: VenueEvent) -> str:
    if not event.event_id:
        return "../"
    return f"../#event={_esc(event.event_id)}"


def _breadcrumb_jsonld(items: Sequence[tuple[str, str]]) -> str:
    """Render a schema.org BreadcrumbList JSON-LD payload.

    ``items`` is an ordered sequence of ``(name, url)`` pairs. The final
    item's URL is often the canonical page URL itself.
    """
    payload = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": i + 1,
                "name": name,
                "item": url,
            }
            for i, (name, url) in enumerate(items)
        ],
    }
    raw = json.dumps(payload, ensure_ascii=False)
    return raw.replace("</", "<\\/")


def _render_event(event: VenueEvent, ordinal: int) -> str:
    anchor = _anchor(event)
    rating_html = ""
    if event.rating is not None:
        rating_html = (
            f'<span class="venue-rating" aria-label="rated {event.rating} out of 10">'
            f"{event.rating} / 10</span>"
        )
    subtitle_bits: list[str] = []
    first = event.first_screening
    if first:
        subtitle_bits.append(_format_when(first))
    if event.category_label:
        subtitle_bits.append(event.category_label)
    subtitle_text = " · ".join(_esc(b) for b in subtitle_bits)
    subtitle_html = (
        f'<p class="venue-event-subtitle">{subtitle_text}</p>'
        if subtitle_text
        else ""
    )
    one_liner_html = ""
    if event.one_liner:
        one_liner_html = (
            f'<p class="venue-event-oneliner">{_esc(event.one_liner)}</p>'
        )
    extra_screenings = ""
    if len(event.screenings) > 1:
        items = "".join(
            f"<li>{_esc(_format_when(s))}</li>" for s in event.screenings[1:]
        )
        extra_screenings = (
            f'<ul class="venue-event-screenings">{items}</ul>'
        )
    official_html = ""
    if event.url:
        official_html = (
            f'<p class="venue-event-footer">'
            f'<a class="venue-event-link" href="{_esc(event.url)}" '
            f'rel="noopener" target="_blank">Official page</a>'
            f"</p>"
        )
    event_dom_id = f"venue-event-{_esc(event.event_id) or ordinal}"
    return (
        f'<li class="venue-event" id="{event_dom_id}">'
        f'<article class="venue-event-article">'
        f'<header class="venue-event-header">'
        f'<div class="venue-event-rank" aria-hidden="true">{ordinal:02d}</div>'
        f"{rating_html}"
        f'<h2 class="venue-event-title">'
        f'<a href="{anchor}">{_esc(event.title)}</a>'
        f"</h2>"
        f"{subtitle_html}"
        f"</header>"
        f"{one_liner_html}"
        f"{extra_screenings}"
        f"{official_html}"
        f"</article>"
        f"</li>"
    )


def render_page(page: VenuePage) -> str:
    """Render one venue's deep-dive HTML page."""
    title = f"{page.venue_name} — Culture Calendar"
    description_meta = (
        f"Upcoming {page.venue_name} events curated by Culture Calendar. "
        f"{len(page.events)} upcoming of {page.total_events} tracked."
    )
    if page.events:
        events_html = "\n".join(
            _render_event(e, i + 1) for i, e in enumerate(page.events)
        )
        events_block = f'<ol class="venue-events">{events_html}</ol>'
    else:
        events_block = (
            '<p class="venue-empty">No upcoming events scheduled. '
            '<a href="../">Browse the full calendar</a> to see what else is on.'
            "</p>"
        )
    count_note = (
        f'<p class="venue-meta">{len(page.events)} upcoming event'
        f"{'s' if len(page.events) != 1 else ''}"
        f" · {_esc(CATEGORY_LABELS.get(page.dominant_category, 'Event'))}"
        f"-forward programming</p>"
    )
    canonical = f"{SITE_URL}venues/{page.slug}.html"
    breadcrumb_json = _breadcrumb_jsonld(
        (
            ("Culture Calendar", SITE_URL),
            ("Venues", f"{SITE_URL}venues/"),
            (page.venue_name, canonical),
        )
    )
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{_esc(title)}</title>\n"
        f'<meta name="description" content="{_esc(description_meta)}">\n'
        f'<link rel="canonical" href="{_esc(canonical)}">\n'
        '<link rel="stylesheet" href="../styles.css">\n'
        '<link rel="alternate" type="application/rss+xml" title="Culture Calendar" '
        f'href="{_esc(RSS_URL)}">\n'
        f'<script type="application/ld+json">{breadcrumb_json}</script>\n'
        "</head>\n"
        '<body class="venue-page">\n'
        '<header class="venue-masthead">\n'
        '<p class="venue-eyebrow">Culture Calendar · Venue</p>\n'
        f"<h1>{_esc(page.venue_name)}</h1>\n"
        f'<p class="venue-description">{_esc(page.description)}</p>\n'
        f"{count_note}\n"
        '<nav class="venue-actions" aria-label="Venue actions">\n'
        '<a href="../">← Back to Calendar</a>\n'
        f'<a href="{_esc(RSS_URL)}">RSS</a>\n'
        f'<a href="{_esc(TOP_PICKS_WEBCAL)}">Top Picks (webcal)</a>\n'
        "</nav>\n"
        "</header>\n"
        '<main class="venue-main">\n'
        f"{events_block}\n"
        "</main>\n"
        '<footer class="venue-footer">\n'
        '<p><a href="../">Culture Calendar</a> · AI-curated Austin cultural events</p>\n'
        "</footer>\n"
        "</body>\n"
        "</html>\n"
    )


def load_events(data_path: Path = DATA_PATH) -> list[dict]:
    if not data_path.exists():
        raise FileNotFoundError(f"Missing data file: {data_path}")
    with data_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, list):
        raise ValueError(f"{data_path} is not a JSON array")
    return payload


def write_pages(
    events: Sequence[dict],
    *,
    out_dir: Path = OUT_DIR,
    today: Optional[date] = None,
    limit: int = DEFAULT_UPCOMING_LIMIT,
) -> list[tuple[Path, VenuePage]]:
    """Write one HTML page per distinct venue. Returns ``(path, page)`` pairs."""
    today = today or datetime.now().date()
    pages = group_by_venue(events, today=today, limit=limit)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[tuple[Path, VenuePage]] = []
    for page in pages:
        out_path = out_dir / f"{page.slug}.html"
        out_path.write_text(render_page(page), encoding="utf-8")
        written.append((out_path, page))
    return written


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--data",
        type=Path,
        default=DATA_PATH,
        help="Path to docs/data.json (default: %(default)s).",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=OUT_DIR,
        help="Output directory for venue HTML (default: %(default)s).",
    )
    parser.add_argument(
        "--today",
        type=str,
        default=None,
        help="Override 'today' as YYYY-MM-DD (default: system date).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_UPCOMING_LIMIT,
        help="Maximum upcoming events per venue (default: %(default)s).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-file summary lines on stdout.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    today: Optional[date] = None
    if args.today:
        today = _parse_iso_date(args.today)
        if today is None:
            parser.error(f"--today must be YYYY-MM-DD, got {args.today!r}")

    events = load_events(args.data)
    written = write_pages(
        events, out_dir=args.out_dir, today=today, limit=args.limit
    )
    if not args.quiet:
        for path, page in written:
            print(f"Wrote {path} ({len(page.events)} upcoming of {page.total_events})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
