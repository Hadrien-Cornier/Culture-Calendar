"""Build per-person deep-dive pages under ``docs/people/<slug>.html``.

One page per composer (concerts + operas), director (movies) or author
(book clubs) with two or more tracked events. Each page lists the
person's upcoming events with deep-links back to ``../#event=<id>``.

Keys mirror ``scripts/build_venue_pages.py``: curated descriptions
where available, otherwise a generic role-based fallback. Stdlib only.
"""

from __future__ import annotations

import argparse
import html
import json
import logging
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = REPO_ROOT / "docs" / "data.json"
OUT_DIR = REPO_ROOT / "docs" / "people"

SITE_HOST = "hadrien-cornier.github.io"
SITE_PATH = "/Culture-Calendar/"
SITE_URL = f"https://{SITE_HOST}{SITE_PATH}"
RSS_URL = f"{SITE_URL}feed.xml"
TOP_PICKS_WEBCAL = f"webcal://{SITE_HOST}{SITE_PATH}top-picks.ics"

DEFAULT_UPCOMING_LIMIT = 40
MIN_EVENTS_PER_PERSON = 2

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

ROLE_COMPOSER = "composer"
ROLE_DIRECTOR = "director"
ROLE_AUTHOR = "author"

ROLE_LABELS = {
    ROLE_COMPOSER: "Composer",
    ROLE_DIRECTOR: "Director",
    ROLE_AUTHOR: "Author",
}

ROLE_DESCRIPTIONS = {
    ROLE_COMPOSER: (
        "{name} is a composer whose works appear across Culture "
        "Calendar's upcoming concert and opera programming."
    ),
    ROLE_DIRECTOR: (
        "{name} is a filmmaker whose films appear across Culture "
        "Calendar's upcoming repertory screenings."
    ),
    ROLE_AUTHOR: (
        "{name} is an author whose books anchor upcoming Culture "
        "Calendar book-club discussions."
    ),
}

# Case-insensitive placeholder values we should never treat as a real
# person name (and therefore never create a page for).
NAME_BLOCKLIST = frozenset({
    "",
    "various",
    "various artists",
    "others",
    "other",
    "unknown",
    "n/a",
    "na",
    "tba",
    "tbd",
    "anonymous",
    "traditional",
})

LOG = logging.getLogger("build_people_pages")

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    """Lowercase, hyphen-separated slug.

    ``"Camille Saint-Saëns"`` → ``"camille-saint-sa-ns"`` (non-ASCII
    collapses to a single hyphen run, then trims).
    """
    lowered = (name or "").strip().lower()
    slug = _SLUG_STRIP.sub("-", lowered)
    return slug.strip("-")


def _clean_name(value: object) -> str:
    if not isinstance(value, str):
        return ""
    stripped = value.strip()
    if stripped.lower() in NAME_BLOCKLIST:
        return ""
    return stripped


def _extract_directors(event: dict) -> list[str]:
    """Return director names for a movie event (usually one)."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in (event.get("director"), event.get("directors")):
        if isinstance(raw, str):
            cleaned = _clean_name(raw)
            if cleaned and cleaned.lower() not in seen:
                out.append(cleaned)
                seen.add(cleaned.lower())
        elif isinstance(raw, list):
            for item in raw:
                cleaned = _clean_name(item)
                if cleaned and cleaned.lower() not in seen:
                    out.append(cleaned)
                    seen.add(cleaned.lower())
    return out


def _extract_composers(event: dict) -> list[str]:
    """Return composer names for a concert or opera event."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in (event.get("composers"), event.get("composer")):
        if isinstance(raw, str):
            cleaned = _clean_name(raw)
            if cleaned and cleaned.lower() not in seen:
                out.append(cleaned)
                seen.add(cleaned.lower())
        elif isinstance(raw, list):
            for item in raw:
                cleaned = _clean_name(item)
                if cleaned and cleaned.lower() not in seen:
                    out.append(cleaned)
                    seen.add(cleaned.lower())
    return out


