"""Build ``docs/api/*.json`` aggregate endpoints and per-event canonical JSON.

Aggregate endpoints under ``docs/api/`` give agents a structured,
HTML-free view of the corpus so they can answer questions without
parsing ``index.html`` or walking per-event shells:

- ``events.json`` — every event with public fields, HTML stripped from
  the review body (``description_text``).
- ``top-picks.json`` — only events with ``rating >= TOP_PICK_MIN_RATING``
  (7), sorted by rating desc. Matches the editorial line of
  ``top-picks.ics`` / the RSS top-picks feed.
- ``venues.json`` — one row per distinct venue with event count and the
  set of categories it programmes, linking back to the ``venues/<slug>``
  deep-dive page.
- ``people.json`` — one row per distinct composer (concerts + operas),
  director (movies) or author (book clubs), with event count and the
  per-person deep-dive + webcal URLs.
- ``categories.json`` — one row per ``type`` with its human label and
  count.

All five share the envelope ``{generated_at, site_url, count, data:
[...]}`` so a client can deserialise any of them with the same adapter.

Per-event canonical files land at ``docs/events/<slug>.json`` and
mirror the schema.org ``Event`` JSON-LD embedded in the sibling
``<slug>.html`` shell. Agents and crawlers can fetch the JSON directly
without scraping the script tag out of HTML.

Stdlib only — no new deps.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
DATA_PATH = DOCS_DIR / "data.json"
API_DIR = DOCS_DIR / "api"
EVENTS_JSON_DIR = DOCS_DIR / "events"
OG_DIR = DOCS_DIR / "og"

SITE_BASE_URL = "https://hadrien-cornier.github.io/Culture-Calendar/"
TOP_PICK_MIN_RATING = 7

# Matches the shell builder's truncation so the canonical JSON body can
# be byte-compared with the inline <script type="application/ld+json"> tag.
_JSONLD_ONE_LINER_MAX = 180
_JSONLD_DESCRIPTION_MAX = 260

CATEGORY_LABELS: dict[str, str] = {
    "movie": "Film",
    "concert": "Concert",
    "opera": "Opera",
    "dance": "Dance",
    "book_club": "Book club",
    "visual_arts": "Visual arts",
    "other": "Other",
}

ROLE_COMPOSER = "composer"
ROLE_DIRECTOR = "director"
ROLE_AUTHOR = "author"

# Which event types contribute which kind of person, and the fields to
# probe on each event.
_PERSON_FIELDS_BY_TYPE: dict[str, tuple[tuple[str, ...], str]] = {
    "movie": (("director", "directors"), ROLE_DIRECTOR),
    "concert": (("composers", "composer"), ROLE_COMPOSER),
    "opera": (("composers", "composer"), ROLE_COMPOSER),
    "book_club": (("author", "authors"), ROLE_AUTHOR),
}

LOG = logging.getLogger("build_api_json")

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    """Lowercase, ASCII-folded, hyphen-separated slug (matches peer builders)."""
    if not value:
        return ""
    normalised = (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    return _SLUG_RE.sub("-", normalised).strip("-")


class _HTMLTextExtractor(HTMLParser):
    """Collect visible text from an HTML fragment, collapsing whitespace."""

    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []

    def handle_data(self, data: str) -> None:  # type: ignore[override]
        self._chunks.append(data)

    def handle_starttag(self, tag: str, attrs):  # type: ignore[override]
        if tag in {"p", "br", "li", "div", "h1", "h2", "h3", "h4"}:
            self._chunks.append(" ")

    def handle_endtag(self, tag: str) -> None:  # type: ignore[override]
        if tag in {"p", "li", "div", "h1", "h2", "h3", "h4"}:
            self._chunks.append(" ")

    @property
    def text(self) -> str:
        collapsed = re.sub(r"\s+", " ", "".join(self._chunks))
        return collapsed.strip()


def html_to_text(html: str) -> str:
    """Return the visible text of ``html`` with whitespace collapsed."""
    if not html:
        return ""
    parser = _HTMLTextExtractor()
    parser.feed(html)
    return parser.text


def _absolute_url(rel: str, *, base_url: str = SITE_BASE_URL) -> str:
    base = base_url if base_url.endswith("/") else base_url + "/"
    if not rel:
        return base
    if rel.startswith(("http://", "https://")):
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
    """Earliest ``YYYY-MM-DD`` across ``screenings[].date`` then ``dates[]``."""
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
    return min(dates)


def _event_first_time(event: dict) -> str:
    screenings = event.get("screenings") or []
    for s in screenings:
        if isinstance(s, dict) and s.get("time"):
            return str(s["time"])
    for t in event.get("times") or []:
        if t:
            return str(t)
    return ""


def _clean_people_values(raw: object) -> list[str]:
    """Return trimmed non-empty string names from a composer/director/author field."""
    if isinstance(raw, str):
        candidates: Iterable[object] = [raw]
    elif isinstance(raw, list):
        candidates = raw
    else:
        return []
    out: list[str] = []
    for item in candidates:
        if not isinstance(item, str):
            continue
        name = item.strip()
        if name:
            out.append(name)
    return out


def _extract_people(event: dict) -> list[tuple[str, str]]:
    """Return ``(role, name)`` tuples contributed by a single event.

    Deduplicates case-insensitively so ``composers: ["Bach", "bach"]``
    counts once. Unknown event types contribute nothing.
    """
    type_ = str(event.get("type") or "").strip().lower()
    spec = _PERSON_FIELDS_BY_TYPE.get(type_)
    if not spec:
        return []
    fields, role = spec
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for field in fields:
        for name in _clean_people_values(event.get(field)):
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append((role, name))
    return out


def _event_api_shape(event: dict, *, base_url: str = SITE_BASE_URL) -> dict:
    """Shrink a raw data.json entry to the public API shape (HTML stripped)."""
    event_id = str(event.get("id") or "")
    shell_rel = f"events/{event_id}.html" if event_id else ""
    return {
        "id": event_id,
        "title": str(event.get("title") or ""),
        "type": str(event.get("type") or "other"),
        "rating": _event_rating(event),
        "one_liner_summary": str(event.get("one_liner_summary") or ""),
        "description_text": html_to_text(str(event.get("description") or "")),
        "venue": str(event.get("venue") or ""),
        "date": _event_first_date(event),
        "time": _event_first_time(event),
        "url": str(event.get("url") or ""),
        "shell_url": _absolute_url(shell_rel, base_url=base_url) if shell_rel else "",
        "screenings": list(event.get("screenings") or []),
    }


def _envelope(data: Sequence[dict], *, now: Optional[datetime] = None) -> dict:
    build_time = now or datetime.now(tz=timezone.utc)
    return {
        "generated_at": build_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "site_url": SITE_BASE_URL,
        "count": len(data),
        "data": list(data),
    }


def _valid_event(event: object) -> bool:
    return isinstance(event, dict) and bool(event.get("id")) and bool(event.get("title"))


def build_events_payload(
    events: Sequence[dict],
    *,
    base_url: str = SITE_BASE_URL,
    now: Optional[datetime] = None,
) -> dict:
    """Return the ``events.json`` envelope for every valid event."""
    rows = [_event_api_shape(e, base_url=base_url) for e in events if _valid_event(e)]
    return _envelope(rows, now=now)


def build_top_picks_payload(
    events: Sequence[dict],
    *,
    base_url: str = SITE_BASE_URL,
    min_rating: int = TOP_PICK_MIN_RATING,
    now: Optional[datetime] = None,
) -> dict:
    """Return the ``top-picks.json`` envelope sorted by rating desc.

    Only events with ``rating >= min_rating`` qualify. Ties are broken
    by earliest date then title so ordering is deterministic.
    """
    qualifying: list[dict] = []
    for event in events:
        if not _valid_event(event):
            continue
        rating = _event_rating(event)
        if rating is None or rating < min_rating:
            continue
        qualifying.append(event)
    qualifying.sort(
        key=lambda e: (
            -(_event_rating(e) or 0),
            _event_first_date(e) or "9999-99-99",
            str(e.get("title") or ""),
        )
    )
    rows = [_event_api_shape(e, base_url=base_url) for e in qualifying]
    return _envelope(rows, now=now)


def build_venues_payload(
    events: Sequence[dict],
    *,
    base_url: str = SITE_BASE_URL,
    now: Optional[datetime] = None,
) -> dict:
    """Return the ``venues.json`` envelope: one row per distinct venue."""
    bucket: dict[str, dict] = {}
    for event in events:
        if not isinstance(event, dict):
            continue
        name = str(event.get("venue") or "").strip()
        if not name:
            continue
        slot = bucket.setdefault(name, {"count": 0, "types": Counter()})
        slot["count"] += 1
        slot["types"][str(event.get("type") or "other")] += 1
    rows: list[dict] = []
    for name in sorted(bucket.keys(), key=lambda s: s.lower()):
        info = bucket[name]
        slug = slugify(name)
        rows.append(
            {
                "slug": slug,
                "name": name,
                "event_count": info["count"],
                "categories": sorted(info["types"].keys()),
                "page_url": (
                    _absolute_url(f"venues/{slug}.html", base_url=base_url) if slug else ""
                ),
            }
        )
    return _envelope(rows, now=now)


def build_people_payload(
    events: Sequence[dict],
    *,
    base_url: str = SITE_BASE_URL,
    now: Optional[datetime] = None,
) -> dict:
    """Return the ``people.json`` envelope: one row per composer / director / author.

    Rows are sorted by event_count desc, then case-insensitive name asc.
    Each row exposes ``page_url`` and ``ics_url`` pointers even when
    the underlying static page has not been generated yet — missing
    pages return 404 but the API shape stays stable.
    """
    bucket: dict[tuple[str, str], dict] = {}
    for event in events:
        if not isinstance(event, dict):
            continue
        for role, name in _extract_people(event):
            key = (role, name.lower())
            slot = bucket.setdefault(key, {"role": role, "name": name, "count": 0})
            slot["count"] += 1
    rows: list[dict] = []
    for info in bucket.values():
        slug = slugify(info["name"])
        rows.append(
            {
                "slug": slug,
                "name": info["name"],
                "role": info["role"],
                "event_count": info["count"],
                "page_url": (
                    _absolute_url(f"people/{slug}.html", base_url=base_url) if slug else ""
                ),
                "ics_url": (
                    _absolute_url(f"people/{slug}.ics", base_url=base_url) if slug else ""
                ),
            }
        )
    rows.sort(key=lambda r: (-r["event_count"], r["name"].lower()))
    return _envelope(rows, now=now)


def build_categories_payload(
    events: Sequence[dict],
    *,
    now: Optional[datetime] = None,
) -> dict:
    """Return the ``categories.json`` envelope: one row per ``type``."""
    counter: Counter[str] = Counter()
    for event in events:
        if isinstance(event, dict):
            counter[str(event.get("type") or "other")] += 1
    rows = [
        {
            "slug": slug,
            "label": CATEGORY_LABELS.get(slug, slug.replace("_", " ").title()),
            "count": count,
        }
        for slug, count in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    return _envelope(rows, now=now)


def _truncate(text: str, *, max_len: int) -> str:
    """Return ``text`` shortened to ``max_len`` chars with a trailing ellipsis."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def _event_slug(event: dict) -> str:
    """Slug used as the ``docs/events/<slug>.json`` filename.

    Derived from the event id (or title as a fallback) using the same
    fold-and-hyphenate rule as :func:`slugify`, so canonical JSON URLs
    line up with the sibling ``.html`` shell and the in-app ``#event=``
    anchor. Events missing both id and title are skipped (empty slug).
    """
    raw = str(event.get("id") or event.get("title") or "").strip()
    return slugify(raw)


