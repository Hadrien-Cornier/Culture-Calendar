"""Build the weekly-digest archive page at ``docs/archive.html``.

Scans ``docs/weekly/*.html`` — the static digest pages emitted by
``scripts/build_weekly_digest.py`` — parses the ISO week out of each
filename (``YYYY-Www.html``), computes its Monday–Sunday date range, and
extracts a pick count from the rendered HTML. The result is a
reverse-chronological landing page that links to every digest under the
``weekly/`` directory so readers (and agent crawlers) can discover past
top-picks issues.

Pick-count extraction is best-effort:

1. Parse the ``<meta name="description">`` content for a ``N top picks``
   token.
2. Fall back to counting ``<li class="weekly-pick"`` occurrences.
3. If neither yields a number, record ``None`` and render ``—``.

Stdlib only. Mirrors the structure of ``scripts/build_wishlist.py`` so
the page shares the Culture Calendar masthead vocabulary.
"""

from __future__ import annotations

import argparse
import html
import logging
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
WEEKLY_DIR = REPO_ROOT / "docs" / "weekly"
OUT_PATH = REPO_ROOT / "docs" / "archive.html"

SITE_HOST = "hadrien-cornier.github.io"
SITE_PATH = "/Culture-Calendar/"
SITE_URL = f"https://{SITE_HOST}{SITE_PATH}"
RSS_URL = f"{SITE_URL}feed.xml"
TOP_PICKS_WEBCAL = f"webcal://{SITE_HOST}{SITE_PATH}top-picks.ics"

MONTHS_SHORT = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]

_FILENAME_RE = re.compile(r"^(?P<year>\d{4})-W(?P<week>\d{2})\.html$")
_META_DESC_RE = re.compile(
    r'<meta\s+name="description"\s+content="(?P<body>[^"]*)"',
    re.IGNORECASE,
)
_PICK_COUNT_IN_META_RE = re.compile(r"(\d+)\s+top\s+picks?", re.IGNORECASE)
_PICK_LI_RE = re.compile(r'<li[^>]*class="[^"]*\bweekly-pick\b[^"]*"', re.IGNORECASE)

LOG = logging.getLogger("build_archive")


@dataclass(frozen=True)
class ArchiveEntry:
    """One weekly-digest row on the archive page."""

    year: int
    week: int
    filename: str
    monday: date
    sunday: date
    pick_count: Optional[int]
    description: str

    @property
    def label(self) -> str:
        return f"{self.year:04d}-W{self.week:02d}"

    @property
    def href(self) -> str:
        return f"weekly/{self.filename}"

    @property
    def sort_key(self) -> tuple[int, int]:
        return (self.year, self.week)


def parse_iso_week_filename(filename: str) -> Optional[tuple[int, int]]:
    """Return ``(year, week)`` from ``YYYY-Www.html`` or None if unparseable."""
    match = _FILENAME_RE.match(filename.strip())
    if not match:
        return None
    year = int(match.group("year"))
    week = int(match.group("week"))
    try:
        date.fromisocalendar(year, week, 1)
    except ValueError:
        return None
    return year, week


def extract_pick_count(
    html_body: str,
) -> tuple[Optional[int], str]:
    """Extract pick count + meta description from rendered digest HTML.

    Returns ``(count, description)``. ``count`` is None when neither the
    meta description nor the li-count heuristic yields a number.
    ``description`` is the trimmed meta description contents (empty
    string if missing).
    """
    description = ""
    count: Optional[int] = None
    meta_match = _META_DESC_RE.search(html_body or "")
    if meta_match:
        description = html.unescape(meta_match.group("body")).strip()
        pick_match = _PICK_COUNT_IN_META_RE.search(description)
        if pick_match:
            count = int(pick_match.group(1))
    if count is None:
        li_count = len(_PICK_LI_RE.findall(html_body or ""))
        if li_count:
            count = li_count
    return count, description


def _iso_week_range(year: int, week: int) -> tuple[date, date]:
    monday = date.fromisocalendar(year, week, 1)
    sunday = monday + timedelta(days=6)
    return monday, sunday