def _extract_authors(event: dict) -> list[str]:
    """Return author names for a book-club event."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in (event.get("author"), event.get("authors")):
        if isinstance(raw, str):
            cleaned = _clean_name(raw)
            if cleaned and cleaned.lower() not in seen:
                out.append(cleaned)
                seen.add(cleaned.lower())
        elif isinstance(raw, list):
            for item in raw:
                cleaned = _clean_name(item)
                if cleaned and cleaned.lower() not in seen:
                    out.append(cleaned)
                    seen.add(cleaned.lower())
    return out


def _people_for_event(event: dict) -> list[tuple[str, str]]:
    """Return ``(role, name)`` pairs contributed by a single event."""
    kind = str(event.get("type") or "").strip().lower()
    if kind == "movie":
        return [(ROLE_DIRECTOR, n) for n in _extract_directors(event)]
    if kind in ("concert", "opera"):
        return [(ROLE_COMPOSER, n) for n in _extract_composers(event)]
    if kind == "book_club":
        return [(ROLE_AUTHOR, n) for n in _extract_authors(event)]
    return []


@dataclass(frozen=True)
class UpcomingScreening:
    date: str
    time: str
    url: str


@dataclass(frozen=True)
class PersonEvent:
    event_id: str
    title: str
    rating: Optional[int]
    one_liner: str
    category_label: str
    venue: str
    url: str
    screenings: tuple[UpcomingScreening, ...]

    @property
    def first_screening(self) -> Optional[UpcomingScreening]:
        return self.screenings[0] if self.screenings else None


@dataclass(frozen=True)
class PersonPage:
    person_name: str
    slug: str
    role: str
    description: str
    events: tuple[PersonEvent, ...]
    total_events: int


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


def _role_description(name: str, role: str) -> str:
    template = ROLE_DESCRIPTIONS.get(role, ROLE_DESCRIPTIONS[ROLE_COMPOSER])
    return template.format(name=name)


def _build_person_event(event: dict, today: date) -> Optional[PersonEvent]:
    title = str(event.get("title") or "").strip()
    if not title:
        return None
    upcoming = _upcoming_screenings(event, today)
    if not upcoming:
        return None
    rating = event.get("rating")
    type_ = str(event.get("type") or "other")
    return PersonEvent(
        event_id=str(event.get("id") or ""),
        title=title,
        rating=int(rating) if isinstance(rating, (int, float)) else None,
        one_liner=str(event.get("one_liner_summary") or ""),
        category_label=CATEGORY_LABELS.get(
            type_, type_.replace("_", " ").title()
        ),
        venue=str(event.get("venue") or ""),
        url=str(event.get("url") or ""),
        screenings=tuple(upcoming),
    )


def group_by_person(
    events: Sequence[dict],
    *,
    today: date,
    limit: int = DEFAULT_UPCOMING_LIMIT,
    min_events: int = MIN_EVENTS_PER_PERSON,
) -> list[PersonPage]:
    """Group events by person and build renderable ``PersonPage`` records.

    Only people attached to at least ``min_events`` total events (past
    or upcoming) produce a page.
    """
    totals: dict[tuple[str, str], int] = {}
    by_key: dict[tuple[str, str], list[dict]] = {}
    display_name: dict[tuple[str, str], str] = {}
    for event in events:
        if not isinstance(event, dict):
            continue
        for role, name in _people_for_event(event):
            key = (role, name.lower())
            display_name.setdefault(key, name)
            totals[key] = totals.get(key, 0) + 1
            by_key.setdefault(key, []).append(event)

    pages: list[PersonPage] = []
    for key, bucket in by_key.items():
        role, _ = key
        if totals.get(key, 0) < min_events:
            continue
        name = display_name[key]
        person_events: list[PersonEvent] = []
        for event in bucket:
            built = _build_person_event(event, today)
            if built is not None:
                person_events.append(built)
        person_events.sort(
            key=lambda v: (
                v.first_screening.date if v.first_screening else "9999-99-99",
                v.first_screening.time if v.first_screening else "",
                v.title.lower(),
            )
        )
        capped = person_events[:limit] if limit > 0 else person_events
        pages.append(
            PersonPage(
                person_name=name,
                slug=slugify(name),
                role=role,
                description=_role_description(name, role),
                events=tuple(capped),
                total_events=totals[key],
            )
        )
    pages.sort(key=lambda p: (p.role, p.person_name.lower()))
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


def _anchor(event: PersonEvent) -> str:
    if not event.event_id:
        return "../"
    return f"../#event={_esc(event.event_id)}"


def _render_event(event: PersonEvent, ordinal: int) -> str:
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
    if event.venue:
        subtitle_bits.append(event.venue)
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
    event_dom_id = f"person-event-{_esc(event.event_id) or ordinal}"
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


def render_page(page: PersonPage) -> str:
    """Render one person's deep-dive HTML page."""
    role_label = ROLE_LABELS.get(page.role, page.role.title())
    title = f"{page.person_name} — {role_label} — Culture Calendar"
    description_meta = (
        f"Upcoming Austin events featuring {page.person_name} "
        f"({role_label.lower()}). "
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
        f" · {_esc(role_label)}</p>"
    )
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{_esc(title)}</title>\n"
        f'<meta name="description" content="{_esc(description_meta)}">\n'
        '<link rel="stylesheet" href="../styles.css">\n'
        '<link rel="alternate" type="application/rss+xml" title="Culture Calendar" '
        f'href="{_esc(RSS_URL)}">\n'
        "</head>\n"
        '<body class="venue-page">\n'
        '<header class="venue-masthead">\n'
        f'<p class="venue-eyebrow">Culture Calendar · {_esc(role_label)}</p>\n'
        f"<h1>{_esc(page.person_name)}</h1>\n"
        f'<p class="venue-description">{_esc(page.description)}</p>\n'
        f"{count_note}\n"
        '<nav class="venue-actions" aria-label="Person actions">\n'
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
    min_events: int = MIN_EVENTS_PER_PERSON,
) -> list[tuple[Path, PersonPage]]:
    """Write one HTML page per qualifying person. Returns ``(path, page)`` pairs."""
    today = today or datetime.now().date()
    pages = group_by_person(
        events, today=today, limit=limit, min_events=min_events
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[tuple[Path, PersonPage]] = []
    seen_slugs: dict[str, tuple[str, str]] = {}
    for page in pages:
        slug = page.slug or f"{page.role}-unknown"
        # Two distinct names could collapse to the same slug (diacritics,
        # punctuation). Disambiguate by appending the role and, if still
        # colliding, a numeric suffix.
        candidate = slug
        n = 2
        while candidate in seen_slugs and seen_slugs[candidate] != (
            page.role,
            page.person_name,
        ):
            candidate = f"{slug}-{page.role}-{n}"
            n += 1
        seen_slugs[candidate] = (page.role, page.person_name)
        out_path = out_dir / f"{candidate}.html"
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
        help="Output directory for per-person HTML (default: %(default)s).",
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
        help="Maximum upcoming events per person (default: %(default)s).",
    )
    parser.add_argument(
        "--min-events",
        type=int,
        default=MIN_EVENTS_PER_PERSON,
        help="Minimum events required to generate a page (default: %(default)s).",
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
        events,
        out_dir=args.out_dir,
        today=today,
        limit=args.limit,
        min_events=args.min_events,
    )
    if not args.quiet:
        for path, page in written:
            print(
                f"Wrote {path} ({page.role}: {len(page.events)} upcoming of "
                f"{page.total_events})"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
