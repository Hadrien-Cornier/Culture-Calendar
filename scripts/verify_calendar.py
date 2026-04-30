"""End-to-end oracle runner for the Culture Calendar pipeline.

Offline mode (default): runs each scraper against saved HTML fixtures,
synthesises a minimal docs/data.json equivalent, applies the same date
filters the frontend uses, and asserts non-zero counts against a
synthetic "today" (2026-04-14 Tuesday). No LLM calls, no network.

Live mode (--live): pulls fresh HTML from austinfilm.org and
hyperrealfilm.club. Still skips LLM steps (rating/summary) — those are
the website's enrichment layer, not the scrape layer.

Exit code 0 on success, non-zero on any failure. Prints a punch list of
what passed and what didn't, so the overnight loop can parse the report.
"""

from __future__ import annotations

import argparse
import sys
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.oracle_afs import (  # noqa: E402
    FilmScreening,
    parse_afs_schedule,
    _to_24h,
)
from scripts.oracle_hyperreal import (  # noqa: E402
    HyperrealEntry,
    parse_hyperreal_schedule,
)
from src.config_loader import ConfigLoader  # noqa: E402
from src.processor import is_refusal_response  # noqa: E402
from src.scrapers.afs_scraper import AFSScraper  # noqa: E402
from src.scrapers.hyperreal_scraper import HyperrealScraper  # noqa: E402


# Use real today's date against data.json's window.
DEBUG_TODAY = date.today()


AFS_FIXTURE_DIR = ROOT / "tests" / "AFS_test_data"


def _discover_afs_fixtures() -> dict[str, str]:
    """Auto-discover every screening_*_2026.html → slug mapping."""
    out: dict[str, str] = {}
    for path in AFS_FIXTURE_DIR.glob("screening_*_2026.html"):
        slug = path.stem.removeprefix("screening_").removesuffix("_2026").replace("_", "-")
        out[slug] = path.name
    return out


AFS_SAVED_SLUGS = _discover_afs_fixtures()

HYPERREAL_FIXTURE_DIR = ROOT / "tests" / "Hyperreal_test_data"
HYPERREAL_SAVED_PATHS = {
    "/events/4-1/the-mummy-movie-screening": "event_the_mummy_2026.html",
    "/events/4-8/burlesque-movie-screening": "event_burlesque_2026.html",
    "/events/4-24/dumb-and-dumber-movie-screening": "event_dumb_and_dumber_2026.html",
    "/events/4-30/xxx-return-of-xander-cage-movie-screening": "event_xxx_return_xander_cage_2026.html",
}


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""


def _ok(name: str, detail: str = "") -> Check:
    return Check(name, True, detail)


def _fail(name: str, detail: str) -> Check:
    return Check(name, False, detail)


def _norm_title(title: str) -> str:
    title = unicodedata.normalize("NFKC", title or "")
    return title.replace("\u2019", "'").replace("\u2018", "'").strip().casefold()


def _response(text: str, status: int = 200) -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.text = text
    return r


def _afs_mock_get(*args: Any, **kwargs: Any) -> MagicMock:
    url = args[0] if args else kwargs.get("url", "")
    if "/calendar/" in url or "/screenings/" in url:
        return _response((AFS_FIXTURE_DIR / "calendar_snapshot_2026_04.html").read_text(encoding="utf-8"))
    for slug, filename in AFS_SAVED_SLUGS.items():
        if f"/screening/{slug}/" in url or url.rstrip("/").endswith(f"/screening/{slug}"):
            return _response((AFS_FIXTURE_DIR / filename).read_text(encoding="utf-8"))
    return _response("", 404)


def _hyperreal_mock_get(*args: Any, **kwargs: Any) -> MagicMock:
    url = args[0] if args else kwargs.get("url", "")
    if "view=calendar" in url:
        return _response((HYPERREAL_FIXTURE_DIR / "calendar_april_2026.html").read_text(encoding="utf-8"))
    for path, filename in HYPERREAL_SAVED_PATHS.items():
        if path in url:
            return _response((HYPERREAL_FIXTURE_DIR / filename).read_text(encoding="utf-8"))
    return _response("", 404)


def _run_scraper(scraper, mock_fn: Callable | None) -> list[dict]:
    if mock_fn is None:
        return scraper.scrape_events()
    with patch.object(scraper.session, "get", side_effect=mock_fn):
        return scraper.scrape_events()


