#!/usr/bin/env python3
"""LLM-driven monthly refresh for ``docs/classical_data.json`` and ``docs/ballet_data.json``.

Phase 3.1a delivered the schema validator + stub pipeline. Phase 3.1b
(this commit) wires :meth:`src.llm_service.LLMService.call_perplexity`
into :func:`fetch_venue_data_via_perplexity` and exposes it through
``--use-perplexity``. Phase 3.2 will add the GitHub Actions cron that
flips the live-mode disk write on and opens a PR with the diff.

The script supplies:

* ``validate_classical_data`` — schema check used by the validator unit tests
  AND by phases 3.1b/3.2 before they overwrite the on-disk JSON.
* ``--dry-run`` — runs the full pipeline without touching disk. Defaults to
  the in-memory stub fetcher; pass ``--use-perplexity`` to exercise the real
  crawler against the live Perplexity API.
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
# Perplexity-backed fetcher
# ---------------------------------------------------------------------------


class LLMFetchError(RuntimeError):
    """Raised when the LLM crawler returns nothing usable for a venue."""


def _load_master_config(path: Path | None = None) -> Mapping[str, Any]:
    """Load ``master_config.yaml`` lazily so unit tests don't pay the import cost."""
    import yaml  # local import — script entry only path that needs PyYAML

    target = path or (_REPO_ROOT / "config" / "master_config.yaml")
    with target.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _venue_refresh_meta(
    config: Mapping[str, Any], venue_key: str
) -> Mapping[str, Any]:
    refresh = config.get("classical_refresh") or {}
    venues = refresh.get("venues") or {}
    cfg = venues.get(venue_key)
    return cfg if isinstance(cfg, dict) else {}


def _venue_display(
    config: Mapping[str, Any],
    venue_key: str,
    refresh_meta: Mapping[str, Any],
) -> tuple[str, str, str]:
    """Return ``(display_name, address, expected_event_type)`` for ``venue_key``."""
    config_key = refresh_meta.get("config_key") or ""
    event_type = refresh_meta.get("event_type") or (
        "dance" if venue_key in BALLET_VENUE_KEYS else "concert"
    )
    venue_meta = (config.get("venues") or {}).get(config_key) or {}
    display = venue_meta.get("display_name") or refresh_meta.get("display_name") or venue_key
    address = venue_meta.get("address") or "Austin, TX"
    return str(display), str(address), str(event_type)


def _build_perplexity_prompt(
    *,
    display_name: str,
    address: str,
    event_type: str,
    season: str,
    season_url: str | None,
) -> str:
    source_hint = (
        f"Use the venue's official season page ({season_url}) and printed program "
        "announcements as primary sources. "
        if season_url
        else "Use the venue's official website and printed program announcements as primary sources. "
    )
    return (
        f"List every public {event_type} event scheduled by {display_name} ({address}) "
        f"during the {season} season. {source_hint}"
        "Respond with a SINGLE JSON object — no prose, no markdown, no code fences — "
        "matching this exact shape: "
        '{"events": [{"title": str, "program": str, "dates": [str], "times": [str], '
        '"venue_name": str, "series": str, "featured_artist": str, '
        '"composers": [str], "works": [str], "type": str}]}. '
        "Rules: (1) every entry in `dates` MUST be YYYY-MM-DD; "
        "(2) `times` MUST have the same length as `dates` (pairwise zip); "
        f"(3) `type` MUST equal {event_type!r}; "
        "(4) include only events with confirmed dates; "
        "(5) leave string fields as empty strings and list fields as empty lists "
        "when information is genuinely unavailable — never invent dates or composers."
    )


def _normalize_event(
    event: Any, *, expected_type: str, expected_venue_name: str | None
) -> dict[str, Any] | None:
    """Coerce one Perplexity event into the on-disk schema, or return None."""
    if not isinstance(event, dict):
        return None
    title = str(event.get("title") or "").strip()
    if not title:
        return None
    venue_name = str(event.get("venue_name") or event.get("venue") or "").strip()
    if not venue_name and expected_venue_name:
        venue_name = expected_venue_name
    if not venue_name:
        return None
    raw_dates = event.get("dates")
    if isinstance(raw_dates, str):
        raw_dates = [raw_dates]
    raw_times = event.get("times")
    if isinstance(raw_times, str):
        raw_times = [raw_times]
    if not isinstance(raw_dates, list) or not isinstance(raw_times, list):
        return None
    dates = [str(d).strip() for d in raw_dates if str(d).strip()]
    times = [str(t).strip() for t in raw_times if str(t).strip()]
    if not dates or not times or len(dates) != len(times):
        return None
    composers = event.get("composers") or []
    works = event.get("works") or []
    if not isinstance(composers, list) or not isinstance(works, list):
        return None
    event_type = str(event.get("type") or expected_type).strip() or expected_type
    return {
        "title": title,
        "program": str(event.get("program") or "").strip(),
        "dates": dates,
        "times": times,
        "venue_name": venue_name,
        "series": str(event.get("series") or "").strip(),
        "featured_artist": str(event.get("featured_artist") or "").strip(),
        "composers": [str(c).strip() for c in composers if str(c).strip()],
        "works": [str(w).strip() for w in works if str(w).strip()],
        "type": event_type,
    }


