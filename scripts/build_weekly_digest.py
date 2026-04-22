"""Build a static weekly digest page under ``docs/weekly/<iso-week>.html``.

Selects every event with at least one screening falling inside the
target ISO week (Monday through Sunday, inclusive), ranks by rating,
and renders a standalone HTML page that re-uses the site stylesheet.
Reproduces the section-aware review layout from ``docs/script.js`` —
see the ``parseReview`` function at script.js:561-587 and its
consumer at script.js:1189-1216 — so the digest mirrors how the main
site presents expanded reviews.

Stdlib only. See ``scripts/build_ics_feed.py`` for the companion
webcal feed linked from the digest.
"""

from __future__ import annotations

import argparse
import html
import json
import logging
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = REPO_ROOT / "docs" / "data.json"
OUT_DIR = REPO_ROOT / "docs" / "weekly"

SITE_HOST = "hadrien-cornier.github.io"
SITE_PATH = "/Culture-Calendar/"
SITE_URL = f"https://{SITE_HOST}{SITE_PATH}"
TOP_PICKS_WEBCAL = f"webcal://{SITE_HOST}{SITE_PATH}top-picks.ics"
TOP_PICKS_HTTPS = f"{SITE_URL}top-picks.ics"
RSS_URL = f"{SITE_URL}feed.xml"
DEFAULT_PICK_LIMIT = 20

# Footer signup form — mirrors the class contract from docs/index.html:33-40
# so the shared ../styles.css styles it consistently. Digest pages don't load
# script.js, so the form degrades gracefully to a GET against the main site's
# #signup-form anchor, where the live JS handler (initSignupForm) takes over.
SIGNUP_FORM_BLOCK = (
    '<form class="signup-form" aria-label="Subscribe to the weekly tipsheet" '
    'action="../#signup-form" method="get" novalidate>'
    '<label class="signup-form-label" for="weekly-digest-email">'
    "Get the weekly tipsheet by email"
    "</label>"
    '<div class="signup-form-row">'
    '<input type="email" id="weekly-digest-email" name="email" '
    'class="signup-form-input" placeholder="you@example.com" '
    'autocomplete="email" required>'
    '<button type="submit" class="signup-form-button">Subscribe</button>'
    "</div>"
    "</form>"
)

CATEGORY_LABELS = {
    "movie": "Film",
    "concert": "Concert",
    "opera": "Opera",
    "dance": "Dance",
    "book_club": "Books",
    "visual_arts": "Visual Arts",
    "other": "Event",
}
MONTHS_LONG = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
MONTHS_SHORT = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]
WEEKDAY_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