def _og_image_url(slug: str, *, base_url: str, og_dir: Path) -> str:
    """Return the per-event OG card URL, falling back to the site default."""
    if slug and (og_dir / f"{slug}.svg").is_file():
        return _absolute_url(f"og/{slug}.svg", base_url=base_url)
    return _absolute_url("og/site-default.svg", base_url=base_url)


def build_event_jsonld(
    event: dict,
    *,
    base_url: str = SITE_BASE_URL,
    og_dir: Path = OG_DIR,
) -> Optional[dict]:
    """Return a schema.org ``Event`` JSON-LD payload, or ``None`` to skip.

    Shape mirrors :func:`scripts.build_event_shells._json_ld` so the
    canonical ``docs/events/<slug>.json`` file is a structured twin of
    the inline ``<script type="application/ld+json">`` tag embedded in
    ``docs/events/<slug>.html``.
    """
    slug = _event_slug(event)
    if not slug:
        return None
    title = str(event.get("title") or slug.replace("-", " ").title()).strip()
    one_liner = _truncate(
        html_to_text(str(event.get("oneLiner") or "")),
        max_len=_JSONLD_ONE_LINER_MAX,
    )
    desc_plain = _truncate(
        html_to_text(str(event.get("description") or "")),
        max_len=_JSONLD_DESCRIPTION_MAX,
    )
    description = one_liner or desc_plain or title
    payload: dict = {
        "@context": "https://schema.org",
        "@type": "Event",
        "name": title,
        "description": description,
        "url": _absolute_url(f"events/{slug}.html", base_url=base_url),
        "image": _og_image_url(slug, base_url=base_url, og_dir=og_dir),
    }
    first_date = _event_first_date(event)
    if first_date:
        payload["startDate"] = first_date
    venue = str(event.get("venue") or "").strip()
    if venue:
        payload["location"] = {
            "@type": "Place",
            "name": venue,
            "address": {
                "@type": "PostalAddress",
                "addressLocality": "Austin",
                "addressRegion": "TX",
            },
        }
    return payload