def load_archive_entries(weekly_dir: Path = WEEKLY_DIR) -> list[ArchiveEntry]:
    """Load every parseable digest under ``weekly_dir``, newest first."""
    entries: list[ArchiveEntry] = []
    if not weekly_dir.exists() or not weekly_dir.is_dir():
        return entries
    for path in sorted(weekly_dir.glob("*.html")):
        parsed = parse_iso_week_filename(path.name)
        if parsed is None:
            LOG.debug("Skipping unrecognized digest file: %s", path.name)
            continue
        year, week = parsed
        monday, sunday = _iso_week_range(year, week)
        try:
            body = path.read_text(encoding="utf-8")
        except OSError as exc:
            LOG.warning("Skipping %s: %s", path, exc)
            continue
        count, description = extract_pick_count(body)
        entries.append(
            ArchiveEntry(
                year=year,
                week=week,
                filename=path.name,
                monday=monday,
                sunday=sunday,
                pick_count=count,
                description=description,
            )
        )
    entries.sort(key=lambda e: e.sort_key, reverse=True)
    return entries


def _format_range(monday: date, sunday: date) -> str:
    same_month = monday.month == sunday.month and monday.year == sunday.year
    m1 = MONTHS_SHORT[monday.month - 1]
    m2 = MONTHS_SHORT[sunday.month - 1]
    if same_month:
        return f"{m1} {monday.day}–{sunday.day}, {sunday.year}"
    if monday.year == sunday.year:
        return f"{m1} {monday.day} – {m2} {sunday.day}, {sunday.year}"
    return (
        f"{m1} {monday.day}, {monday.year} – "
        f"{m2} {sunday.day}, {sunday.year}"
    )


def _esc(value: str) -> str:
    return html.escape(value or "", quote=True)


def _render_entry(entry: ArchiveEntry) -> str:
    date_range = _format_range(entry.monday, entry.sunday)
    if entry.pick_count is None:
        count_text = "—"
    else:
        noun = "pick" if entry.pick_count == 1 else "picks"
        count_text = f"{entry.pick_count} {noun}"
    summary_html = ""
    if entry.description:
        summary_html = (
            f'<p class="archive-summary">{_esc(entry.description)}</p>'
        )
    return (
        '<li class="archive-item">'
        '<article class="archive-article">'
        '<header class="archive-entry-header">'
        f'<h2 class="archive-entry-title">'
        f'<a class="archive-entry-link" href="{_esc(entry.href)}">'
        f'{_esc(entry.label)}</a></h2>'
        f'<p class="archive-entry-range">{_esc(date_range)}</p>'
        f'<p class="archive-entry-count">{_esc(count_text)}</p>'
        "</header>"
        f"{summary_html}"
        "</article>"
        "</li>"
    )