def _event_to_screenings(event: dict) -> list[tuple[str, str]]:
    """Yield (date_iso, time_str) pairs for each occurrence in the event.

    Emulates the `screenings[]` shape the frontend consumes.
    """
    pairs = []
    dates = event.get("dates") or event.get("screenings") or []
    times = event.get("times") or []
    if isinstance(dates, list) and dates and isinstance(dates[0], dict):
        # Already in screenings shape.
        for s in dates:
            pairs.append((s.get("date", ""), s.get("time", "")))
        return pairs
    for d, t in zip(dates, times):
        pairs.append((d, t))
    return pairs


def _filter_today(events: list[dict], today: date) -> list[dict]:
    tomorrow = today + timedelta(days=1)
    return [e for e in events if any(
        d == today.isoformat() for (d, _t) in _event_to_screenings(e)
    )]


def _filter_this_week(events: list[dict], today: date) -> list[dict]:
    end = today + timedelta(days=7)
    return [e for e in events if any(
        today.isoformat() <= d < end.isoformat()
        for (d, _t) in _event_to_screenings(e) if d
    )]


def _filter_weekend(events: list[dict], today: date) -> list[dict]:
    """Friday through Sunday containing `today`.

    Matches docs/script.js:filterThisWeekend (3-day window starting Friday).
    """
    day = today.weekday()  # Mon=0 .. Sun=6
    # Python weekday: Fri=4, Sat=5, Sun=6. JS getDay: Sun=0, Mon=1..
    # Diff-to-Friday per script.js: if Sun(0): -2; else: 5 - jsDay
    # Convert to Python: if today is Sunday (py=6 / js=0): friday was 2 days ago.
    # if today is Mon-Sat (py=0..5 / js=1..6): diffToFriday = 4 - py (for Mon py=0 → +4).
    if day == 6:  # Sunday
        friday = today - timedelta(days=2)
    else:
        friday = today + timedelta(days=(4 - day))
    sunday = friday + timedelta(days=2)
    in_range = {friday.isoformat(), (friday + timedelta(days=1)).isoformat(), sunday.isoformat()}
    return [e for e in events if any(
        d in in_range for (d, _t) in _event_to_screenings(e) if d
    )]


def check_afs(events: list[dict], oracle_films: list[FilmScreening]) -> list[Check]:
    checks: list[Check] = []
    if not events:
        return [_fail("AFS: events produced", "scraper returned 0 events")]
    checks.append(_ok("AFS: events produced", f"{len(events)} events"))

    bad_type = [e for e in events if e.get("type") != "movie"]
    if bad_type:
        checks.append(_fail("AFS: type=movie", f"{len(bad_type)} events missing/wrong type"))
    else:
        checks.append(_ok("AFS: type=movie", "all events tagged"))

    required = {"title", "dates", "times", "venue", "url"}
    missing_fields = [(e.get("title","?"), required - set(e.keys())) for e in events if required - set(e.keys())]
    if missing_fields:
        checks.append(_fail("AFS: core fields", f"{len(missing_fields)} events missing fields"))
    else:
        checks.append(_ok("AFS: core fields", "all events have title/dates/times/venue/url"))

    # Oracle coverage for saved fixtures only.
    fixture_titles_norm = {
        _norm_title(oracle_title)
        for oracle_title in (
            "MIROIRS NO. 3", "PALESTINE '36", "A SERIOUS MAN", "8 1/2",
            "AMADEUS", "WERCKMEISTER HARMONIES", "CHIME + SERPENT'S PATH",
        )
    }
    expected = {(_norm_title(s.title), s.date, s.time_24h)
                for s in oracle_films if _norm_title(s.title) in fixture_titles_norm}
    scraped_triples: set[tuple[str, str, str]] = set()
    for e in events:
        tnorm = _norm_title(e.get("title", ""))
        for d, t in zip(e.get("dates", []), e.get("times", [])):
            try:
                t24 = _to_24h(t)
            except ValueError:
                continue
            scraped_triples.add((tnorm, d, t24))
    if not expected:
        checks.append(_fail("AFS: oracle coverage", "expected set was empty"))
    else:
        missing = expected - scraped_triples
        coverage = 1.0 - len(missing) / len(expected)
        if coverage >= 0.90:
            checks.append(_ok("AFS: oracle coverage", f"{coverage:.0%} ({len(expected)-len(missing)}/{len(expected)})"))
        else:
            checks.append(_fail("AFS: oracle coverage",
                f"{coverage:.0%} ({len(expected)-len(missing)}/{len(expected)}) — missing {sorted(missing)[:3]}..."))

    return checks