def _coerce_perplexity_events(
    payload: Any, *, expected_type: str, expected_venue_name: str | None
) -> list[dict[str, Any]]:
    """Normalize the LLM response (dict-with-`events`, list, etc.) to event dicts."""
    if isinstance(payload, dict):
        for key in ("events", "results", "data", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                payload = value
                break
        else:
            payload = []
    if not isinstance(payload, list):
        return []
    out: list[dict[str, Any]] = []
    for event in payload:
        normalized = _normalize_event(
            event,
            expected_type=expected_type,
            expected_venue_name=expected_venue_name,
        )
        if normalized is not None:
            out.append(normalized)
    return out


def fetch_venue_data_via_perplexity(
    venue_key: str,
    *,
    llm_service: Any,
    config: Mapping[str, Any] | None = None,
    season: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch a venue's current-season events via :class:`LLMService`.

    Always validates the Perplexity output against the same schema the on-disk
    files use; raises :class:`LLMFetchError` if nothing usable comes back.
    """
    config = config or _load_master_config()
    refresh_meta = _venue_refresh_meta(config, venue_key)
    if not refresh_meta:
        raise LLMFetchError(
            f"no classical_refresh entry for venue {venue_key!r} — "
            "add it under classical_refresh.venues in master_config.yaml"
        )
    display, address, event_type = _venue_display(config, venue_key, refresh_meta)
    season = season or infer_season()
    season_url = refresh_meta.get("season_url")
    prompt = _build_perplexity_prompt(
        display_name=display,
        address=address,
        event_type=event_type,
        season=season,
        season_url=season_url if isinstance(season_url, str) else None,
    )
    recency = (config.get("classical_refresh") or {}).get("recency_filter") or "month"
    response = llm_service.call_perplexity(
        prompt,
        temperature=0.1,
        search_recency_filter=recency,
    )
    if response is None:
        raise LLMFetchError(
            f"Perplexity returned no response for {venue_key!r} — "
            "check PERPLEXITY_API_KEY and network reachability"
        )
    events = _coerce_perplexity_events(
        response, expected_type=event_type, expected_venue_name=display
    )
    if not events:
        raise LLMFetchError(
            f"Perplexity response for {venue_key!r} did not contain any "
            f"well-formed events; raw response: {response!r}"
        )
    return events


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


def _build_perplexity_fetcher() -> tuple[Callable[[str], list[dict[str, Any]]], str]:
    """Construct the Perplexity-backed fetcher used by ``--use-perplexity``.

    Imports :class:`LLMService` lazily so plain ``--dry-run`` (stub) doesn't
    pay the cost of pulling in the LLM client stack.
    """
    try:
        from src.llm_service import LLMService  # type: ignore
    except ImportError as exc:  # pragma: no cover — guarded on the script path
        raise LLMFetchError(
            f"could not import src.llm_service.LLMService ({exc})"
        ) from exc

    config = _load_master_config()
    llm = LLMService()
    if llm.provider is None and not llm.perplexity_api_key:
        raise LLMFetchError(
            "no LLM provider configured — set PERPLEXITY_API_KEY or "
            "ANTHROPIC_API_KEY in the environment / .env"
        )

    def fetcher(venue_key: str) -> list[dict[str, Any]]:
        return fetch_venue_data_via_perplexity(
            venue_key, llm_service=llm, config=config
        )

    return fetcher, "perplexity"


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
        help="Run the pipeline without writing to disk.",
    )
    parser.add_argument(
        "--use-perplexity",
        action="store_true",
        help=(
            "Fetch events from Perplexity (via src.llm_service.LLMService) "
            "instead of the in-memory stub. Requires PERPLEXITY_API_KEY (or "
            "the Anthropic fallback). Combine with --dry-run for a smoke run "
            "that does not touch on-disk data."
        ),
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
        # The Perplexity crawler exists (see fetch_venue_data_via_perplexity),
        # but disk-write orchestration + PR-on-diff lands in task 3.2's
        # workflow. Refuse here so an accidental local invocation can't clobber
        # on-disk data with a partially-fetched payload.
        print(
            "refresh_classical_data: live mode not implemented yet — "
            "disk write + PR opening land in task 3.2. "
            "Re-run with --dry-run (stub) or --dry-run --use-perplexity "
            "(real crawler, no disk write) to exercise the pipeline.",
            file=sys.stderr,
        )
        return 2

    if args.use_perplexity:
        try:
            fetcher, source_label = _build_perplexity_fetcher()
        except LLMFetchError as exc:
            print(f"refresh_classical_data: {exc}", file=sys.stderr)
            return 1
    else:
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
