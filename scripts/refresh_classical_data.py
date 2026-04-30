#!/usr/bin/env python3
"""LLM-driven monthly refresh for ``docs/classical_data.json`` and ``docs/ballet_data.json``.

This script is the skeleton stage (task 3.1a). Phase 3.1b will wire
:meth:`src.llm_service.LLMService.call_perplexity` into :func:`fetch_venue_data`;
phase 3.2 will add the GitHub Actions cron that opens a PR with the diff.
For now the skeleton supplies:

* ``validate_classical_data`` — schema check used by the validator unit tests
  AND by phases 3.1b/3.2 before they overwrite the on-disk JSON.
* ``--dry-run`` — runs the full pipeline against an in-memory stub instead
  of hitting Perplexity, so CI / the runner can exercise the script safely.
* ``--venue`` — restricts the refresh to one venue key (used by 3.1b's
  per-venue smoke run).

Output paths are kept stable so the workflow in phase 3.2 only has to commit
two JSON files.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

CLASSICAL_OUTPUT_PATH = Path("docs/classical_data.json")
BALLET_OUTPUT_PATH = Path("docs/ballet_data.json")

CLASSICAL_VENUE_KEYS: tuple[str, ...] = (
    "austinSymphony",
    "earlyMusicAustin",
    "laFolliaAustin",
    "austinChamberMusic",
    "austinOpera",
)
BALLET_VENUE_KEYS: tuple[str, ...] = ("balletAustin",)
ALL_VENUE_KEYS: tuple[str, ...] = CLASSICAL_VENUE_KEYS + BALLET_VENUE_KEYS

ALLOWED_EVENT_TYPES: tuple[str, ...] = ("concert", "opera", "dance")
REQUIRED_EVENT_FIELDS: tuple[str, ...] = (
    "title",
    "dates",
    "times",
    "venue_name",
    "type",
)
OPTIONAL_EVENT_FIELDS: tuple[str, ...] = (
    "program",
    "series",
    "featured_artist",
    "composers",
    "works",
)

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class RefreshResult:
    """Outcome of a refresh invocation."""

    venue_key: str
    events: list[dict[str, Any]]
    source: str  # "stub" | "perplexity"


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


def validate_event(event: Any, *, venue_key: str = "") -> list[str]:
    """Return a list of human-readable schema errors for one event."""
    errors: list[str] = []
    if not isinstance(event, dict):
        return [f"{venue_key or 'event'}: not a JSON object"]

    for field in REQUIRED_EVENT_FIELDS:
        if field not in event:
            errors.append(f"{venue_key}: missing required field '{field}'")

    title = event.get("title")
    if "title" in event and (not isinstance(title, str) or not title.strip()):
        errors.append(f"{venue_key}: 'title' must be a non-empty string")

    venue_name = event.get("venue_name")
    if "venue_name" in event and (not isinstance(venue_name, str) or not venue_name.strip()):
        errors.append(f"{venue_key}: 'venue_name' must be a non-empty string")

    event_type = event.get("type")
    if "type" in event and event_type not in ALLOWED_EVENT_TYPES:
        errors.append(
            f"{venue_key}: 'type' must be one of {ALLOWED_EVENT_TYPES}, got {event_type!r}"
        )

    dates = event.get("dates")
    times = event.get("times")
    if "dates" in event:
        if not isinstance(dates, list) or not dates:
            errors.append(f"{venue_key}: 'dates' must be a non-empty list")
        else:
            for d in dates:
                if not isinstance(d, str) or not _DATE_RE.match(d):
                    errors.append(
                        f"{venue_key}: 'dates' entry {d!r} must match YYYY-MM-DD"
                    )
                    break
    if "times" in event:
        if not isinstance(times, list) or not times:
            errors.append(f"{venue_key}: 'times' must be a non-empty list")
        else:
            for t in times:
                if not isinstance(t, str) or not t.strip():
                    errors.append(f"{venue_key}: 'times' entry {t!r} must be a non-empty string")
                    break

    if (
        isinstance(dates, list)
        and isinstance(times, list)
        and dates
        and times
        and len(dates) != len(times)
    ):
        errors.append(
            f"{venue_key}: 'dates' (len={len(dates)}) and 'times' (len={len(times)}) "
            "must be the same length (pairwise zip rule)"
        )

    for list_field in ("composers", "works"):
        if list_field in event and not isinstance(event[list_field], list):
            errors.append(f"{venue_key}: '{list_field}' must be a list when present")

    return errors


def validate_classical_data(
    data: Any,
    *,
    expected_venue_keys: Sequence[str] = CLASSICAL_VENUE_KEYS,
) -> list[str]:
    """Validate the full ``classical_data.json`` payload.

    The payload is shaped ``{venue_key: [event, ...], "lastUpdated": str?, "season": str?}``.
    Unknown top-level keys are tolerated (forward compatibility), but every
    venue key listed in ``expected_venue_keys`` MUST be present and map to a
    list of events that pass :func:`validate_event`.
    """
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["payload: not a JSON object"]

    for venue_key in expected_venue_keys:
        if venue_key not in data:
            errors.append(f"payload: missing venue key '{venue_key}'")
            continue
        events = data[venue_key]
        if not isinstance(events, list):
            errors.append(f"{venue_key}: must map to a list of events")
            continue
        for idx, ev in enumerate(events):
            errors.extend(validate_event(ev, venue_key=f"{venue_key}[{idx}]"))

    last_updated = data.get("lastUpdated")
    if last_updated is not None and not isinstance(last_updated, str):
        errors.append("payload: 'lastUpdated' must be a string when present")

    season = data.get("season")
    if season is not None and not isinstance(season, str):
        errors.append("payload: 'season' must be a string when present")

    return errors


# ---------------------------------------------------------------------------
# Stub data — used by --dry-run and as the seed for phase 3.1b
# ---------------------------------------------------------------------------


def _stub_event_for(venue_key: str) -> dict[str, Any]:
    """Return a canonical stub event for the given venue key."""
    if venue_key == "austinOpera":
        event_type = "opera"
        title = "Austin Opera Stub Production"
        venue_name = "The Long Center"
    elif venue_key == "balletAustin":
        event_type = "dance"
        title = "Ballet Austin Stub Production"
        venue_name = "The Long Center"
    else:
        event_type = "concert"
        title = f"{venue_key} Stub Concert"
        venue_name = "Stub Venue"

    return {
        "title": title,
        "program": "Stub program description for dry-run validation only.",
        "dates": ["2099-01-01"],
        "times": ["8:00 PM"],
        "venue_name": venue_name,
        "series": "Stub Series",
        "featured_artist": "Stub Artist",
        "composers": ["Stub Composer"],
        "works": ["Stub Work"],
        "type": event_type,
    }


def stub_fetch(venue_key: str) -> list[dict[str, Any]]:
    """Stub fetcher that returns one valid event per venue. Used by --dry-run."""
    return [_stub_event_for(venue_key)]


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def refresh_venues(
    venue_keys: Sequence[str],
    *,
    fetcher: Callable[[str], list[dict[str, Any]]],
    source_label: str = "stub",
) -> list[RefreshResult]:
    """Call ``fetcher(venue_key)`` for each requested venue, validating each result."""
    results: list[RefreshResult] = []
    for venue_key in venue_keys:
        events = fetcher(venue_key)
        if not isinstance(events, list):
            raise ValueError(f"fetcher for {venue_key} returned {type(events).__name__}, expected list")
        for idx, ev in enumerate(events):
            errors = validate_event(ev, venue_key=f"{venue_key}[{idx}]")
            if errors:
                raise ValueError("\n".join(errors))
        results.append(RefreshResult(venue_key=venue_key, events=events, source=source_label))
    return results


def assemble_payload(
    results: Iterable[RefreshResult],
    *,
    expected_venue_keys: Sequence[str],
    season: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Assemble a writable JSON payload from refresh results."""
    now = now or datetime.now(timezone.utc)
    payload: dict[str, Any] = {key: [] for key in expected_venue_keys}
    for result in results:
        if result.venue_key in payload:
            payload[result.venue_key] = result.events
        else:
            payload[result.venue_key] = result.events
    payload["lastUpdated"] = now.isoformat()
    payload["season"] = season
    return payload