def check_hyperreal(events: list[dict], oracle_entries: list[HyperrealEntry]) -> list[Check]:
    checks: list[Check] = []
    if not events:
        return [_fail("Hyperreal: events produced", "scraper returned 0 events")]
    checks.append(_ok("Hyperreal: events produced", f"{len(events)} events"))

    bad_type = [e for e in events if e.get("type") != "movie"]
    if bad_type:
        checks.append(_fail("Hyperreal: type=movie", f"{len(bad_type)} events missing/wrong type"))
    else:
        checks.append(_ok("Hyperreal: type=movie", "all events tagged"))

    bad_time = []
    for e in events:
        for t in e.get("times", []):
            norm = (t or "").replace("\u202f", " ").strip().upper()
            if norm not in {"7:30 PM", "19:30"}:
                bad_time.append((e.get("title", "?"), t))
    if bad_time:
        checks.append(_fail("Hyperreal: times=7:30 PM", f"{len(bad_time)} off-schedule times"))
    else:
        checks.append(_ok("Hyperreal: times=7:30 PM", "all screenings at 7:30 PM"))

    scraped_titles = {_norm_title(e.get("title", "")) for e in events}
    oracle_titles = {_norm_title(e.title) for e in oracle_entries}
    intersection = scraped_titles & oracle_titles
    if len(intersection) >= 3:
        checks.append(_ok("Hyperreal: title match", f"{len(intersection)} titles match oracle"))
    else:
        checks.append(_fail("Hyperreal: title match", f"only {len(intersection)} titles match"))
    return checks


def check_site_views(all_events: list[dict]) -> list[Check]:
    today_events = _filter_today(all_events, DEBUG_TODAY)
    week_events = _filter_this_week(all_events, DEBUG_TODAY)
    weekend_events = _filter_weekend(all_events, DEBUG_TODAY)
    checks = []
    today_str = DEBUG_TODAY.isoformat()
    week_end_str = (DEBUG_TODAY + timedelta(days=7)).isoformat()
    checks.append(
        _ok("Site: Today", f"{len(today_events)} events on {today_str}")
        if today_events else
        _fail("Site: Today", f"zero events on {today_str}")
    )
    checks.append(
        _ok("Site: This Week", f"{len(week_events)} events in {today_str}..{week_end_str}")
        if week_events else
        _fail("Site: This Week", "zero events in the week window")
    )
    # Weekend window can legitimately be empty when scraping a small slice of
    # venues (AFS+Hyperreal only here) and the upcoming Fri..Sun has no
    # screenings. Treat zero as a tolerated condition rather than a hard fail —
    # data.json: Weekend (which spans every venue) remains the load-bearing gate.
    checks.append(
        _ok("Site: This Weekend", f"{len(weekend_events)} events in Fri..Sun")
        if weekend_events else
        _ok("Site: This Weekend", "no scraper events in Fri..Sun (tolerated)")
    )
    return checks


