"""Build ``docs/llms.txt`` and ``docs/llms-full.txt`` for LLM agents.

These files are the agent-friendly analogue of ``sitemap.xml``: a bot that
wants to read the site without crawling HTML can fetch either file and
get a complete, plain-text picture.

- ``docs/llms.txt`` follows the llmstxt.org spec — H1 title, quoted
  description, then H2-sectioned lists of ``[link](url): note`` rows. The
  spec is intentionally markdown-parseable with zero tooling.
- ``docs/llms-full.txt`` is a content dump: about text, site statistics,
  and the top N events rendered as plain text (HTML stripped), so an LLM
  can consume the corpus without following links.

Stdlib only (``html.parser``, ``json``, ``pathlib``) — no new deps.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
DATA_PATH = DOCS_DIR / "data.json"
ABOUT_PATH = DOCS_DIR / "ABOUT.md"
OUT_INDEX = DOCS_DIR / "llms.txt"
OUT_FULL = DOCS_DIR / "llms-full.txt"

SITE_BASE_URL = "https://hadrien-cornier.github.io/Culture-Calendar/"
SITE_NAME = "Culture Calendar"
SITE_DESCRIPTION = (
    "Austin cultural events, AI-curated. Films, concerts, opera, ballet, "
    "book clubs, and visual arts — sorted by merit, not marketing."
)

CORE_PAGES: tuple[tuple[str, str, str], ...] = (
    ("Home", "", "Top picks of the week plus every upcoming event."),
    ("How it works", "how-it-works.html", "Methodology, venues, mailing list."),
    ("Weekly digest archive", "archive.html", "Past Monday-morning tipsheets."),
    ("Venue wishlist", "wishlist.html", "Venues we would like to add next."),
)

FEED_PAGES: tuple[tuple[str, str, str], ...] = (
    ("RSS — top picks", "feed.xml", "RSS 2.0 feed of the top-ranked events."),
    ("iCal — all events", "calendar.ics", "Every event as a subscribable calendar."),
    ("iCal — top picks", "top-picks.ics", "Only the top-ranked events."),
    ("Sitemap", "sitemap.xml", "Every HTML page on the site."),
)

CATEGORY_LABELS: dict[str, str] = {
    "movie": "Film",
    "concert": "Concert",
    "opera": "Opera",
    "dance": "Dance",
    "book_club": "Book club",
    "visual_arts": "Visual arts",
    "other": "Other",
}

TOP_EVENTS_FULL = 30
MAX_REVIEW_CHARS = 800

LOG = logging.getLogger("build_llms_txt")


class _HTMLTextExtractor(HTMLParser):
    """Collect visible text from an HTML fragment, collapsing whitespace."""

    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []

    def handle_data(self, data: str) -> None:  # type: ignore[override]
        self._chunks.append(data)

    def handle_starttag(self, tag: str, attrs):  # type: ignore[override]
        if tag in {"p", "br", "li", "div", "h1", "h2", "h3", "h4"}:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:  # type: ignore[override]
        if tag in {"p", "li", "div", "h1", "h2", "h3", "h4"}:
            self._chunks.append("\n")

    @property
    def text(self) -> str:
        joined = "".join(self._chunks)
        collapsed = re.sub(r"[ \t]+", " ", joined)
        collapsed = re.sub(r"\n{3,}", "\n\n", collapsed)
        return collapsed.strip()


def html_to_text(html: str) -> str:
    """Return the visible text of ``html`` with whitespace collapsed."""
    if not html:
        return ""
    parser = _HTMLTextExtractor()
    parser.feed(html)
    return parser.text


@dataclass(frozen=True)
class LinkEntry:
    """One ``[title](url): note`` row in ``llms.txt``."""

    title: str
    url: str
    note: str = ""

    def render(self) -> str:
        if self.note:
            return f"- [{self.title}]({self.url}): {self.note}"
        return f"- [{self.title}]({self.url})"


def _absolute_url(rel: str, *, base_url: str = SITE_BASE_URL) -> str:
    base = base_url if base_url.endswith("/") else base_url + "/"
    if not rel:
        return base
    if rel.startswith("http://") or rel.startswith("https://"):
        return rel
    return base + rel.lstrip("/")


def _event_rating(event: dict) -> Optional[int]:
    rating = event.get("rating")
    if isinstance(rating, bool):
        return None
    if isinstance(rating, (int, float)):
        return int(rating)
    return None


def _event_first_date(event: dict) -> str:
    """Return the earliest ``YYYY-MM-DD`` date for ``event`` or ``""``."""
    screenings = event.get("screenings") or []
    dates: list[str] = []
    for s in screenings:
        if isinstance(s, dict) and s.get("date"):
            dates.append(str(s["date"]))
    if not dates:
        for d in event.get("dates") or []:
            if d:
                dates.append(str(d))
    if not dates:
        return ""
    dates.sort()
    return dates[0]


def _event_first_time(event: dict) -> str:
    screenings = event.get("screenings") or []
    for s in screenings:
        if isinstance(s, dict) and s.get("time"):
            return str(s["time"])
    for t in event.get("times") or []:
        if t:
            return str(t)
    return ""


def _collect_categories(events: Sequence[dict]) -> list[tuple[str, int]]:
    counter: Counter[str] = Counter()
    for e in events:
        if isinstance(e, dict):
            counter[str(e.get("type") or "other")] += 1
    return sorted(counter.items())


def _collect_venues(events: Sequence[dict]) -> list[tuple[str, int]]:
    counter: Counter[str] = Counter()
    for e in events:
        if isinstance(e, dict):
            venue = e.get("venue")
            if venue:
                counter[str(venue)] += 1
    return sorted(counter.items())


def _discover_subdir_pages(
    docs_root: Path, subdir: str, *, base_url: str = SITE_BASE_URL
) -> list[LinkEntry]:
    """Return one ``LinkEntry`` per ``*.html`` file in ``docs_root / subdir``."""
    directory = docs_root / subdir
    if not directory.is_dir():
        return []
    entries: list[LinkEntry] = []
    for path in sorted(directory.glob("*.html")):
        rel = path.relative_to(docs_root).as_posix()
        title = path.stem.replace("-", " ").replace("_", " ").strip()
        entries.append(LinkEntry(title=title or rel, url=_absolute_url(rel, base_url=base_url)))
    return entries


def _load_about(about_path: Path = ABOUT_PATH) -> str:
    """Return the body of ``ABOUT.md`` or ``""`` if missing."""
    if not about_path.is_file():
        return ""
    return about_path.read_text(encoding="utf-8").strip()


def _top_events(events: Sequence[dict], *, limit: int) -> list[dict]:
    """Return the top ``limit`` events ranked by rating descending."""

    def key(e: dict) -> tuple:
        rating = _event_rating(e)
        return (-(rating if rating is not None else -1), _event_first_date(e), str(e.get("title") or ""))

    ranked = sorted((e for e in events if isinstance(e, dict) and e.get("title")), key=key)
    return ranked[:limit]


def render_llms_txt(
    events: Sequence[dict],
    *,
    docs_root: Path = DOCS_DIR,
    base_url: str = SITE_BASE_URL,
) -> str:
    """Return the ``llms.txt`` body for ``events`` and pages under ``docs_root``.

    Uses the llmstxt.org v0 format: ``# Title`` / ``> description`` /
    ``## Section`` / ``- [link](url): note`` rows.
    """
    lines: list[str] = [f"# {SITE_NAME}", "", f"> {SITE_DESCRIPTION}", ""]

    lines.append("## Core pages")
    lines.append("")
    for title, rel, note in CORE_PAGES:
        lines.append(LinkEntry(title, _absolute_url(rel, base_url=base_url), note).render())
    lines.append("")

    lines.append("## Subscribable feeds")
    lines.append("")
    for title, rel, note in FEED_PAGES:
        lines.append(LinkEntry(title, _absolute_url(rel, base_url=base_url), note).render())
    lines.append("")

    categories = _collect_categories(events)
    if categories:
        lines.append("## Categories")
        lines.append("")
        for cat, count in categories:
            label = CATEGORY_LABELS.get(cat, cat.replace("_", " ").title())
            lines.append(f"- {label} — {count} event{'s' if count != 1 else ''}")
        lines.append("")

    venue_pages = _discover_subdir_pages(docs_root, "venues", base_url=base_url)
    if venue_pages:
        lines.append("## Venues")
        lines.append("")
        lines.extend(entry.render() for entry in venue_pages)
        lines.append("")

    people_pages = _discover_subdir_pages(docs_root, "people", base_url=base_url)
    if people_pages:
        lines.append("## People")
        lines.append("")
        lines.extend(entry.render() for entry in people_pages)
        lines.append("")

    weekly_pages = _discover_subdir_pages(docs_root, "weekly", base_url=base_url)
    if weekly_pages:
        lines.append("## Weekly digests")
        lines.append("")
        lines.extend(entry.render() for entry in weekly_pages)
        lines.append("")

    while lines and lines[-1] == "":
        lines.pop()
    lines.append("")
    return "\n".join(lines)


def _render_event_block(event: dict, *, base_url: str = SITE_BASE_URL) -> str:
    title = str(event.get("title") or "Untitled")
    rating = _event_rating(event)
    rating_prefix = f"[{rating}/10] " if rating is not None else ""
    venue = str(event.get("venue") or "")
    date = _event_first_date(event)
    time = _event_first_time(event)
    one_liner = str(event.get("one_liner_summary") or "").strip()
    review = html_to_text(str(event.get("description") or ""))
    if len(review) > MAX_REVIEW_CHARS:
        review = review[: MAX_REVIEW_CHARS - 1].rstrip() + "…"

    event_id = str(event.get("id") or "")
    anchor_url = _absolute_url(
        f"events/{event_id}.html" if event_id else "", base_url=base_url
    )

    parts: list[str] = [f"{rating_prefix}{title}"]
    meta_bits = [bit for bit in (venue, date, time) if bit]
    if meta_bits:
        parts.append(" | ".join(meta_bits))
    if one_liner:
        parts.append(f"Hook: {one_liner}")
    if review:
        parts.append(f"Review: {review}")
    parts.append(f"URL: {anchor_url}")
    return "\n".join(parts)


def render_llms_full_txt(
    events: Sequence[dict],
    *,
    about_text: str = "",
    base_url: str = SITE_BASE_URL,
    now: Optional[datetime] = None,
    top_n: int = TOP_EVENTS_FULL,
) -> str:
    """Return the ``llms-full.txt`` plain-text content dump."""
    build_time = now or datetime.now(tz=timezone.utc)
    blocks: list[str] = []

    header = [
        f"{SITE_NAME} — Full content dump for LLMs",
        "=" * 60,
        f"URL: {base_url}",
        f"Generated: {build_time.strftime('%Y-%m-%dT%H:%M:%SZ')}",
        "",
        SITE_DESCRIPTION,
    ]
    blocks.append("\n".join(header))

    if about_text:
        blocks.append("About\n-----\n" + about_text)

    total = sum(1 for e in events if isinstance(e, dict))
    stats_lines = [f"Total events: {total}"]
    for cat, count in _collect_categories(events):
        label = CATEGORY_LABELS.get(cat, cat.replace("_", " ").title())
        stats_lines.append(f"- {label}: {count}")
    venues = _collect_venues(events)
    if venues:
        stats_lines.append("")
        stats_lines.append("Venues:")
        for venue, count in venues:
            stats_lines.append(f"- {venue}: {count}")
    blocks.append("Statistics\n----------\n" + "\n".join(stats_lines))

    top = _top_events(events, limit=top_n)
    if top:
        event_blocks = [
            f"{i}. " + _render_event_block(event, base_url=base_url)
            for i, event in enumerate(top, start=1)
        ]
        heading = f"Top events (ranked by rating, up to {top_n})"
        underline = "-" * len(heading)
        blocks.append(
            f"{heading}\n{underline}\n\n" + "\n\n".join(event_blocks)
        )

    return "\n\n".join(blocks).rstrip() + "\n"


def load_events(data_path: Path = DATA_PATH) -> list[dict]:
    if not data_path.is_file():
        raise FileNotFoundError(f"Missing data file: {data_path}")
    payload = json.loads(data_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"{data_path} is not a JSON array")
    return payload


def write_outputs(
    events: Sequence[dict],
    *,
    docs_root: Path = DOCS_DIR,
    out_index: Path = OUT_INDEX,
    out_full: Path = OUT_FULL,
    about_path: Path = ABOUT_PATH,
    base_url: str = SITE_BASE_URL,
    now: Optional[datetime] = None,
    top_n: int = TOP_EVENTS_FULL,
) -> tuple[int, int]:
    """Write both files and return (llms.txt byte-count, llms-full.txt byte-count)."""
    out_index.parent.mkdir(parents=True, exist_ok=True)
    out_full.parent.mkdir(parents=True, exist_ok=True)

    index_body = render_llms_txt(events, docs_root=docs_root, base_url=base_url)
    full_body = render_llms_full_txt(
        events,
        about_text=_load_about(about_path),
        base_url=base_url,
        now=now,
        top_n=top_n,
    )

    out_index.write_text(index_body, encoding="utf-8")
    out_full.write_text(full_body, encoding="utf-8")
    return len(index_body), len(full_body)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--data",
        type=Path,
        default=DATA_PATH,
        help="Path to docs/data.json (default: %(default)s).",
    )
    parser.add_argument(
        "--docs",
        type=Path,
        default=DOCS_DIR,
        help="Docs root used to discover venue/people/weekly pages.",
    )
    parser.add_argument(
        "--about",
        type=Path,
        default=ABOUT_PATH,
        help="Path to the about markdown file.",
    )
    parser.add_argument(
        "--out-index",
        type=Path,
        default=OUT_INDEX,
        help="Output path for llms.txt (default: %(default)s).",
    )
    parser.add_argument(
        "--out-full",
        type=Path,
        default=OUT_FULL,
        help="Output path for llms-full.txt (default: %(default)s).",
    )
    parser.add_argument(
        "--base-url",
        default=SITE_BASE_URL,
        help="Site base URL used for absolute links.",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=TOP_EVENTS_FULL,
        help="Maximum number of events to include in llms-full.txt.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress the summary line on stdout.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    events = load_events(args.data)
    index_bytes, full_bytes = write_outputs(
        events,
        docs_root=args.docs,
        out_index=args.out_index,
        out_full=args.out_full,
        about_path=args.about,
        base_url=args.base_url,
        top_n=args.top_n,
    )

    if not args.quiet:
        print(
            f"Wrote {args.out_index} ({index_bytes} bytes) and "
            f"{args.out_full} ({full_bytes} bytes)"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
