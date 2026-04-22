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
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional, Sequence

import pytz
from icalendar import Calendar, Event, Timezone, TimezoneDaylight, TimezoneStandard

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = REPO_ROOT / "docs" / "data.json"
OUT_DIR = REPO_ROOT / "docs" / "people"

SITE_HOST = "hadrien-cornier.github.io"
SITE_PATH = "/Culture-Calendar/"
SITE_URL = f"https://{SITE_HOST}{SITE_PATH}"
RSS_URL = f"{SITE_URL}feed.xml"
TOP_PICKS_WEBCAL = f"webcal://{SITE_HOST}{SITE_PATH}top-picks.ics"
PEOPLE_WEBCAL_BASE = f"webcal://{SITE_HOST}{SITE_PATH}people/"

DEFAULT_UPCOMING_LIMIT = 40
MIN_EVENTS_PER_PERSON = 2
DEFAULT_ICS_DURATION = timedelta(hours=2)
AUSTIN_TZ = pytz.timezone("America/Chicago")
UID_DOMAIN = "culturecalendar.local"

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
# person name (and therefore never create a page for). Exact matches after
# lowercasing + stripping.
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

# Substrings that, if present anywhere in the lowercased name, mark it as a
# programme-note placeholder rather than a real person. These catch entries
# like ``various medieval composers``, ``various troubadour composers``,
# ``scottish songs`` (a genre, not a composer), ``consort of viols`` (an
# ensemble type), or ``various england/france/italy`` (a regional label).
NAME_SUBSTRING_BLOCKLIST: tuple[str, ...] = (
    "various",
    "consort of",
    "ensemble",
    "scottish songs",
    "british lowland composers",
    "troubadour composers",
    "medieval composers",
    "england/france",
)

# Canonical-name aliases: the key is the display form encountered in the
# data, the value is the canonical full name we should write pages under.
# Prevents a composer from getting two pages (``beethoven.html`` and
# ``ludwig-van-beethoven.html``) which would split SEO weight in half.
NAME_ALIASES: dict[str, str] = {
    "beethoven": "Ludwig van Beethoven",
    "haydn": "Joseph Haydn",
    "mozart": "Wolfgang Amadeus Mozart",
    "bach": "Johann Sebastian Bach",
    "schubert": "Franz Schubert",
    "brahms": "Johannes Brahms",
    "purcell": "Henry Purcell",
    "telemann": "Georg Philipp Telemann",
    "mendelssohn": "Felix Mendelssohn",
    "gershwin": "George Gershwin",
    "verdi": "Giuseppe Verdi",
    "puccini": "Giacomo Puccini",
    "saint-saens": "Camille Saint-Saëns",
    "saint saens": "Camille Saint-Saëns",
    "copland": "Aaron Copland",
    "bernstein": "Leonard Bernstein",
}

LOG = logging.getLogger("build_people_pages")

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def _canonicalise(name: str) -> str:
    """Expand a bare surname like ``"Beethoven"`` to its canonical full form.

    Keeps already-qualified names unchanged. Case-insensitive lookup.
    """
    if not name:
        return name
    stripped = name.strip()
    alias = NAME_ALIASES.get(stripped.lower())
    return alias if alias else stripped


def slugify(name: str) -> str:
    """Lowercase, ASCII-folded, hyphen-separated slug.

    ``"Camille Saint-Saëns"`` → ``"camille-saint-saens"`` (diacritics
    stripped via NFKD before the non-alnum replacement).
    """
    if not name:
        return ""
    normalised = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    lowered = normalised.strip().lower()
    slug = _SLUG_STRIP.sub("-", lowered)
    return slug.strip("-")


def _clean_name(value: object) -> str:
    """Normalise, reject placeholders, canonicalise aliases."""
    if not isinstance(value, str):
        return ""
    stripped = value.strip()
    lowered = stripped.lower()
    if lowered in NAME_BLOCKLIST:
        return ""
    for needle in NAME_SUBSTRING_BLOCKLIST:
        if needle in lowered:
            return ""
    return _canonicalise(stripped)


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