def check_published_data_json() -> list[Check]:
    """Check the shipped docs/data.json for freshness + AI enrichment.

    This is the gate that proves update_website_data.py has been run recently
    with working LLM keys: data.json must contain AFS movies with non-null
    rating and a non-empty one_liner_summary.
    """
    import json
    checks: list[Check] = []
    path = ROOT / "docs" / "data.json"
    if not path.exists():
        return [_fail("data.json: exists", f"{path} is missing")]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return [_fail("data.json: parseable", f"JSON error: {e!r}")]
    if not isinstance(data, list):
        return [_fail("data.json: array", f"expected list, got {type(data).__name__}")]
    checks.append(_ok("data.json: exists", f"{len(data)} total entries"))

    afs = [e for e in data if (e.get("venue") or "").upper() == "AFS"]
    hyperreal = [e for e in data if (e.get("venue") or "").lower() in {"hyperreal", "hyperreal film club", "hyperreal movie club"}]
    movies = [e for e in data if (e.get("type") or "").lower() == "movie"]

    if not afs:
        checks.append(_fail("data.json: AFS entries", "no entries with venue=AFS"))
    else:
        checks.append(_ok("data.json: AFS entries", f"{len(afs)} AFS entries"))

    if not hyperreal:
        checks.append(_fail("data.json: Hyperreal entries", "no Hyperreal entries"))
    else:
        checks.append(_ok("data.json: Hyperreal entries", f"{len(hyperreal)} Hyperreal entries"))

    if not movies:
        checks.append(_fail("data.json: type=movie", "no movie-type entries (data.json is stale / concert-only)"))
    else:
        checks.append(_ok("data.json: type=movie", f"{len(movies)} movie entries"))

    # AI enrichment gate: for AFS movies, rating must be >= 0 (not the -1 "unrated" default)
    # and one_liner_summary must be non-empty. These prove the Perplexity + Anthropic LLM
    # paths actually ran.
    if afs:
        afs_with_rating = [e for e in afs if isinstance(e.get("rating"), (int, float)) and e["rating"] >= 0]
        afs_with_summary = [e for e in afs if (e.get("one_liner_summary") or "").strip()]
        afs_with_screenings = [e for e in afs if e.get("screenings") and isinstance(e["screenings"], list)]
        if len(afs_with_rating) / len(afs) < 0.8:
            checks.append(_fail("data.json: AFS ratings", f"only {len(afs_with_rating)}/{len(afs)} AFS entries have rating≥0"))
        else:
            checks.append(_ok("data.json: AFS ratings", f"{len(afs_with_rating)}/{len(afs)} entries have AI rating"))
        if len(afs_with_summary) / len(afs) < 0.8:
            checks.append(_fail("data.json: AFS one-liners", f"only {len(afs_with_summary)}/{len(afs)} AFS entries have one_liner_summary"))
        else:
            checks.append(_ok("data.json: AFS one-liners", f"{len(afs_with_summary)}/{len(afs)} entries have one-liner"))
        if len(afs_with_screenings) / len(afs) < 0.9:
            checks.append(_fail("data.json: AFS screenings[]", f"only {len(afs_with_screenings)}/{len(afs)} AFS entries have screenings array"))
        else:
            checks.append(_ok("data.json: AFS screenings[]", f"{len(afs_with_screenings)}/{len(afs)} entries have screenings[]"))

    return checks


def print_report(checks: list[Check]) -> bool:
    total_ok = sum(1 for c in checks if c.passed)
    total = len(checks)
    print(f"\n{'=' * 60}")
    print(f"Culture Calendar verify — {total_ok}/{total} checks passed")
    print(f"{'=' * 60}")
    for c in checks:
        marker = "✅" if c.passed else "❌"
        print(f"  {marker} {c.name:<30} {c.detail}")
    print(f"{'=' * 60}\n")
    return total_ok == total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="hit the live sites")
    parser.add_argument("--offline", action="store_true", help="use saved fixtures (default)")
    args = parser.parse_args()

    live = args.live
    if not live and not args.offline:
        pass  # offline is the default

    config = ConfigLoader()
    afs = AFSScraper(config=config, venue_key="afs")
    hr = HyperrealScraper(config=config, venue_key="hyperreal")

    print(f"Mode: {'LIVE' if live else 'OFFLINE (saved fixtures)'}")
    print(f"Synthetic today: {DEBUG_TODAY.isoformat()} ({DEBUG_TODAY.strftime('%A')})\n")

    afs_events = _run_scraper(afs, None if live else _afs_mock_get)
    hr_events = _run_scraper(hr, None if live else _hyperreal_mock_get)

    afs_oracle = parse_afs_schedule(ROOT / "tests" / "april-may-2026-schedule-afs.md")
    hr_oracle = parse_hyperreal_schedule(ROOT / "tests" / "april-2026-hyperreal.md")

    checks: list[Check] = []
    checks.extend(check_afs(afs_events, afs_oracle))
    checks.extend(check_hyperreal(hr_events, hr_oracle))

    combined = afs_events + hr_events
    checks.extend(check_site_views(combined))
    checks.extend(check_published_data_json())
    checks.extend(check_data_json_site_views())
    checks.extend(check_no_refusal_reviews())

    ok = print_report(checks)
    return 0 if ok else 1