def render_page(
    entries: Sequence[ArchiveEntry],
    *,
    generated_at: Optional[datetime] = None,
) -> str:
    """Render the full HTML page body."""
    generated_at = generated_at or datetime.now(tz=timezone.utc)
    stamp = generated_at.strftime("%Y-%m-%d %H:%M UTC")
    total = len(entries)
    if entries:
        items_html = "\n".join(_render_entry(entry) for entry in entries)
        body_html = f'<ol class="archive-items">{items_html}</ol>'
    else:
        body_html = (
            '<p class="archive-empty">No weekly digests yet. '
            "Run <code>scripts/build_weekly_digest.py</code> to "
            "generate the first issue.</p>"
        )
    count_noun = "issue" if total == 1 else "issues"
    description_meta = (
        f"Archive of Culture Calendar weekly top-picks digests. "
        f"{total} {count_noun} indexed."
    )
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>Weekly Digest Archive — Culture Calendar</title>\n"
        f'<meta name="description" content="{_esc(description_meta)}">\n'
        '<link rel="canonical" '
        f'href="{_esc(SITE_URL)}archive.html">\n'
        '<link rel="stylesheet" href="styles.css">\n'
        '<link rel="alternate" type="application/rss+xml" '
        f'title="Culture Calendar" href="{_esc(RSS_URL)}">\n'
        "<style>\n"
        ".archive-page { max-width: 880px; margin: 0 auto; "
        "padding: 2rem 1.25rem 4rem; "
        "font-family: 'Libre Franklin', system-ui, sans-serif; "
        "color: #1f1f1f; }\n"
        ".archive-masthead { border-bottom: 1px solid #d4a574; "
        "padding-bottom: 1.25rem; margin-bottom: 2rem; }\n"
        ".archive-eyebrow { font-size: 0.75rem; letter-spacing: 0.08em; "
        "text-transform: uppercase; color: #8a6f4a; margin: 0; }\n"
        ".archive-page h1 { font-family: 'et-book', Georgia, serif; "
        "font-size: 2.25rem; margin: 0.25rem 0 0.75rem; }\n"
        ".archive-lead { font-size: 1rem; line-height: 1.55; "
        "color: #3a3a3a; margin: 0 0 0.75rem; }\n"
        ".archive-stamp { font-size: 0.8rem; color: #6b6b6b; margin: 0; }\n"
        ".archive-actions { margin-top: 1rem; display: flex; gap: 1rem; "
        "flex-wrap: wrap; font-size: 0.9rem; }\n"
        ".archive-actions a { color: #8a3b2a; text-decoration: none; "
        "border-bottom: 1px solid #d4a574; }\n"
        ".archive-items { list-style: none; margin: 0; padding: 0; "
        "display: grid; gap: 1rem; }\n"
        ".archive-item { border-left: 2px solid #d4a574; "
        "padding: 0.5rem 0 0.5rem 0.85rem; }\n"
        ".archive-entry-header { display: flex; align-items: baseline; "
        "flex-wrap: wrap; gap: 0.5rem 1rem; }\n"
        ".archive-entry-title { font-family: 'et-book', Georgia, serif; "
        "font-size: 1.3rem; margin: 0; flex: 1 1 auto; }\n"
        ".archive-entry-link { color: #1f1f1f; text-decoration: none; "
        "border-bottom: 1px solid #d4a574; }\n"
        ".archive-entry-range { font-size: 0.9rem; color: #3a3a3a; "
        "margin: 0; }\n"
        ".archive-entry-count { font-size: 0.8rem; color: #6b6b6b; "
        "margin: 0; font-variant-numeric: tabular-nums; }\n"
        ".archive-summary { margin: 0.35rem 0 0; font-size: 0.9rem; "
        "line-height: 1.45; color: #3a3a3a; }\n"
        ".archive-empty { padding: 1.5rem; border: 1px dashed #d4a574; "
        "text-align: center; color: #6b6b6b; }\n"
        "</style>\n"
        "</head>\n"
        '<body class="archive-page">\n'
        '<header class="archive-masthead">\n'
        '<p class="archive-eyebrow">Culture Calendar · Weekly Archive</p>\n'
        "<h1>Weekly top-picks digest archive</h1>\n"
        '<p class="archive-lead">Every issue of the weekly digest, '
        'newest first. Subscribe via '
        f'<a href="{_esc(TOP_PICKS_WEBCAL)}">webcal</a> or '
        f'<a href="{_esc(RSS_URL)}">RSS</a> to get future picks '
        "automatically.</p>\n"
        f'<p class="archive-stamp">{total} '
        f'{count_noun} · generated {_esc(stamp)}</p>\n'
        '<nav class="archive-actions" aria-label="Archive actions">\n'
        '<a href="./">&larr; Back to Calendar</a>\n'
        f'<a href="{_esc(RSS_URL)}">RSS</a>\n'
        f'<a href="{_esc(TOP_PICKS_WEBCAL)}">Top Picks (webcal)</a>\n'
        "</nav>\n"
        "</header>\n"
        '<main class="archive-main">\n'
        f"{body_html}\n"
        "</main>\n"
        '<footer class="archive-footer">\n'
        '<p><a href="./">Culture Calendar</a> · '
        "AI-curated Austin cultural events</p>\n"
        "</footer>\n"
        "</body>\n"
        "</html>\n"
    )


def write_archive(
    *,
    weekly_dir: Path = WEEKLY_DIR,
    out_path: Path = OUT_PATH,
    generated_at: Optional[datetime] = None,
) -> tuple[Path, int]:
    """Render and persist the archive HTML. Returns ``(path, entry_count)``."""
    entries = load_archive_entries(weekly_dir)
    rendered = render_page(entries, generated_at=generated_at)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered, encoding="utf-8")
    return out_path, len(entries)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--weekly-dir",
        type=Path,
        default=WEEKLY_DIR,
        help="Directory of weekly digest HTML files (default: %(default)s).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=OUT_PATH,
        help="Output HTML file (default: %(default)s).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress stdout summary.",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    out_path, count = write_archive(
        weekly_dir=args.weekly_dir, out_path=args.out
    )
    if not args.quiet:
        print(f"Wrote {out_path} ({count} entries)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