def write_event_json_files(
    events: Sequence[dict],
    *,
    out_dir: Path = EVENTS_JSON_DIR,
    base_url: str = SITE_BASE_URL,
    og_dir: Path = OG_DIR,
) -> int:
    """Emit one ``<slug>.json`` per event under ``out_dir``; return count.

    Clears stale ``*.json`` files first but leaves sibling ``*.html``
    shells untouched, so this builder and :mod:`build_event_shells`
    share the directory safely. Duplicate slugs are de-duplicated, with
    the first occurrence winning.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("*.json"):
        stale.unlink()
    seen: set[str] = set()
    written = 0
    for event in events:
        if not isinstance(event, dict):
            continue
        payload = build_event_jsonld(event, base_url=base_url, og_dir=og_dir)
        if payload is None:
            continue
        slug = _event_slug(event)
        if slug in seen:
            continue
        seen.add(slug)
        body = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
        (out_dir / f"{slug}.json").write_text(body, encoding="utf-8")
        written += 1
    return written


def load_events(data_path: Path = DATA_PATH) -> list[dict]:
    """Load ``docs/data.json`` as a list of event dicts."""
    if not data_path.is_file():
        raise FileNotFoundError(f"Missing data file: {data_path}")
    payload = json.loads(data_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"{data_path} is not a JSON array")
    return payload


def write_outputs(
    events: Sequence[dict],
    *,
    out_dir: Path = API_DIR,
    base_url: str = SITE_BASE_URL,
    min_rating: int = TOP_PICK_MIN_RATING,
    now: Optional[datetime] = None,
) -> dict[str, int]:
    """Write all five endpoint files to ``out_dir`` and return their byte sizes."""
    out_dir.mkdir(parents=True, exist_ok=True)
    payloads = {
        "events.json": build_events_payload(events, base_url=base_url, now=now),
        "top-picks.json": build_top_picks_payload(
            events, base_url=base_url, min_rating=min_rating, now=now
        ),
        "venues.json": build_venues_payload(events, base_url=base_url, now=now),
        "people.json": build_people_payload(events, base_url=base_url, now=now),
        "categories.json": build_categories_payload(events, now=now),
    }
    sizes: dict[str, int] = {}
    for name, payload in payloads.items():
        body = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
        (out_dir / name).write_text(body, encoding="utf-8")
        sizes[name] = len(body)
    return sizes


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
        default=API_DIR,
        help="Output directory for the five JSON files (default: %(default)s).",
    )
    parser.add_argument(
        "--base-url",
        default=SITE_BASE_URL,
        help="Site base URL used for absolute links.",
    )
    parser.add_argument(
        "--min-rating",
        type=int,
        default=TOP_PICK_MIN_RATING,
        help="Minimum rating to qualify for top-picks.json (default: %(default)s).",
    )
    parser.add_argument(
        "--event-json-dir",
        type=Path,
        default=EVENTS_JSON_DIR,
        help="Output directory for per-event canonical JSON files (default: %(default)s).",
    )
    parser.add_argument(
        "--no-event-json",
        action="store_true",
        help="Skip emitting docs/events/<slug>.json per-event JSON files.",
    )
    parser.add_argument(
        "--og-dir",
        type=Path,
        default=OG_DIR,
        help="Directory of per-event OG cards used for the JSON-LD image URL.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress the summary line on stdout.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    events = load_events(args.data)
    sizes = write_outputs(
        events,
        out_dir=args.out_dir,
        base_url=args.base_url,
        min_rating=args.min_rating,
    )
    event_json_count = 0
    if not args.no_event_json:
        event_json_count = write_event_json_files(
            events,
            out_dir=args.event_json_dir,
            base_url=args.base_url,
            og_dir=args.og_dir,
        )

    if not args.quiet:
        total = sum(sizes.values())
        names = ", ".join(sizes.keys())
        msg = f"Wrote {len(sizes)} files ({names}) to {args.out_dir} ({total} bytes)"
        if not args.no_event_json:
            msg += (
                f"; {event_json_count} per-event JSON files to {args.event_json_dir}"
            )
        print(msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