def render_page(page: PersonPage, *, ics_slug: Optional[str] = None) -> str:
    """Render one person's deep-dive HTML page.

    ``ics_slug`` is the filename stem used for the companion ``.ics``
    feed (defaults to ``page.slug``). ``write_pages`` overrides it when
    slug-collision disambiguation kicks in so the webcal link points at
    the actual file on disk.
    """
    role_label = ROLE_LABELS.get(page.role, page.role.title())
    title = f"{page.person_name} — {role_label} — Culture Calendar"
    description_meta = (
        f"Upcoming Austin events featuring {page.person_name} "
        f"({role_label.lower()}). "
        f"{len(page.events)} upcoming of {page.total_events} tracked."
    )
    person_webcal = (
        f"{PEOPLE_WEBCAL_BASE}{_esc(ics_slug or page.slug)}.ics"
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
    canonical = f"{SITE_URL}people/{ics_slug or page.slug}.html"
    breadcrumb_json = _breadcrumb_jsonld(
        (
            ("Culture Calendar", SITE_URL),
            ("People", f"{SITE_URL}people/"),
            (page.person_name, canonical),
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
        f'<p class="venue-eyebrow">Culture Calendar · {_esc(role_label)}</p>\n'
        f"<h1>{_esc(page.person_name)}</h1>\n"
        f'<p class="venue-description">{_esc(page.description)}</p>\n'
        f"{count_note}\n"
        '<nav class="venue-actions" aria-label="Person actions">\n'
        '<a href="../">← Back to Calendar</a>\n'
        f'<a href="{_esc(RSS_URL)}">RSS</a>\n'
        f'<a class="person-webcal" href="{person_webcal}">Follow (webcal)</a>\n'
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


def _parse_ics_datetime(date_str: str, time_str: str) -> Optional[datetime]:
    """Parse ``YYYY-MM-DD`` + ``HH:mm`` (or ``H:MM AM/PM``) into Austin tz."""
    try:
        base = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return None

    cleaned = (time_str or "").strip().upper().replace(" ", "")
    if not cleaned:
        return None

    hour: Optional[int] = None
    minute: Optional[int] = None
    if cleaned.endswith("PM") or cleaned.endswith("AM"):
        suffix = cleaned[-2:]
        core = cleaned[:-2]
        try:
            if ":" in core:
                h, m = core.split(":")
                hour, minute = int(h), int(m)
            else:
                hour, minute = int(core), 0
        except ValueError:
            return None
        if suffix == "PM" and hour != 12:
            hour += 12
        if suffix == "AM" and hour == 12:
            hour = 0
    else:
        try:
            h, m = cleaned.split(":")
            hour, minute = int(h), int(m)
        except ValueError:
            return None

    if hour is None or minute is None:
        return None
    if not (0 <= hour < 24 and 0 <= minute < 60):
        return None
    return AUSTIN_TZ.localize(base.replace(hour=hour, minute=minute))


def _ics_timezone() -> Timezone:
    """VTIMEZONE component for America/Chicago (CST/CDT)."""
    tz = Timezone()
    tz.add("tzid", "America/Chicago")

    standard = TimezoneStandard()
    standard.add("dtstart", datetime(1970, 11, 1, 2, 0, 0))
    standard.add("rrule", {"freq": "yearly", "bymonth": 11, "byday": "1su"})
    standard.add("tzoffsetfrom", timedelta(hours=-5))
    standard.add("tzoffsetto", timedelta(hours=-6))
    standard.add("tzname", "CST")

    daylight = TimezoneDaylight()
    daylight.add("dtstart", datetime(1970, 3, 8, 2, 0, 0))
    daylight.add("rrule", {"freq": "yearly", "bymonth": 3, "byday": "2su"})
    daylight.add("tzoffsetfrom", timedelta(hours=-6))
    daylight.add("tzoffsetto", timedelta(hours=-5))
    daylight.add("tzname", "CDT")

    tz.add_component(standard)
    tz.add_component(daylight)
    return tz


def _ics_uid(slug: str, event: PersonEvent, screening: UpcomingScreening) -> str:
    sanitized_time = screening.time.replace(":", "").replace(" ", "")
    base = event.event_id or slugify(event.title) or "event"
    return f"{slug}-{base}-{screening.date}-{sanitized_time}@{UID_DOMAIN}"


def _ics_vevent(
    slug: str,
    event: PersonEvent,
    screening: UpcomingScreening,
    *,
    stamp: datetime,
) -> Optional[Event]:
    start = _parse_ics_datetime(screening.date, screening.time)
    if start is None:
        return None

    vevent = Event()
    vevent.add("uid", _ics_uid(slug, event, screening))
    vevent.add("dtstamp", stamp)
    vevent.add("dtstart", start)
    vevent.add("dtend", start + DEFAULT_ICS_DURATION)

    summary = event.title
    if event.rating is not None:
        summary = f"[{event.rating}/10] {summary}"
    vevent.add("summary", summary)

    description_parts: list[str] = []
    if event.rating is not None:
        description_parts.append(f"Rating: {event.rating}/10")
    if event.one_liner:
        description_parts.append(event.one_liner)
    if screening.url:
        description_parts.append(f"Details: {screening.url}")
    elif event.url:
        description_parts.append(f"Details: {event.url}")
    if description_parts:
        vevent.add("description", "\n\n".join(description_parts))

    if event.venue:
        vevent.add("location", event.venue)
    link_url = screening.url or event.url
    if link_url:
        vevent.add("url", link_url)
    if event.category_label:
        vevent.add("categories", [event.category_label])
    return vevent


def render_person_ics(
    page: PersonPage, *, stamp: Optional[datetime] = None
) -> bytes:
    """Render a per-person iCalendar feed containing only upcoming events.

    People with no upcoming screenings still get a well-formed calendar
    so the advertised ``webcal://…`` URL resolves.
    """
    stamp = stamp or datetime.now(AUSTIN_TZ)
    role_label = ROLE_LABELS.get(page.role, page.role.title())

    cal = Calendar()
    cal.add("prodid", "-//Culture Calendar//Austin Events//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", f"Culture Calendar — {page.person_name}")
    cal.add(
        "x-wr-caldesc",
        f"Upcoming Austin events featuring {page.person_name} ({role_label.lower()})",
    )
    cal.add("x-wr-timezone", "America/Chicago")
    cal.add_component(_ics_timezone())

    for event in page.events:
        for screening in event.screenings:
            vevent = _ics_vevent(page.slug, event, screening, stamp=stamp)
            if vevent is not None:
                cal.add_component(vevent)
    return cal.to_ical()


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
    stamp: Optional[datetime] = None,
) -> list[tuple[Path, PersonPage]]:
    """Write one HTML page + companion ``.ics`` per qualifying person.

    Returns ``(html_path, page)`` pairs. The ``.ics`` sibling lives at
    ``<html_path>.with_suffix('.ics')`` and carries only the upcoming
    screenings already collected on ``page``.
    """
    today = today or datetime.now().date()
    pages = group_by_person(
        events, today=today, limit=limit, min_events=min_events
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    ics_stamp = stamp or datetime.now(AUSTIN_TZ)
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
        html_path = out_dir / f"{candidate}.html"
        html_path.write_text(
            render_page(page, ics_slug=candidate), encoding="utf-8"
        )
        ics_path = out_dir / f"{candidate}.ics"
        ics_path.write_bytes(render_person_ics(page, stamp=ics_stamp))
        written.append((html_path, page))
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
