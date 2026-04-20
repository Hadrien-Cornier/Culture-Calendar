"""Build the "Composer of the Week" feature page under
``docs/features/composer-<yyyy-Www>.html``.

Selects the composer with the most upcoming concert events tracked in
``docs/data.json``, asks :class:`src.llm_service.LLMService` (Perplexity
Sonar with Anthropic fallback) for a short editorial essay, and renders
a standalone HTML page that reuses the site stylesheet.

The generated page lists every upcoming event featuring the chosen
composer with deep-links back to ``../#event=<id>``. When no API key is
configured — or when the LLM call returns nothing — the script degrades
gracefully to a static fallback essay so the page is always produced.

Stdlib only (plus the existing ``src.llm_service`` dependency tree).
See ``scripts/build_weekly_digest.py`` for the companion page these
features link back to.
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
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.llm_service import LLMService  # noqa: E402

DATA_PATH = REPO_ROOT / "docs" / "data.json"
OUT_DIR = REPO_ROOT / "docs" / "features"

SITE_HOST = "hadrien-cornier.github.io"
SITE_PATH = "/Culture-Calendar/"
SITE_URL = f"https://{SITE_HOST}{SITE_PATH}"
RSS_URL = f"{SITE_URL}feed.xml"
TOP_PICKS_WEBCAL = f"webcal://{SITE_HOST}{SITE_PATH}top-picks.ics"

MONTHS_SHORT = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]
WEEKDAY_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Case-insensitive placeholder values we should never treat as a real
# composer name.
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

LOG = logging.getLogger("build_composer_feature")


@dataclass(frozen=True)
class UpcomingEvent:
    """One upcoming concert featuring the chosen composer."""

    event_id: str
    title: str
    rating: Optional[int]
    one_liner: str
    venue: str
    url: str
    first_date: str
    first_time: str


@dataclass(frozen=True)
class ComposerFeature:
    """Everything the renderer needs to emit a feature page."""

    name: str
    upcoming_count: int
    events: tuple[UpcomingEvent, ...]
    essay: str
    tagline: str
    iso_year: int
    iso_week: int
    generated_at: str
    source: str  # "llm" or "fallback"


def _parse_iso_date(value: str) -> Optional[date]:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _clean_name(value: object) -> str:
    if not isinstance(value, str):
        return ""
    stripped = value.strip()
    if stripped.lower() in NAME_BLOCKLIST:
        return ""
    return stripped


def _event_screenings(event: dict) -> list[dict]:
    screenings = event.get("screenings") or []
    if screenings:
        return [s for s in screenings if isinstance(s, dict) and s.get("date")]
    dates = event.get("dates") or []
    times = event.get("times") or []
    default_url = event.get("url") or ""
    default_venue = event.get("venue") or ""
    if dates and times and len(dates) == len(times):
        return [
            {"date": d, "time": t, "url": default_url, "venue": default_venue}
            for d, t in zip(dates, times)
        ]
    if dates:
        return [
            {"date": d, "time": "", "url": default_url, "venue": default_venue}
            for d in dates
        ]
    return []


def _extract_composers(event: dict) -> list[str]:
    """Return cleaned composer names attached to one concert event."""
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


def _first_upcoming(event: dict, today: date) -> Optional[tuple[str, str]]:
    """Return the earliest upcoming (date, time) pair, or None."""
    best: Optional[tuple[str, str]] = None
    for raw in _event_screenings(event):
        sd = _parse_iso_date(str(raw.get("date", "")))
        if sd is None or sd < today:
            continue
        pair = (str(raw.get("date") or ""), str(raw.get("time") or ""))
        if best is None or pair < best:
            best = pair
    return best


def _is_concert_like(event: dict) -> bool:
    kind = str(event.get("type") or "").strip().lower()
    return kind == "concert"


def select_composer(
    events: Sequence[dict], *, today: date
) -> Optional[tuple[str, list[dict]]]:
    """Pick the composer with the most upcoming concert events.

    Returns ``(display_name, [events])`` or ``None`` when no eligible
    composer is tracked (e.g. empty dataset or every concert lists only
    blocklisted names).
    """
    counts: dict[str, int] = {}
    display: dict[str, str] = {}
    buckets: dict[str, list[dict]] = {}
    for event in events:
        if not isinstance(event, dict) or not _is_concert_like(event):
            continue
        if _first_upcoming(event, today) is None:
            continue
        for name in _extract_composers(event):
            key = name.lower()
            display.setdefault(key, name)
            counts[key] = counts.get(key, 0) + 1
            buckets.setdefault(key, []).append(event)
    if not counts:
        return None
    top_key = max(counts, key=lambda k: (counts[k], -len(k), display[k]))
    return display[top_key], buckets[top_key]


def _build_upcoming(event: dict, today: date) -> Optional[UpcomingEvent]:
    first = _first_upcoming(event, today)
    if first is None:
        return None
    title = str(event.get("title") or "").strip()
    if not title:
        return None
    rating = event.get("rating") if isinstance(event.get("rating"), (int, float)) else None
    return UpcomingEvent(
        event_id=str(event.get("id") or ""),
        title=title,
        rating=int(rating) if isinstance(rating, (int, float)) else None,
        one_liner=str(event.get("one_liner_summary") or ""),
        venue=str(event.get("venue") or ""),
        url=str(event.get("url") or ""),
        first_date=first[0],
        first_time=first[1],
    )


def _ordered_upcoming(
    events: Sequence[dict], today: date
) -> tuple[UpcomingEvent, ...]:
    built: list[UpcomingEvent] = []
    seen: set[str] = set()
    for event in events:
        record = _build_upcoming(event, today)
        if record is None:
            continue
        key = record.event_id or f"{record.title}|{record.first_date}|{record.first_time}"
        if key in seen:
            continue
        seen.add(key)
        built.append(record)
    built.sort(key=lambda r: (r.first_date, r.first_time, r.title.lower()))
    return tuple(built)


_ESSAY_SYSTEM_PROMPT = (
    "You are a seasoned classical-music editor writing short editorial "
    "features for an Austin-focused cultural calendar. Write with "
    "authority, warmth, and specificity. Prefer concrete details about "
    "the composer's style, contemporaries, and why their music rewards "
    "live listening today. Avoid filler phrases and refusals. Return "
    "valid JSON only — no prose wrapper, no code fences."
)


def _essay_prompt(composer: str, upcoming: Sequence[UpcomingEvent]) -> str:
    upcoming_lines = "\n".join(
        f"- {ev.title} ({ev.venue or 'venue TBA'}, {ev.first_date})"
        for ev in upcoming[:8]
    ) or "- (no tracked programmes in the current window)"
    return (
        f"Profile the composer {composer!r} for an Austin Culture Calendar "
        "\"Composer of the Week\" feature. Ground the essay in their "
        "musical voice, historical period, and what live audiences should "
        "listen for. Mention — but do not list bullet-style — that their "
        "works are on upcoming Austin programmes below.\n\n"
        f"Upcoming Austin programmes featuring {composer}:\n{upcoming_lines}\n\n"
        "Respond with JSON ONLY in this exact shape: "
        '{"tagline": "<one sentence, <= 20 words>", '
        '"essay": "<4 to 6 short paragraphs separated by double newlines, '
        "180 to 320 words total, no Markdown, no HTML>\"}."
    )


def _fallback_essay(composer: str, upcoming: Sequence[UpcomingEvent]) -> tuple[str, str]:
    count = len(upcoming)
    venues = sorted({ev.venue for ev in upcoming if ev.venue})
    venue_str = ", ".join(venues) if venues else "Austin stages"
    programme_preview = "; ".join(ev.title for ev in upcoming[:3])
    tagline = (
        f"{composer} returns to Austin stages with {count} upcoming programme"
        f"{'s' if count != 1 else ''} tracked by Culture Calendar."
    )
    essay = (
        f"{composer} anchors this week's Culture Calendar feature with "
        f"{count} upcoming Austin programme{'s' if count != 1 else ''}, "
        f"reaching listeners across {venue_str}.\n\n"
        "An LLM-generated editorial essay was unavailable when this page "
        "was built, so the programme index below is the authoritative "
        "guide. Each entry links back to the main calendar with its AI "
        "rating, one-line hook, and venue details intact.\n\n"
        f"Highlights to scan for: {programme_preview}.\n\n"
        "Subscribe to the weekly digest webcal feed at the top of the page "
        "to keep this composer's appearances on your calendar as new "
        "programmes are scraped."
    )
    return tagline, essay


def _call_llm_for_essay(
    llm: LLMService, composer: str, upcoming: Sequence[UpcomingEvent]
) -> Optional[tuple[str, str]]:
    """Ask the LLM for a tagline + essay JSON payload."""
    try:
        response = llm.call_perplexity(
            _essay_prompt(composer, upcoming), temperature=0.4
        )
    except Exception as exc:  # pragma: no cover - defensive: stay exit-0
        LOG.warning("LLM call raised: %s", exc)
        return None
    if not isinstance(response, dict):
        return None
    essay = response.get("essay")
    tagline = response.get("tagline") or ""
    if not isinstance(essay, str) or len(essay.strip()) < 40:
        return None
    return str(tagline).strip(), essay.strip()


def build_feature(
    events: Sequence[dict],
    *,
    today: date,
    llm: Optional[LLMService] = None,
) -> Optional[ComposerFeature]:
    """Compose a full :class:`ComposerFeature` ready for rendering."""
    pick = select_composer(events, today=today)
    if pick is None:
        return None
    composer_name, bucket = pick
    upcoming = _ordered_upcoming(bucket, today)
    if not upcoming:
        return None
    service = llm if llm is not None else LLMService()
    pair = _call_llm_for_essay(service, composer_name, upcoming)
    if pair is None:
        tagline, essay = _fallback_essay(composer_name, upcoming)
        source = "fallback"
    else:
        tagline, essay = pair
        source = "llm"
    iso = today.isocalendar()
    return ComposerFeature(
        name=composer_name,
        upcoming_count=len(upcoming),
        events=upcoming,
        essay=essay,
        tagline=tagline,
        iso_year=iso.year,
        iso_week=iso.week,
        generated_at=datetime.now().replace(microsecond=0).isoformat(),
        source=source,
    )


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


def _format_when(date_str: str, time_str: str) -> str:
    sd = _parse_iso_date(date_str)
    if sd is None:
        base = date_str or ""
    else:
        base = f"{WEEKDAY_SHORT[sd.weekday()]}, {MONTHS_SHORT[sd.month - 1]} {sd.day}"
    tpart = _format_time(time_str)
    return f"{base} \u00b7 {tpart}" if tpart else base


def _anchor(event: UpcomingEvent) -> str:
    if not event.event_id:
        return "../"
    return f"../#event={_esc(event.event_id)}"


def _render_essay(essay: str) -> str:
    paragraphs = [p.strip() for p in essay.split("\n\n") if p.strip()]
    if not paragraphs:
        return ""
    return "".join(
        f'<p class="feature-essay-p">{_esc(p)}</p>' for p in paragraphs
    )


def _render_event(event: UpcomingEvent, ordinal: int) -> str:
    rating_html = ""
    if event.rating is not None:
        rating_html = (
            f'<span class="venue-rating" aria-label="rated {event.rating} out of 10">'
            f"{event.rating} / 10</span>"
        )
    subtitle_bits: list[str] = [
        _format_when(event.first_date, event.first_time),
    ]
    if event.venue:
        subtitle_bits.append(event.venue)
    subtitle_text = " \u00b7 ".join(_esc(b) for b in subtitle_bits if b)
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
    event_dom_id = f"feature-event-{_esc(event.event_id) or ordinal}"
    return (
        f'<li class="venue-event" id="{event_dom_id}">'
        f'<article class="venue-event-article">'
        f'<header class="venue-event-header">'
        f'<div class="venue-event-rank" aria-hidden="true">{ordinal:02d}</div>'
        f"{rating_html}"
        f'<h2 class="venue-event-title">'
        f'<a href="{_anchor(event)}">{_esc(event.title)}</a>'
        f"</h2>"
        f"{subtitle_html}"
        f"</header>"
        f"{one_liner_html}"
        f"</article>"
        f"</li>"
    )


def render_page(feature: ComposerFeature) -> str:
    iso_label = f"{feature.iso_year:04d}-W{feature.iso_week:02d}"
    title = f"Composer of the Week: {feature.name} \u2014 Culture Calendar"
    description_meta = (
        f"{feature.name} is Culture Calendar's Composer of the Week for "
        f"{iso_label} with {feature.upcoming_count} upcoming Austin "
        f"programme{'s' if feature.upcoming_count != 1 else ''}."
    )
    events_html = "\n".join(
        _render_event(ev, i + 1) for i, ev in enumerate(feature.events)
    )
    events_block = (
        f'<ol class="venue-events">{events_html}</ol>'
        if feature.events
        else (
            '<p class="venue-empty">No upcoming events tracked. '
            '<a href="../">Browse the full calendar</a>.</p>'
        )
    )
    source_note = (
        "LLM-generated"
        if feature.source == "llm"
        else "Static fallback (LLM unavailable)"
    )
    tagline_html = (
        f'<p class="feature-tagline">{_esc(feature.tagline)}</p>'
        if feature.tagline
        else ""
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
        '<body class="venue-page feature-page">\n'
        '<header class="weekly-masthead">\n'
        f'<p class="weekly-eyebrow">Composer of the Week \u00b7 {_esc(iso_label)}</p>\n'
        f"<h1>{_esc(feature.name)}</h1>\n"
        f"{tagline_html}\n"
        '<nav class="weekly-actions" aria-label="Feature actions">\n'
        '<a href="../">\u2190 Back to Calendar</a>\n'
        f'<a href="{_esc(TOP_PICKS_WEBCAL)}">Subscribe (webcal)</a>\n'
        f'<a href="{_esc(RSS_URL)}">RSS</a>\n'
        "</nav>\n"
        "</header>\n"
        '<main class="weekly-main">\n'
        '<section class="feature-essay">\n'
        f"{_render_essay(feature.essay)}\n"
        "</section>\n"
        '<section class="feature-programme">\n'
        f'<h2 class="feature-programme-heading">Upcoming programmes featuring {_esc(feature.name)}</h2>\n'
        f"{events_block}\n"
        "</section>\n"
        "</main>\n"
        '<footer class="weekly-footer">\n'
        f'<p class="feature-meta">{_esc(source_note)} \u00b7 generated {_esc(feature.generated_at)}</p>\n'
        '<p><a href="../">Culture Calendar</a> \u00b7 AI-curated Austin cultural events</p>\n'
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


def write_feature(
    events: Sequence[dict],
    *,
    today: date,
    out_dir: Path = OUT_DIR,
    llm: Optional[LLMService] = None,
) -> Optional[tuple[Path, ComposerFeature]]:
    """Build the feature and write the HTML file. Returns ``(path, feature)``."""
    feature = build_feature(events, today=today, llm=llm)
    if feature is None:
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    iso_label = f"{feature.iso_year:04d}-W{feature.iso_week:02d}"
    out_path = out_dir / f"composer-{iso_label}.html"
    out_path.write_text(render_page(feature), encoding="utf-8")
    return out_path, feature


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
        help="Output directory for feature HTML (default: %(default)s).",
    )
    parser.add_argument(
        "--today",
        type=str,
        default=None,
        help="Override reference date (ISO format). Defaults to today.",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Skip the LLM call and use the static fallback essay.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-file summary line on stdout.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    events = load_events(args.data)
    today = datetime.now().date()
    if args.today:
        parsed = _parse_iso_date(args.today)
        if parsed is None:
            parser.error(f"--today must be YYYY-MM-DD, got {args.today!r}")
        today = parsed

    llm: Optional[LLMService]
    if args.offline:
        llm = None
    else:
        try:
            llm = LLMService()
        except Exception as exc:  # pragma: no cover - defensive only
            LOG.warning("LLMService init failed, falling back: %s", exc)
            llm = None

    if llm is None:
        # Pass a stub whose call_perplexity returns None so we fall through
        # to the static template without touching the network.
        class _Stub:
            def call_perplexity(self, *args, **kwargs):
                return None

        stub: LLMService = _Stub()  # type: ignore[assignment]
        result = write_feature(events, today=today, out_dir=args.out_dir, llm=stub)
    else:
        result = write_feature(events, today=today, out_dir=args.out_dir, llm=llm)

    if result is None:
        print(
            "No eligible composer found (no upcoming concert events with "
            "named composers).",
            file=sys.stderr,
        )
        # Still write a placeholder page so downstream sitemap links resolve.
        iso = today.isocalendar()
        iso_label = f"{iso.year:04d}-W{iso.week:02d}"
        args.out_dir.mkdir(parents=True, exist_ok=True)
        placeholder = args.out_dir / f"composer-{iso_label}.html"
        placeholder.write_text(
            "<!DOCTYPE html>\n<html lang=\"en\"><head>"
            "<meta charset=\"utf-8\"><title>Composer of the Week — Culture Calendar</title>"
            "<link rel=\"stylesheet\" href=\"../styles.css\"></head>"
            "<body class=\"venue-page feature-page\"><main class=\"weekly-main\">"
            "<p class=\"venue-empty\">No eligible composer this week. "
            "<a href=\"../\">Browse the calendar</a>.</p>"
            "</main></body></html>\n",
            encoding="utf-8",
        )
        if not args.quiet:
            print(f"Wrote {placeholder} (placeholder — no eligible composer)")
        return 0

    path, feature = result
    if not args.quiet:
        print(
            f"Wrote {path} ({feature.name}, "
            f"{feature.upcoming_count} events, source={feature.source})"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