def infer_season(now: datetime | None = None) -> str:
    """Best-effort season label, e.g. ``2025-26``.

    Convention: a season starts in August and runs through the following July.
    Months August–December belong to ``YYYY-(YY+1)``; January–July to
    ``(YYYY-1)-YY``.
    """
    now = now or datetime.now(timezone.utc)
    if now.month >= 8:
        start = now.year
    else:
        start = now.year - 1
    return f"{start}-{(start + 1) % 100:02d}"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _resolve_venues(requested: str | None) -> tuple[Sequence[str], Sequence[str]]:
    """Return ``(classical_keys, ballet_keys)`` to refresh given ``--venue``."""
    if requested in (None, "", "all"):
        return CLASSICAL_VENUE_KEYS, BALLET_VENUE_KEYS
    if requested == "classical":
        return CLASSICAL_VENUE_KEYS, ()
    if requested == "ballet":
        return (), BALLET_VENUE_KEYS
    if requested in CLASSICAL_VENUE_KEYS:
        return (requested,), ()
    if requested in BALLET_VENUE_KEYS:
        return (), (requested,)
    raise SystemExit(
        f"unknown --venue {requested!r}; expected one of "
        f"{('all', 'classical', 'ballet') + ALL_VENUE_KEYS}"
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="refresh_classical_data",
        description="Refresh classical/ballet season data via Perplexity (skeleton stage).",
    )
    parser.add_argument(
        "--venue",
        default="all",
        help="Venue key, group ('classical'|'ballet'), or 'all' (default).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Use stub data instead of Perplexity; do not write to disk.",
    )
    parser.add_argument(
        "--out-classical",
        default=str(CLASSICAL_OUTPUT_PATH),
        help=f"Output path for classical data (default: {CLASSICAL_OUTPUT_PATH}).",
    )
    parser.add_argument(
        "--out-ballet",
        default=str(BALLET_OUTPUT_PATH),
        help=f"Output path for ballet data (default: {BALLET_OUTPUT_PATH}).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    classical_keys, ballet_keys = _resolve_venues(args.venue)

    if not args.dry_run:
        # Real Perplexity wiring lands in task 3.1b. Until then, refusing to
        # write avoids accidentally clobbering on-disk data with empty output.
        print(
            "refresh_classical_data: live mode not implemented yet (task 3.1b). "
            "Re-run with --dry-run to exercise the skeleton.",
            file=sys.stderr,
        )
        return 2

    fetcher = stub_fetch
    source_label = "stub"

    classical_results = refresh_venues(classical_keys, fetcher=fetcher, source_label=source_label)
    ballet_results = refresh_venues(ballet_keys, fetcher=fetcher, source_label=source_label)

    season = infer_season()

    summary: dict[str, Any] = {
        "dry_run": True,
        "source": source_label,
        "season": season,
        "venues": {},
    }

    if classical_results:
        classical_payload = assemble_payload(
            classical_results,
            expected_venue_keys=CLASSICAL_VENUE_KEYS,
            season=season,
        )
        errors = validate_classical_data(
            classical_payload, expected_venue_keys=[r.venue_key for r in classical_results]
        )
        if errors:
            for err in errors:
                print(f"validation error: {err}", file=sys.stderr)
            return 1
        summary["venues"]["classical"] = {
            r.venue_key: len(r.events) for r in classical_results
        }
        summary["classical_payload"] = classical_payload

    if ballet_results:
        ballet_payload = assemble_payload(
            ballet_results,
            expected_venue_keys=BALLET_VENUE_KEYS,
            season=season,
        )
        errors = validate_classical_data(
            ballet_payload, expected_venue_keys=[r.venue_key for r in ballet_results]
        )
        if errors:
            for err in errors:
                print(f"validation error: {err}", file=sys.stderr)
            return 1
        summary["venues"]["ballet"] = {
            r.venue_key: len(r.events) for r in ballet_results
        }
        summary["ballet_payload"] = ballet_payload

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
