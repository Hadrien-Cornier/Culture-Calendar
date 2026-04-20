"""Build subscribable ICS feeds from ``docs/data.json``.

Produces two RFC 5545 files published alongside the static site:

* ``docs/calendar.ics`` — every screening of every event.
* ``docs/top-picks.ics`` — only screenings of events with
  ``rating >= TOP_PICK_MIN_RATING`` (7).

Both feeds are safe to expose as ``webcal://…`` URLs: they carry no
secrets and are regenerated end-to-end on every build (no diff merging).

Patterns adapted from :class:`src.calendar_generator.CalendarGenerator`.
The on-demand generator there takes a flat list of ``{date, time}``
events; the long-run data file keeps a ``screenings: [{date, time,
url, venue}]`` array per event, so this module fans them out into one
VEVENT per screening.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Optional, Sequence

import pytz
from icalendar import Calendar, Event, Timezone, TimezoneDaylight, TimezoneStandard

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = REPO_ROOT / "docs" / "data.json"
OUT_ALL = REPO_ROOT / "docs" / "calendar.ics"
OUT_TOP = REPO_ROOT / "docs" / "top-picks.ics"

AUSTIN_TZ = pytz.timezone("America/Chicago")
TOP_PICK_MIN_RATING = 7
DEFAULT_DURATION = timedelta(hours=2)
UID_DOMAIN = "culturecalendar.local"

LOG = logging.getLogger("build_ics_feed")


@dataclass(frozen=True)
class Screening:
    """One concrete showing of an event at a specific date/time."""

    event_id: str
    title: str
    rating: Optional[int]
    one_liner: str
    description_html: str
    type_: str
    venue: str
    date: str
    time: str
    url: str


def _iter_screenings(events: Sequence[dict]) -> Iterable[Screening]:
    """Flatten events × screenings into individual :class:`Screening` rows."""
    for event in events:
        if not isinstance(event, dict):
            continue
        event_id = event.get("id") or event.get("title") or ""
        title = event.get("title") or "Untitled"
        rating = event.get("rating")
        one_liner = event.get("one_liner_summary") or ""
        description_html = event.get("description") or ""
        type_ = event.get("type") or "other"
        default_venue = event.get("venue") or ""
        default_url = event.get("url") or ""

        screenings = event.get("screenings") or []
        if not screenings and event.get("dates") and event.get("times"):
            screenings = [
                {"date": d, "time": t, "venue": default_venue, "url": default_url}
                for d, t in zip(event["dates"], event["times"])
            ]

        for s in screenings:
            if not isinstance(s, dict):
                continue
            date_str = s.get("date")
            time_str = s.get("time")
            if not date_str or not time_str:
                continue
            yield Screening(
                event_id=event_id,
                title=title,
                rating=rating,
                one_liner=one_liner,
                description_html=description_html,
                type_=type_,
                venue=s.get("venue") or default_venue,
                date=date_str,
                time=time_str,
                url=s.get("url") or default_url,
            )


def _parse_datetime(date_str: str, time_str: str) -> Optional[datetime]:
    """Parse ``YYYY-MM-DD`` + ``HH:mm`` (or ``H:MM AM/PM``) into Austin tz."""
    try:
        base = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        LOG.warning("Unparseable date %r; skipping", date_str)
        return None

    hour = minute = None
    cleaned = time_str.strip().upper().replace(" ", "")
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
            LOG.warning("Unparseable 12h time %r; skipping", time_str)
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
            LOG.warning("Unparseable 24h time %r; skipping", time_str)
            return None

    if not (0 <= hour < 24 and 0 <= minute < 60):
        return None

    naive = base.replace(hour=hour, minute=minute)
    return AUSTIN_TZ.localize(naive)


def _category_tags(type_: str) -> list[str]:
    mapping = {
        "movie": ["Movie", "Film"],
        "concert": ["Concert", "Music"],
        "opera": ["Opera", "Music"],
        "book_club": ["Book Club", "Literature"],
        "visual_arts": ["Visual Arts", "Exhibition"],
        "other": ["Event"],
    }
    return mapping.get(type_, ["Event"])


def _build_description(screening: Screening) -> str:
    parts: list[str] = []
    if screening.rating is not None:
        parts.append(f"Rating: {screening.rating}/10")
    if screening.one_liner:
        parts.append(screening.one_liner)
    if screening.url:
        parts.append(f"Details: {screening.url}")
    return "\n\n".join(parts)


def _build_uid(screening: Screening) -> str:
    sanitized_time = screening.time.replace(":", "").replace(" ", "")
    base = screening.event_id or "event"
    return f"{base}-{screening.date}-{sanitized_time}@{UID_DOMAIN}"


def _create_timezone() -> Timezone:
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


def _screening_to_vevent(
    screening: Screening, *, stamp: datetime
) -> Optional[Event]:
    start = _parse_datetime(screening.date, screening.time)
    if start is None:
        return None

    vevent = Event()
    vevent.add("uid", _build_uid(screening))
    vevent.add("dtstamp", stamp)
    vevent.add("dtstart", start)
    vevent.add("dtend", start + DEFAULT_DURATION)

    summary = screening.title
    if screening.rating is not None:
        summary = f"[{screening.rating}/10] {summary}"
    vevent.add("summary", summary)
    vevent.add("description", _build_description(screening))
    if screening.venue:
        vevent.add("location", screening.venue)
    if screening.url:
        vevent.add("url", screening.url)
    vevent.add("categories", _category_tags(screening.type_))
    return vevent


def build_calendar(
    screenings: Iterable[Screening],
    *,
    cal_name: str,
    cal_desc: str,
    stamp: Optional[datetime] = None,
) -> Calendar:
    """Assemble an :class:`icalendar.Calendar` from screenings."""
    stamp = stamp or datetime.now(AUSTIN_TZ)

    cal = Calendar()
    cal.add("prodid", "-//Culture Calendar//Austin Events//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", cal_name)
    cal.add("x-wr-caldesc", cal_desc)
    cal.add("x-wr-timezone", "America/Chicago")
    cal.add_component(_create_timezone())

    for screening in screenings:
        try:
            vevent = _screening_to_vevent(screening, stamp=stamp)
        except Exception as exc:  # pragma: no cover - defensive
            LOG.warning("Failed to build VEVENT for %s: %s", screening.title, exc)
            continue
        if vevent is not None:
            cal.add_component(vevent)

    return cal


def load_events(data_path: Path = DATA_PATH) -> list[dict]:
    if not data_path.exists():
        raise FileNotFoundError(f"Missing data file: {data_path}")
    with data_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, list):
        raise ValueError(f"{data_path} is not a JSON array")
    return payload


def write_feeds(
    events: Sequence[dict],
    *,
    all_out: Path = OUT_ALL,
    top_out: Path = OUT_TOP,
    min_rating: int = TOP_PICK_MIN_RATING,
    stamp: Optional[datetime] = None,
) -> tuple[int, int]:
    """Render both feeds. Returns ``(all_count, top_count)`` VEVENT totals."""
    all_screenings = list(_iter_screenings(events))
    top_screenings = [
        s for s in all_screenings if s.rating is not None and s.rating >= min_rating
    ]

    all_cal = build_calendar(
        all_screenings,
        cal_name="Culture Calendar — Austin",
        cal_desc="All AI-curated Austin cultural events",
        stamp=stamp,
    )
    top_cal = build_calendar(
        top_screenings,
        cal_name="Culture Calendar — Top Picks",
        cal_desc=f"Events rated {min_rating}+ of 10 by Culture Calendar",
        stamp=stamp,
    )

    all_out.parent.mkdir(parents=True, exist_ok=True)
    all_out.write_bytes(all_cal.to_ical())
    top_out.write_bytes(top_cal.to_ical())

    all_count = sum(1 for c in all_cal.subcomponents if c.name == "VEVENT")
    top_count = sum(1 for c in top_cal.subcomponents if c.name == "VEVENT")
    return all_count, top_count


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--data",
        type=Path,
        default=DATA_PATH,
        help="Path to docs/data.json (default: %(default)s).",
    )
    parser.add_argument(
        "--all-out",
        type=Path,
        default=OUT_ALL,
        help="Output path for the all-events feed.",
    )
    parser.add_argument(
        "--top-out",
        type=Path,
        default=OUT_TOP,
        help="Output path for the top-picks feed.",
    )
    parser.add_argument(
        "--min-rating",
        type=int,
        default=TOP_PICK_MIN_RATING,
        help="Minimum rating for the top-picks feed (default: %(default)s).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress the summary line on stdout.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    events = load_events(args.data)
    all_count, top_count = write_feeds(
        events,
        all_out=args.all_out,
        top_out=args.top_out,
        min_rating=args.min_rating,
    )

    if not args.quiet:
        print(
            f"Wrote {args.all_out} ({all_count} events) "
            f"and {args.top_out} ({top_count} events, rating>={args.min_rating})"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