_P_BLOCK = re.compile(r"<p[^>]*>(.*?)</p>", re.DOTALL | re.IGNORECASE)
_STRONG_BLOCK = re.compile(r"<strong[^>]*>(.*?)</strong>", re.DOTALL | re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")
_RATING_LINE = re.compile(r"^★\s*Rating:\s*(\d+(?:\.\d+)?)\s*/\s*10", re.IGNORECASE)
_ISO_WEEK = re.compile(r"^(\d{4})-W(\d{2})$")

LOG = logging.getLogger("build_weekly_digest")


@dataclass(frozen=True)
class ReviewSection:
    """One labelled section of a parsed AI review."""

    emoji: str
    label: str
    body: str


@dataclass(frozen=True)
class ParsedReview:
    """Parsed review: optional rating and ordered labelled sections."""

    rating: Optional[str]
    sections: tuple[ReviewSection, ...]


@dataclass(frozen=True)
class WeekScreening:
    """A single screening that lands inside the target ISO week."""

    date: str
    time: str
    venue: str
    url: str


@dataclass(frozen=True)
class DigestPick:
    """One ranked event on the weekly digest page."""

    event_id: str
    title: str
    rating: Optional[int]
    one_liner: str
    description_html: str
    review: ParsedReview
    category_label: str
    venue: str
    url: str
    in_week: tuple[WeekScreening, ...] = field(default_factory=tuple)


def _strip_html(fragment: str) -> str:
    return _TAG.sub("", fragment or "").strip()


def _leading_emoji(text: str) -> str:
    """Return the leading emoji-ish run of the string.

    Approximates the JS regex ``[\\p{Extended_Pictographic}\\p{Emoji}]+``
    by treating any leading non-ASCII, non-alphanumeric run as emoji.
    Good enough for the small symbol set used in AI reviews (★, 🎭, ✨, 📚, 💡).
    """
    if not text:
        return ""
    out_chars: list[str] = []
    for ch in text:
        if ch.isspace():
            break
        if ord(ch) < 128 and ch.isalnum():
            break
        out_chars.append(ch)
    return "".join(out_chars)


def parse_review(description_html: Optional[str]) -> ParsedReview:
    """Port of ``parseReview`` from ``docs/script.js:561-587``."""
    if not description_html:
        return ParsedReview(rating=None, sections=())
    rating: Optional[str] = None
    sections: list[ReviewSection] = []
    for raw in _P_BLOCK.findall(description_html):
        text = _strip_html(raw)
        if not text:
            continue
        m_rating = _RATING_LINE.match(text)
        if m_rating:
            rating = m_rating.group(1)
            continue
        label = ""
        strong_match = _STRONG_BLOCK.search(raw)
        if strong_match:
            label = _strip_html(strong_match.group(1))
        body = text
        if label:
            idx = text.find(label)
            if idx >= 0:
                tail = text[idx + len(label):]
                body = tail.lstrip(" \u2013\u2014-:\t\n").strip()
        emoji = _leading_emoji(text)
        if label or body:
            sections.append(ReviewSection(emoji=emoji, label=label, body=body))
    return ParsedReview(rating=rating, sections=tuple(sections))


def iso_week_from_date(d: date) -> tuple[int, int]:
    iso = d.isocalendar()
    return iso.year, iso.week


def iso_week_label(year: int, week: int) -> str:
    return f"{year:04d}-W{week:02d}"


def iso_week_range(year: int, week: int) -> tuple[date, date]:
    """Return (Monday, Sunday) inclusive for an ISO week."""
    monday = date.fromisocalendar(year, week, 1)
    sunday = monday + timedelta(days=6)
    return monday, sunday


def parse_iso_week_arg(raw: str) -> tuple[int, int]:
    m = _ISO_WEEK.match(raw.strip())
    if not m:
        raise ValueError(f"Expected ISO week format YYYY-Www, got {raw!r}")
    year = int(m.group(1))
    week = int(m.group(2))
    # Validate by round-tripping through fromisocalendar.
    date.fromisocalendar(year, week, 1)
    return year, week


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
    default_venue = event.get("venue") or ""
    default_url = event.get("url") or ""
    if dates and times and len(dates) == len(times):
        return [
            {"date": d, "time": t, "venue": default_venue, "url": default_url}
            for d, t in zip(dates, times)
        ]
    if dates:
        return [
            {"date": d, "time": "", "venue": default_venue, "url": default_url}
            for d in dates
        ]
    return []


def _screenings_in_week(
    event: dict, monday: date, sunday: date
) -> list[WeekScreening]:
    out: list[WeekScreening] = []
    for raw in _event_screenings(event):
        sd = _parse_iso_date(str(raw.get("date", "")))
        if sd is None:
            continue
        if sd < monday or sd > sunday:
            continue
        out.append(
            WeekScreening(
                date=str(raw.get("date") or ""),
                time=str(raw.get("time") or ""),
                venue=str(raw.get("venue") or event.get("venue") or ""),
                url=str(raw.get("url") or event.get("url") or ""),
            )
        )
    out.sort(key=lambda s: (s.date, s.time))
    return out


def select_picks(
    events: Sequence[dict],
    *,
    monday: date,
    sunday: date,
    limit: int = DEFAULT_PICK_LIMIT,
) -> list[DigestPick]:
    """Collect events with ≥1 screening in the week, ranked by rating."""
    picks: list[DigestPick] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        title = event.get("title")
        if not title:
            continue
        in_week = _screenings_in_week(event, monday, sunday)
        if not in_week:
            continue
        rating = event.get("rating") if isinstance(event.get("rating"), (int, float)) else None
        type_ = str(event.get("type") or "other")
        picks.append(
            DigestPick(
                event_id=str(event.get("id") or ""),
                title=str(title),
                rating=int(rating) if isinstance(rating, (int, float)) else None,
                one_liner=str(event.get("one_liner_summary") or ""),
                description_html=str(event.get("description") or ""),
                review=parse_review(event.get("description")),
                category_label=CATEGORY_LABELS.get(type_, type_.replace("_", " ").title()),
                venue=str(event.get("venue") or ""),
                url=str(event.get("url") or ""),
                in_week=tuple(in_week),
            )
        )
    picks.sort(
        key=lambda p: (
            -(p.rating if p.rating is not None else -1),
            p.in_week[0].date if p.in_week else "",
            p.in_week[0].time if p.in_week else "",
        )
    )
    return picks[:limit]


def _format_time(t: str) -> str:
    m = re.match(r"^(\d{1,2}):(\d{2})$", t or "")
    if not m:
        return t or ""
    hh = int(m.group(1))
    mm = m.group(2)
    ampm = "PM" if hh >= 12 else "AM"
    h12 = hh % 12 or 12
    return f"{h12}:{mm} {ampm}"


def _format_when(screening: WeekScreening) -> str:
    sd = _parse_iso_date(screening.date)
    if sd is None:
        base = screening.date or ""
    else:
        base = f"{WEEKDAY_SHORT[sd.weekday()]}, {MONTHS_SHORT[sd.month - 1]} {sd.day}"
    tpart = _format_time(screening.time)
    return f"{base} · {tpart}" if tpart else base


def _format_range(monday: date, sunday: date) -> str:
    same_month = monday.month == sunday.month
    m1 = MONTHS_LONG[monday.month - 1]
    m2 = MONTHS_LONG[sunday.month - 1]
    if same_month:
        return f"{m1} {monday.day}\u2013{sunday.day}, {sunday.year}"
    return f"{m1} {monday.day} \u2013 {m2} {sunday.day}, {sunday.year}"


def _esc(value: str) -> str:
    return html.escape(value or "", quote=True)


def _anchor(pick: DigestPick) -> str:
    if not pick.event_id:
        return "../"
    return f"../#event={_esc(pick.event_id)}"


def _render_review(review: ParsedReview) -> str:
    if not review.sections:
        return ""
    out: list[str] = ['<section class="weekly-review">']
    for idx, sec in enumerate(review.sections):
        cls = "weekly-review-section"
        if idx == 0:
            cls += " weekly-review-first"
        out.append(f'<section class="{cls}">')
        if sec.label:
            parts = ['<h3 class="weekly-review-heading">']
            if sec.emoji:
                parts.append(
                    f'<span class="weekly-review-emoji" aria-hidden="true">{_esc(sec.emoji)}</span> '
                )
            parts.append(_esc(sec.label))
            parts.append("</h3>")
            out.append("".join(parts))
        if sec.body:
            out.append(f'<p class="weekly-review-body">{_esc(sec.body)}</p>')
        out.append("</section>")
    out.append("</section>")
    return "".join(out)


def _render_pick(pick: DigestPick, ordinal: int) -> str:
    anchor = _anchor(pick)
    screenings_html = ""
    if pick.in_week:
        items = "".join(
            f"<li>{_esc(_format_when(s))}"
            + (f" \u00b7 {_esc(s.venue)}" if s.venue and s.venue != pick.venue else "")
            + "</li>"
            for s in pick.in_week
        )
        screenings_html = f'<ul class="weekly-screenings">{items}</ul>'
    subtitle_bits = [b for b in [pick.venue, pick.category_label] if b]
    subtitle_text = " \u00b7 ".join(_esc(s) for s in subtitle_bits)
    subtitle_html = (
        f'<p class="weekly-pick-subtitle">{subtitle_text}</p>' if subtitle_text else ""
    )
    rating_html = ""
    if pick.rating is not None:
        rating_html = (
            f'<span class="weekly-rating" aria-label="rated {pick.rating} out of 10">'
            f"{pick.rating} / 10</span>"
        )
    one_liner_html = ""
    if pick.one_liner:
        one_liner_html = f'<p class="weekly-oneliner">{_esc(pick.one_liner)}</p>'
    review_html = _render_review(pick.review)
    official_html = ""
    if pick.url:
        official_html = (
            f'<p class="weekly-pick-footer">'
            f'<a class="weekly-pick-link" href="{_esc(pick.url)}" '
            f'rel="noopener" target="_blank">Official page</a>'
            f"</p>"
        )
    pick_id = f"pick-{_esc(pick.event_id) or ordinal}"
    return (
        f'<li class="weekly-pick" id="{pick_id}">'
        f'<article class="weekly-pick-article">'
        f'<header class="weekly-pick-header">'
        f'<div class="weekly-pick-rank" aria-hidden="true">{ordinal:02d}</div>'
        f'{rating_html}'
        f'<h2 class="weekly-pick-title">'
        f'<a href="{anchor}">{_esc(pick.title)}</a>'
        f"</h2>"
        f'{subtitle_html}'
        f"{screenings_html}"
        f"</header>"
        f"{one_liner_html}"
        f"{review_html}"
        f"{official_html}"
        f"</article>"
        f"</li>"
    )


def render_digest(
    picks: Sequence[DigestPick],
    *,
    year: int,
    week: int,
    monday: date,
    sunday: date,
) -> str:
    """Build the static digest HTML for one ISO week."""
    label = iso_week_label(year, week)
    date_range = _format_range(monday, sunday)
    if picks:
        picks_html = "\n".join(
            _render_pick(p, idx + 1) for idx, p in enumerate(picks)
        )
        picks_block = f'<ol class="weekly-picks">{picks_html}</ol>'
    else:
        picks_block = (
            '<p class="weekly-empty">No scheduled picks for this week yet. '
            '<a href="../">Browse the full calendar</a> to see what\'s on.'
            "</p>"
        )
    title = f"Top Picks \u00b7 Week of {MONTHS_SHORT[monday.month - 1]} {monday.day}, {monday.year}"
    description_meta = (
        f"AI-curated Austin cultural events for {date_range}. "
        f"{len(picks)} top picks with reviews."
    )
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{_esc(title)} \u2014 Culture Calendar</title>\n"
        f'<meta name="description" content="{_esc(description_meta)}">\n'
        '<link rel="stylesheet" href="../styles.css">\n'
        '<link rel="alternate" type="application/rss+xml" title="Culture Calendar" '
        f'href="{_esc(RSS_URL)}">\n'
        "</head>\n"
        '<body class="weekly-digest">\n'
        '<header class="weekly-masthead">\n'
        f'<p class="weekly-eyebrow">Culture Calendar \u00b7 {_esc(label)}</p>\n'
        f"<h1>{_esc(title)}</h1>\n"
        f'<p class="weekly-subtitle">{_esc(date_range)}</p>\n'
        '<nav class="weekly-actions" aria-label="Digest actions">\n'
        '<a href="../">\u2190 Back to Calendar</a>\n'
        f'<a href="{_esc(TOP_PICKS_WEBCAL)}">Subscribe (webcal)</a>\n'
        f'<a href="{_esc(TOP_PICKS_HTTPS)}">Download ICS</a>\n'
        f'<a href="{_esc(RSS_URL)}">RSS</a>\n'
        "</nav>\n"
        "</header>\n"
        '<main class="weekly-main">\n'
        f"{picks_block}\n"
        "</main>\n"
        '<footer class="weekly-footer">\n'
        f"{SIGNUP_FORM_BLOCK}\n"
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


def write_digest(
    events: Sequence[dict],
    *,
    year: int,
    week: int,
    out_dir: Path = OUT_DIR,
    limit: int = DEFAULT_PICK_LIMIT,
) -> tuple[Path, int]:
    """Render one digest page for ``(year, week)``. Returns ``(path, pick_count)``."""
    monday, sunday = iso_week_range(year, week)
    picks = select_picks(events, monday=monday, sunday=sunday, limit=limit)
    html_doc = render_digest(
        picks, year=year, week=week, monday=monday, sunday=sunday
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{iso_week_label(year, week)}.html"
    out_path.write_text(html_doc, encoding="utf-8")
    return out_path, len(picks)


def _unique_upcoming_weeks(
    events: Sequence[dict], today: date, weeks_ahead: int
) -> list[tuple[int, int]]:
    horizon = today + timedelta(weeks=weeks_ahead)
    seen: set[tuple[int, int]] = set()
    for event in events:
        if not isinstance(event, dict):
            continue
        for raw in _event_screenings(event):
            sd = _parse_iso_date(str(raw.get("date", "")))
            if sd is None or sd < today or sd > horizon:
                continue
            iso = sd.isocalendar()
            seen.add((iso.year, iso.week))
    return sorted(seen)


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
        help="Output directory for weekly HTML (default: %(default)s).",
    )
    parser.add_argument(
        "--week",
        type=str,
        default=None,
        help="Target ISO week as YYYY-Www (default: current ISO week).",
    )
    parser.add_argument(
        "--all-upcoming",
        action="store_true",
        help="Generate a digest for every ISO week with upcoming screenings.",
    )
    parser.add_argument(
        "--weeks-ahead",
        type=int,
        default=4,
        help="Lookahead horizon when --all-upcoming is set (default: %(default)s).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_PICK_LIMIT,
        help="Maximum picks per week (default: %(default)s).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-file summary lines on stdout.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    events = load_events(args.data)

    targets: list[tuple[int, int]]
    today = datetime.now().date()
    if args.all_upcoming:
        targets = _unique_upcoming_weeks(events, today, max(args.weeks_ahead, 1))
        if not targets:
            targets = [iso_week_from_date(today)]
    elif args.week:
        targets = [parse_iso_week_arg(args.week)]
    else:
        targets = [iso_week_from_date(today)]

    for year, week in targets:
        path, count = write_digest(
            events, year=year, week=week, out_dir=args.out_dir, limit=args.limit
        )
        if not args.quiet:
            print(f"Wrote {path} ({count} picks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
