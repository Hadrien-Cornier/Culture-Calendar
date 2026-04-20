"""Generate per-event Open Graph SVG cards from ``docs/data.json``.

Each event in the data file becomes one 1200×630 SVG card under
``docs/og/<event_id>.svg``. The SVG is plain string-templated markup —
no Cairo, no headless browser, no new dependencies. A deep-linked
``#event=<id>`` page sets the matching card as ``og:image``.

Card composition:
    - Dark gradient background tinted by event category.
    - Brand chip ("Culture Calendar · Austin") at the top-left.
    - Category pill at the top-right.
    - Wrapped title (up to three lines, ellipsis overflow).
    - Venue · date line.
    - Rating badge (bottom-right) or "Not yet rated" placeholder.

Title text is fitted with a simple width estimator rather than a real
text-metrics engine (which would require fonttools or PIL). The font
falls back across common sans-serifs so that the card still looks
reasonable on platforms that don't have the bespoke stack.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = REPO_ROOT / "docs" / "data.json"
OUT_DIR = REPO_ROOT / "docs" / "og"

CARD_WIDTH = 1200
CARD_HEIGHT = 630
TITLE_MAX_CHARS_PER_LINE = 28
TITLE_MAX_LINES = 3
ELLIPSIS = "\u2026"

LOG = logging.getLogger("build_og_cards")

_CATEGORY_THEME: dict[str, tuple[str, str, str]] = {
    # (gradient_stop1, gradient_stop2, accent)
    "movie": ("#1a1030", "#3d1a4a", "#ff6b6b"),
    "concert": ("#0d1b2a", "#1b263b", "#f4a261"),
    "opera": ("#2b0a3d", "#4a0e5c", "#e0a96d"),
    "book_club": ("#1a2e1f", "#2d4a32", "#a3c9a8"),
    "visual_arts": ("#2b1d0e", "#4a3319", "#d4a574"),
    "dance": ("#2a0e1f", "#4a1a3a", "#e0a8c4"),
    "other": ("#1a1a2e", "#2d2d4a", "#9ca3af"),
}

_CATEGORY_LABEL: dict[str, str] = {
    "movie": "Film",
    "concert": "Concert",
    "opera": "Opera",
    "book_club": "Book Club",
    "visual_arts": "Visual Arts",
    "dance": "Dance",
    "other": "Event",
}


@dataclass(frozen=True)
class CardData:
    """Minimal projection of an event used to render one SVG card."""

    event_id: str
    title: str
    venue: str
    date: str
    rating: Optional[int]
    type_: str


_SLUG_RE = re.compile(r"[^a-z0-9._-]+")
_DASH_COLLAPSE_RE = re.compile(r"-{2,}")


def _safe_filename(event_id: str) -> str:
    """Produce a filesystem-safe stem from an event id (no extension)."""
    slug = _SLUG_RE.sub("-", event_id.lower()).strip("-.")
    slug = _DASH_COLLAPSE_RE.sub("-", slug)
    return slug or "event"


_XML_ESCAPES: tuple[tuple[str, str], ...] = (
    ("&", "&amp;"),
    ("<", "&lt;"),
    (">", "&gt;"),
    ('"', "&quot;"),
    ("'", "&apos;"),
)


def _xml_escape(text: str) -> str:
    """XML-escape text for safe embedding inside ``<text>`` and attributes."""
    for needle, replacement in _XML_ESCAPES:
        text = text.replace(needle, replacement)
    return text


def _format_date(date_str: str) -> str:
    """Render ``YYYY-MM-DD`` as ``Mon Day, Year``; pass-through on failure."""
    try:
        parsed = datetime.strptime(date_str, "%Y-%m-%d")
    except (TypeError, ValueError):
        return date_str or ""
    return parsed.strftime("%b %-d, %Y") if sys.platform != "win32" else parsed.strftime("%b %d, %Y")


def _wrap_title(title: str, max_chars: int, max_lines: int) -> list[str]:
    """Greedy word-wrap a title to at most ``max_lines`` of ``max_chars``."""
    if not title:
        return [""]

    words = title.split()
    lines: list[str] = []
    current = ""

    for word in words:
        if len(lines) >= max_lines:
            break
        if len(word) > max_chars:
            if current:
                lines.append(current)
                current = ""
                if len(lines) >= max_lines:
                    break
            lines.append(word[: max_chars - 1] + ELLIPSIS)
            continue
        candidate = f"{current} {word}".strip()
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current and len(lines) < max_lines:
        lines.append(current)

    remaining_words = words[sum(len(line.split()) for line in lines) :]
    if remaining_words and lines:
        last = lines[-1]
        if len(last) > max_chars - 1:
            last = last[: max_chars - 1]
        lines[-1] = f"{last}{ELLIPSIS}"
    return lines or [""]


def _first_screening_date(event: dict) -> str:
    screenings = event.get("screenings") or []
    for s in screenings:
        if isinstance(s, dict) and s.get("date"):
            return str(s["date"])
    dates = event.get("dates") or []
    if isinstance(dates, list) and dates:
        return str(dates[0])
    return ""


def _first_venue(event: dict) -> str:
    screenings = event.get("screenings") or []
    for s in screenings:
        if isinstance(s, dict) and s.get("venue"):
            return str(s["venue"])
    return str(event.get("venue") or "")


def _rating_int(value: object) -> Optional[int]:
    if value is None:
        return None
    try:
        rating = int(value)
    except (TypeError, ValueError):
        return None
    if rating < 0 or rating > 10:
        return None
    return rating


def _normalize_event(event: dict) -> Optional[CardData]:
    if not isinstance(event, dict):
        return None
    event_id = event.get("id") or event.get("title")
    if not event_id:
        return None
    title = str(event.get("title") or "Untitled").strip() or "Untitled"
    type_ = str(event.get("type") or "other").strip() or "other"
    return CardData(
        event_id=str(event_id),
        title=title,
        venue=_first_venue(event),
        date=_first_screening_date(event),
        rating=_rating_int(event.get("rating")),
        type_=type_,
    )


def _theme_for(type_: str) -> tuple[str, str, str]:
    return _CATEGORY_THEME.get(type_, _CATEGORY_THEME["other"])


def _category_label(type_: str) -> str:
    return _CATEGORY_LABEL.get(type_, _CATEGORY_LABEL["other"])


def render_svg(card: CardData) -> str:
    """Render one CardData into a self-contained SVG string."""
    stop1, stop2, accent = _theme_for(card.type_)
    category_label = _category_label(card.type_)

    title_lines = _wrap_title(
        card.title, TITLE_MAX_CHARS_PER_LINE, TITLE_MAX_LINES
    )
    escaped_lines = [_xml_escape(line) for line in title_lines]

    title_tspans: list[str] = []
    title_start_y = 260
    line_height = 86
    for idx, line in enumerate(escaped_lines):
        dy = 0 if idx == 0 else line_height
        title_tspans.append(
            f'<tspan x="80" dy="{dy}">{line}</tspan>'
        )
    title_block = (
        f'<text x="80" y="{title_start_y}" fill="#f5f2ec" '
        f'font-family="Georgia, \'Times New Roman\', serif" '
        f'font-size="74" font-weight="700" letter-spacing="-1">'
        f'{"".join(title_tspans)}</text>'
    )

    venue = _xml_escape(card.venue.strip()) if card.venue else ""
    date = _xml_escape(_format_date(card.date))
    meta_bits = [bit for bit in (venue, date) if bit]
    meta_text = _xml_escape(" · ").join(bit for bit in meta_bits)
    if not meta_text:
        meta_text = _xml_escape("Austin")

    if card.rating is not None:
        rating_text = f"{card.rating} / 10"
        rating_badge = (
            '<g transform="translate(940,500)">'
            f'<rect x="0" y="0" width="180" height="72" rx="36" ry="36" '
            f'fill="{accent}" opacity="0.95"/>'
            f'<text x="90" y="48" text-anchor="middle" fill="#0b0b10" '
            f'font-family="Inter, \'Helvetica Neue\', Arial, sans-serif" '
            f'font-size="36" font-weight="700">{rating_text}</text>'
            "</g>"
        )
    else:
        rating_badge = (
            '<g transform="translate(820,500)">'
            '<rect x="0" y="0" width="300" height="72" rx="36" ry="36" '
            'fill="none" stroke="#f5f2ec" stroke-opacity="0.35" stroke-width="2"/>'
            '<text x="150" y="48" text-anchor="middle" fill="#f5f2ec" '
            'font-family="Inter, \'Helvetica Neue\', Arial, sans-serif" '
            'font-size="28" font-weight="500" opacity="0.8">'
            "Pending review</text>"
            "</g>"
        )

    brand_chip = (
        '<g transform="translate(80,80)">'
        '<text x="0" y="0" fill="#f5f2ec" '
        'font-family="Inter, \'Helvetica Neue\', Arial, sans-serif" '
        'font-size="24" font-weight="600" letter-spacing="4">'
        "CULTURE CALENDAR</text>"
        '<text x="0" y="34" fill="#f5f2ec" opacity="0.65" '
        'font-family="Inter, \'Helvetica Neue\', Arial, sans-serif" '
        'font-size="18" font-weight="400" letter-spacing="2">'
        "AUSTIN, AI-CURATED</text>"
        "</g>"
    )

    category_chip = (
        f'<g transform="translate({CARD_WIDTH - 80},80)">'
        f'<rect x="-180" y="-30" width="180" height="48" rx="24" ry="24" '
        f'fill="{accent}" opacity="0.18"/>'
        f'<text x="-90" y="4" text-anchor="middle" fill="{accent}" '
        f'font-family="Inter, \'Helvetica Neue\', Arial, sans-serif" '
        f'font-size="22" font-weight="600" letter-spacing="2">'
        f"{_xml_escape(category_label.upper())}</text>"
        "</g>"
    )

    meta_line = (
        f'<text x="80" y="540" fill="#f5f2ec" opacity="0.8" '
        f'font-family="Inter, \'Helvetica Neue\', Arial, sans-serif" '
        f'font-size="30" font-weight="500">{meta_text}</text>'
    )

    accent_bar = (
        f'<rect x="80" y="200" width="64" height="6" rx="3" ry="3" '
        f'fill="{accent}"/>'
    )

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {CARD_WIDTH} {CARD_HEIGHT}" '
        f'width="{CARD_WIDTH}" height="{CARD_HEIGHT}">'
        "<defs>"
        '<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0%" stop-color="{stop1}"/>'
        f'<stop offset="100%" stop-color="{stop2}"/>'
        "</linearGradient>"
        "</defs>"
        f'<rect width="{CARD_WIDTH}" height="{CARD_HEIGHT}" fill="url(#bg)"/>'
        f'<rect width="{CARD_WIDTH}" height="{CARD_HEIGHT}" '
        f'fill="{accent}" opacity="0.04"/>'
        f"{brand_chip}"
        f"{category_chip}"
        f"{accent_bar}"
        f"{title_block}"
        f"{meta_line}"
        f"{rating_badge}"
        "</svg>\n"
    )


def load_events(data_path: Path = DATA_PATH) -> list[dict]:
    if not data_path.exists():
        raise FileNotFoundError(f"Missing data file: {data_path}")
    with data_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, list):
        raise ValueError(f"{data_path} is not a JSON array")
    return payload


def _iter_cards(events: Iterable[dict]) -> Iterable[CardData]:
    for event in events:
        card = _normalize_event(event)
        if card is not None:
            yield card


def write_cards(
    events: Sequence[dict],
    *,
    out_dir: Path = OUT_DIR,
    clean: bool = True,
) -> int:
    """Render every event to ``out_dir/<event_id>.svg``.

    ``clean=True`` removes stale ``.svg`` files that aren't re-emitted this
    run so the directory stays in sync with ``data.json``.
    Returns the number of cards written.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    written: set[Path] = set()
    for card in _iter_cards(events):
        filename = f"{_safe_filename(card.event_id)}.svg"
        dest = out_dir / filename
        dest.write_text(render_svg(card), encoding="utf-8")
        written.add(dest)

    if clean:
        for existing in out_dir.glob("*.svg"):
            if existing not in written:
                try:
                    existing.unlink()
                except OSError as exc:  # pragma: no cover - defensive
                    LOG.warning("Could not remove stale %s: %s", existing, exc)

    return len(written)


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
        help="Output directory for SVG cards (default: %(default)s).",
    )
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="Keep stale SVGs that no longer correspond to an event.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress the summary line on stdout.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    events = load_events(args.data)
    count = write_cards(events, out_dir=args.out_dir, clean=not args.no_clean)

    if not args.quiet:
        print(f"Wrote {count} SVG cards to {args.out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