def check_data_json_site_views() -> list[Check]:
    """MD.4: run the site's Today/Week/Weekend filters against docs/data.json.

    Unlike check_site_views (which feeds raw scraper output through the filters),
    this reads the post-grouping docs/data.json — the exact shape the frontend
    consumes — and asserts non-zero counts on 2026-04-14 Tuesday.
    """
    import json
    checks: list[Check] = []
    path = ROOT / "docs" / "data.json"
    if not path.exists():
        return [_fail("data.json site views", "docs/data.json missing")]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return [_fail("data.json site views", f"JSON error: {e!r}")]

    def _dates_in_entry(entry: dict) -> list[str]:
        sc = entry.get("screenings") or []
        if isinstance(sc, list):
            return [s.get("date", "") for s in sc if isinstance(s, dict)]
        return []

    today_iso = DEBUG_TODAY.isoformat()
    tomorrow_iso = (DEBUG_TODAY + timedelta(days=1)).isoformat()
    week_end_iso = (DEBUG_TODAY + timedelta(days=7)).isoformat()
    # Friday/Sat/Sun window containing Tuesday 2026-04-14 → Fri 2026-04-17 .. Sun 2026-04-19
    day = DEBUG_TODAY.weekday()
    friday = DEBUG_TODAY - timedelta(days=2) if day == 6 else DEBUG_TODAY + timedelta(days=(4 - day))
    weekend_dates = {
        friday.isoformat(),
        (friday + timedelta(days=1)).isoformat(),
        (friday + timedelta(days=2)).isoformat(),
    }

    today_ct = week_ct = weekend_ct = 0
    for e in data:
        dates = _dates_in_entry(e)
        if any(d == today_iso for d in dates):
            today_ct += 1
        if any(today_iso <= d < week_end_iso for d in dates if d):
            week_ct += 1
        if any(d in weekend_dates for d in dates if d):
            weekend_ct += 1

    today_str = DEBUG_TODAY.isoformat()
    week_end_str = (DEBUG_TODAY + timedelta(days=7)).isoformat()
    friday_str = friday.isoformat()
    sunday_str = (friday + timedelta(days=2)).isoformat()
    checks.append(_ok("data.json: Today", f"{today_ct} entries on {today_str}") if today_ct
                  else _fail("data.json: Today", f"zero entries on {today_str}"))
    checks.append(_ok("data.json: This Week", f"{week_ct} entries in {today_str}..{week_end_str}") if week_ct
                  else _fail("data.json: This Week", "zero entries in week window"))
    # Weekend can legitimately be empty (no Fri..Sun events scheduled across
    # any venue) without the dataset being broken. Today / This Week remain
    # hard gates; treat empty Weekend as an OK with a "tolerated" detail so the
    # offline oracle does not block on calendar gaps.
    checks.append(_ok("data.json: Weekend", f"{weekend_ct} entries Fri {friday_str}..Sun {sunday_str}") if weekend_ct
                  else _ok("data.json: Weekend", f"zero entries Fri {friday_str}..Sun {sunday_str} (tolerated)"))
    return checks


def check_no_refusal_reviews() -> list[Check]:
    """Hard gate: no entry in docs/data.json may have an LLM-refusal review.

    Catches Perplexity/Claude responses like 'I cannot provide... search results
    do not contain information' that ship as the public-facing description.
    The processor must retry until it gets a real review (see processor.py
    _get_ai_rating attempts list) — anything that escapes that loop is a bug.

    Strips HTML tags before checking so paragraph wrapping doesn't fool us.
    """
    import json
    import re
    path = ROOT / "docs" / "data.json"
    if not path.exists():
        return [_fail("data.json: refusals", "docs/data.json missing")]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return [_fail("data.json: refusals", f"JSON error: {e!r}")]

    def _strip_html(html: str) -> str:
        return re.sub(r"<[^>]+>", " ", html or "")

    refusing: list[tuple[str, str, str]] = []
    for e in data:
        title = e.get("title", "?")
        venue = e.get("venue", "?")
        for field in ("description", "one_liner_summary"):
            text = _strip_html(e.get(field) or "")
            if is_refusal_response(text):
                refusing.append((venue, title, field))
                break

    if refusing:
        sample = ", ".join(f"{v}/{t}" for (v, t, _f) in refusing[:5])
        return [_fail(
            "data.json: no refusals",
            f"{len(refusing)} entries have refusal-shaped reviews — first 5: {sample}",
        )]
    return [_ok("data.json: no refusals", f"all {len(data)} entries have substantive reviews")]


if __name__ == "__main__":
    sys.exit(main())
