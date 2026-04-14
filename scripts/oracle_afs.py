"""Parse the AFS schedule markdown oracle into machine-checkable tuples.

The markdown file `tests/april-may-2026-schedule-afs.md` is the ground truth
for what the AFS scraper must recover. This module turns it into a list of
`FilmScreening` records so tests and the end-to-end verifier can compare.

Classification rule (film vs. class/workshop):
  - Title is all uppercase after stripping punctuation/whitespace → film.
  - Title has no alphabetic characters at all (e.g. "8 1/2") → film.
  - Otherwise (Title Case with letters, e.g. "Producer Program Info Session") → class, skip.

Date format: markdown uses section headers like `### Monday, April 13`. Month
is pulled from the preceding `## <Month> <Year>` block. Times within a line
are comma-separated (`— 12:30 PM, 6:15 PM`), each becomes a separate record.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


@dataclass(frozen=True)
class FilmScreening:
    title: str
    date: str          # YYYY-MM-DD
    time_12h: str      # e.g. "5:15 PM"
    time_24h: str      # e.g. "17:15"


def _normalize_title(title: str) -> str:
    return re.sub(r"\s+", " ", title.strip())


def is_film_title(title: str) -> bool:
    """A title is a film iff it's ALL CAPS or has no alphabetic characters."""
    alpha = [c for c in title if c.isalpha()]
    if not alpha:
        return True  # "8 1/2" and the like
    return all(c.isupper() for c in alpha)


def _to_24h(time_12h: str) -> str:
    """Convert '5:15 PM' → '17:15'. Raises ValueError on malformed input."""
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*([AP]M)\s*", time_12h, flags=re.IGNORECASE)
    if not m:
        raise ValueError(f"Unparseable time: {time_12h!r}")
    hour, minute, ampm = int(m.group(1)), int(m.group(2)), m.group(3).upper()
    if ampm == "AM":
        hour = 0 if hour == 12 else hour
    else:
        hour = 12 if hour == 12 else hour + 12
    return f"{hour:02d}:{minute:02d}"


def parse_afs_schedule(markdown_path: str | Path) -> list[FilmScreening]:
    """Parse the AFS markdown fixture and return only film screenings."""
    path = Path(markdown_path)
    if not path.exists():
        raise FileNotFoundError(path)
    text = path.read_text(encoding="utf-8")

    current_year: int | None = None
    current_month: int | None = None
    current_day: int | None = None
    screenings: list[FilmScreening] = []

    month_header = re.compile(r"^##\s+([A-Za-z]+)\s+(\d{4})\s*$")
    day_header = re.compile(
        r"^###\s+(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+"
        r"([A-Za-z]+)\s+(\d{1,2})\s*$"
    )
    entry_line = re.compile(r"^-\s*\*\*(.+?)\*\*\s*[—–-]\s*(.+?)\s*$")

    for line in text.splitlines():
        line = line.rstrip()
        if not line:
            continue

        mh = month_header.match(line)
        if mh:
            current_month = MONTHS.get(mh.group(1).lower())
            current_year = int(mh.group(2))
            continue

        dh = day_header.match(line)
        if dh:
            month_name = dh.group(2).lower()
            if month_name in MONTHS:
                current_month = MONTHS[month_name]
            current_day = int(dh.group(3))
            continue

        em = entry_line.match(line)
        if not em or current_year is None or current_month is None or current_day is None:
            continue
        raw_title, raw_times = em.group(1), em.group(2)
        title = _normalize_title(raw_title)
        if not is_film_title(title):
            continue

        date_iso = f"{current_year:04d}-{current_month:02d}-{current_day:02d}"
        for chunk in [t.strip() for t in raw_times.split(",")]:
            if not chunk:
                continue
            try:
                time_24h = _to_24h(chunk)
            except ValueError:
                continue
            screenings.append(
                FilmScreening(title=title, date=date_iso, time_12h=chunk, time_24h=time_24h)
            )

    return screenings


def iter_unique_titles(screenings: list[FilmScreening]) -> Iterator[str]:
    seen: set[str] = set()
    for s in screenings:
        if s.title not in seen:
            seen.add(s.title)
            yield s.title


if __name__ == "__main__":
    import json
    import sys

    default = Path(__file__).resolve().parents[1] / "tests" / "april-may-2026-schedule-afs.md"
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else default
    rows = parse_afs_schedule(target)
    print(json.dumps(
        [{"title": r.title, "date": r.date, "time_12h": r.time_12h, "time_24h": r.time_24h} for r in rows],
        indent=2,
    ))
    print(f"\nTotal film screenings: {len(rows)}", file=sys.stderr)
    print(f"Unique film titles:    {len(list(iter_unique_titles(rows)))}", file=sys.stderr)
