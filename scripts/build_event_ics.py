"""Emit per-event ICS files at ``docs/events/<slug>.ics``.

Each file is a self-contained RFC 5545 calendar containing every
screening of a single event. The Apple Calendar share-menu entry
subscribes to ``webcal://…/events/<slug>.ics`` so the follow feed
keeps updating automatically; users who prefer a one-shot import can
also just download the file.

Slugs match :func:`scripts.build_event_shells._slugify` (itself a
thin alias over :func:`scripts._slug_util.safe_slug`), so
``docs/events/<slug>.html`` and ``docs/events/<slug>.ics`` line up
1:1 — deep links and follow feeds share a single identifier.

Implementation reuses :class:`scripts.build_ics_feed.Screening`,
:func:`scripts.build_ics_feed._iter_screenings` and
:func:`scripts.build_ics_feed._screening_to_vevent`. Keeping the
VEVENT shape in a single place avoids drift between the aggregate
feeds (``calendar.ics`` / ``top-picks.ics``) and these per-event
exports — a VEVENT emitted here is byte-identical to the one a
subscriber sees in the master feed.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Sequence

from icalendar import Calendar

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts._slug_util import safe_slug  # noqa: E402
from scripts.build_ics_feed import (  # noqa: E402
    AUSTIN_TZ,
    _create_timezone,
    _iter_screenings,
    _screening_to_vevent,
    load_events,
)

DATA_PATH = REPO_ROOT / "docs" / "data.json"
OUT_DIR = REPO_ROOT / "docs" / "events"

LOG = logging.getLogger("build_event_ics")


def _event_slug(event: dict) -> Optional[str]:
    """Return the per-event slug or ``None`` for unidentifiable events."""
    if not isinstance(event, dict):
        return None
    raw = event.get("id") or event.get("title") or ""
    if not raw:
        return None
    slug = safe_slug(str(raw))
    # safe_slug returns "event" for empty/symbol-only input; guard that case
    # the same way build_event_shells._shell_from_event does.
    if slug == "event" and not event.get("id") and not event.get("title"):
        return None
    return slug


def _build_event_calendar(
    event: dict,
    *,
    stamp: datetime,
) -> Optional[Calendar]:
    """Return an :class:`icalendar.Calendar` for one event, or ``None``.

    Returns ``None`` when the event has no screenings with a parseable
    date/time, so callers can simply skip unwriteable events without
    emitting an empty ``.ics``.
    """
    screenings = list(_iter_screenings([event]))
    if not screenings:
        return None

    title = str(event.get("title") or event.get("id") or "Untitled")

    cal = Calendar()
    cal.add("prodid", "-//Culture Calendar//Per-Event ICS//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", f"Culture Calendar — {title}")
    cal.add("x-wr-caldesc", f"All screenings of {title}")
    cal.add("x-wr-timezone", "America/Chicago")
    cal.add_component(_create_timezone())

    vevent_count = 0
    for screening in screenings:
        try:
            vevent = _screening_to_vevent(screening, stamp=stamp)
        except Exception as exc:  # pragma: no cover - defensive
            LOG.warning(
                "Failed to build VEVENT for %s (%s): %s",
                screening.title,
                screening.date,
                exc,
            )
            continue
        if vevent is not None:
            cal.add_component(vevent)
            vevent_count += 1

    if vevent_count == 0:
        return None
    return cal


def build_event_calendars(
    events: Sequence[dict],
    *,
    stamp: Optional[datetime] = None,
) -> dict[str, Calendar]:
    """Return ``{slug: Calendar}`` for every event with at least one VEVENT.

    Duplicates (same slug) resolve to the first occurrence — matching
    :func:`scripts.build_event_shells.build_shells` which de-dupes the
    same way for HTML shells.
    """
    stamp = stamp or datetime.now(AUSTIN_TZ)
    calendars: dict[str, Calendar] = {}
    for event in events:
        slug = _event_slug(event)
        if slug is None or slug in calendars:
            continue
        cal = _build_event_calendar(event, stamp=stamp)
        if cal is not None:
            calendars[slug] = cal
    return calendars


def write_event_ics(
    events: Sequence[dict],
    *,
    out_dir: Path = OUT_DIR,
    stamp: Optional[datetime] = None,
) -> int:
    """Write one ``<slug>.ics`` per event; return count written.

    Clears stale ``.ics`` files from a previous build so slugs that no
    longer appear in ``data.json`` don't leak forward — identical to
    :func:`scripts.build_event_shells.write_shells`'s stale-HTML sweep,
    scoped to ``*.ics`` only so companion ``.html`` / ``.json`` files
    emitted by other builders survive.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("*.ics"):
        stale.unlink()
    calendars = build_event_calendars(events, stamp=stamp)
    for slug, cal in calendars.items():
        (out_dir / f"{slug}.ics").write_bytes(cal.to_ical())
    return len(calendars)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--data",
        type=Path,
        default=DATA_PATH,
        help="Path to docs/data.json (default: %(default)s).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=OUT_DIR,
        help="Output directory for per-event ICS files.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress the summary line on stdout.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    events = load_events(args.data)
    count = write_event_ics(events, out_dir=args.out)
    if not args.quiet:
        print(f"Wrote {count} per-event ICS files to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
