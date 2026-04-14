"""Parse the Hyperreal schedule markdown oracle into machine-checkable tuples.

The file `tests/april-2026-hyperreal.md` lists April 2026 screenings as a
simple two-column table: `Date\tEvent / Film`. All times are 7:30 PM. Lines
suffixed with `(live event)` or matching the "festival" / "LIVE" / "Night"
patterns are live events, not films, and are flagged separately.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


MONTHS_ABBR = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

DEFAULT_TIME_12H = "7:30 PM"
DEFAULT_TIME_24H = "19:30"

LIVE_MARKERS = (
    r"\(live event\)",
    r"\bLIVE\b",
    r"\bFilm Festival\b",
    r"\bNight!",
)


@dataclass(frozen=True)
class HyperrealEntry:
    title: str
    date: str          # YYYY-MM-DD
    time_12h: str
    time_24h: str
    is_live_event: bool


def _looks_live(title: str) -> bool:
    for pat in LIVE_MARKERS:
        if re.search(pat, title, flags=re.IGNORECASE):
            return True
    return False


def parse_hyperreal_schedule(markdown_path: str | Path, default_year: int = 2026) -> list[HyperrealEntry]:
    """Parse the Hyperreal markdown fixture.

    Returns every entry (films AND live events), tagged with is_live_event so
    callers can filter. Default year is pulled from the filename if it contains
    a 4-digit year; otherwise falls back to the `default_year` parameter.
    """
    path = Path(markdown_path)
    if not path.exists():
        raise FileNotFoundError(path)

    filename_year = re.search(r"(\d{4})", path.name)
    year = int(filename_year.group(1)) if filename_year else default_year

    text = path.read_text(encoding="utf-8")
    entries: list[HyperrealEntry] = []

    row = re.compile(r"^([A-Za-z]{3,4})\s+(\d{1,2})\s*\t(.+?)\s*$")

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        m = row.match(line)
        if not m:
            continue
        month_abbr = m.group(1).lower()
        day = int(m.group(2))
        raw_title = m.group(3).strip()
        month = MONTHS_ABBR.get(month_abbr)
        if month is None:
            continue
        title = re.sub(r"\s+\(live event\)\s*$", "", raw_title, flags=re.IGNORECASE).strip()
        date_iso = f"{year:04d}-{month:02d}-{day:02d}"
        entries.append(HyperrealEntry(
            title=title,
            date=date_iso,
            time_12h=DEFAULT_TIME_12H,
            time_24h=DEFAULT_TIME_24H,
            is_live_event=_looks_live(raw_title),
        ))

    return entries


def films_only(entries: list[HyperrealEntry]) -> list[HyperrealEntry]:
    return [e for e in entries if not e.is_live_event]


if __name__ == "__main__":
    import json
    import sys

    default = Path(__file__).resolve().parents[1] / "tests" / "april-2026-hyperreal.md"
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else default
    rows = parse_hyperreal_schedule(target)
    print(json.dumps(
        [dict(title=r.title, date=r.date, time_12h=r.time_12h, time_24h=r.time_24h, live=r.is_live_event)
         for r in rows],
        indent=2,
    ))
    print(f"\nTotal entries:    {len(rows)}", file=sys.stderr)
    print(f"Film screenings:  {len(films_only(rows))}", file=sys.stderr)
    print(f"Live events:      {sum(1 for r in rows if r.is_live_event)}", file=sys.stderr)
