#!/usr/bin/env python3
"""Perplexity-driven Austin venue prospector.

Reads already-tracked venues from ``config/master_config.yaml``, asks
Perplexity (via :meth:`src.llm_service.LLMService.call_perplexity`) for 5–10
Austin venue candidates in the requested category with browsable online event
calendars, deduplicates the suggestions against the tracked list, and
appends the survivors as a checklist section to a markdown file for human
review.

This script is write-only against ``.overnight/venue-prospects/`` (or any
``--out`` path the operator picks). It NEVER mutates
``config/master_config.yaml`` or anything under ``src/scrapers/`` — onboarding
a prospect is always a separate, human-approved change.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import yaml

# Make ``src.*`` importable when invoked as ``python scripts/prospect_venues.py``.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.llm_service import LLMService  # noqa: E402

ALLOWED_CATEGORIES: tuple[str, ...] = (
    "movie",
    "concert",
    "book_club",
    "opera",
    "dance",
    "visual_arts",
    "other",
)

DEFAULT_CONFIG_PATH = Path("config/master_config.yaml")
DEFAULT_OUT_DIR = Path(".overnight/venue-prospects")

_FENCED_BLOCK_RE = re.compile(r"```(?:json)?\s*(?P<body>.+?)```", re.DOTALL)


def load_existing_venues(config_path: Path) -> list[str]:
    """Return display names of every venue already tracked in master_config."""
    with config_path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}
    venues = config.get("venues") or {}
    names: list[str] = []
    for key, meta in venues.items():
        if not isinstance(meta, dict):
            continue
        display = meta.get("display_name") or key
        names.append(str(display))
    return names


def build_prompt(category: str, existing_venues: Sequence[str]) -> str:
    """Compose the Perplexity prompt for a given category."""
    existing_str = ", ".join(existing_venues) if existing_venues else "(none)"
    return (
        f"List Austin, TX venues that host public {category} events with "
        "browsable online event calendars. Exclude these already-tracked "
        f"venues: {existing_str}. "
        "Return 5-10 candidates as JSON matching this exact shape: "
        '{"candidates": [{"name": str, "url": str, '
        '"sample_event": str, "why_relevant": str}]}. '
        "Every URL must be a real, current event calendar or events listing "
        "page. Respond with ONLY the JSON object — no prose, no code fences."
    )


def _coerce_candidates(payload: Any) -> list[dict[str, str]]:
    """Normalize a variety of LLM response shapes to a list of candidate dicts."""
    if payload is None:
        return []
    if isinstance(payload, str):
        payload = _parse_json_loose(payload)
    if isinstance(payload, dict):
        for key in ("candidates", "venues", "results", "data"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
        else:
            return []
    if not isinstance(payload, list):
        return []
    out: list[dict[str, str]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "name": str(item.get("name") or "").strip(),
                "url": str(item.get("url") or "").strip(),
                "sample_event": str(item.get("sample_event") or "").strip(),
                "why_relevant": str(item.get("why_relevant") or "").strip(),
            }
        )
    return out


def _parse_json_loose(text: str) -> Any:
    """Extract JSON from raw LLM text, tolerating fenced code blocks."""
    text = text.strip()
    if not text:
        return None
    match = _FENCED_BLOCK_RE.search(text)
    if match:
        text = match.group("body").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Last-resort: slice between first { and last } (object) or [ ... ] (array).
    for opener, closer in (("[", "]"), ("{", "}")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue
    return None


def _normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", name).strip().casefold()


def dedupe_candidates(
    candidates: Iterable[dict[str, str]],
    existing_venues: Sequence[str],
) -> list[dict[str, str]]:
    """Drop candidates whose normalized name matches an existing venue."""
    existing_norm = {_normalize_name(v) for v in existing_venues if v}
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for cand in candidates:
        name = cand.get("name", "")
        norm = _normalize_name(name)
        if not norm:
            continue
        if norm in existing_norm or norm in seen:
            continue
        seen.add(norm)
        out.append(cand)
    return out


def format_section(
    candidates: Sequence[dict[str, str]],
    category: str,
    now: datetime,
) -> str:
    """Render a markdown section for one prospecting run."""
    header = f"## Prospecting run: {now.isoformat()} — category {category}\n"
    if not candidates:
        return header + "- _(no new candidates returned)_\n"
    lines = [header]
    for cand in candidates:
        name = cand.get("name") or "(unnamed)"
        url = cand.get("url") or "(no url)"
        why = cand.get("why_relevant") or "(no rationale)"
        lines.append(f"- [ ] {name} ({category}) — {why} — {url}")
    return "\n".join(lines) + "\n"


def append_section(out_path: Path, section: str) -> None:
    """Append (never overwrite) the markdown section to ``out_path``."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    needs_leading_break = out_path.exists() and out_path.stat().st_size > 0
    with out_path.open("a", encoding="utf-8") as handle:
        if needs_leading_break:
            handle.write("\n")
        handle.write(section)


def default_out_path(category: str, now: datetime) -> Path:
    return DEFAULT_OUT_DIR / f"{category}-{now.strftime('%Y-%m-%d')}.md"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Query Perplexity for Austin venue candidates in a given event "
            "category and append a human-review checklist to a markdown file."
        )
    )
    parser.add_argument(
        "--category",
        required=True,
        choices=ALLOWED_CATEGORIES,
        help="Event category to prospect for.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help=(
            "Output markdown path. Defaults to "
            ".overnight/venue-prospects/<category>-<YYYY-MM-DD>.md."
        ),
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Path to master_config.yaml (default: config/master_config.yaml).",
    )
    return parser.parse_args(argv)


def run(
    category: str,
    out_path: Path,
    config_path: Path,
    llm: LLMService | None = None,
    now: datetime | None = None,
) -> list[dict[str, str]]:
    """Core prospecting pipeline. Returns the deduped candidates written."""
    now = now or datetime.now(timezone.utc)
    llm = llm or LLMService()
    existing = load_existing_venues(config_path)
    prompt = build_prompt(category, existing)
    response = llm.call_perplexity(prompt, temperature=0.3)
    candidates = _coerce_candidates(response)
    survivors = dedupe_candidates(candidates, existing)
    section = format_section(survivors, category, now)
    append_section(out_path, section)
    return survivors


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    out_path = args.out or default_out_path(args.category, datetime.now(timezone.utc))
    survivors = run(
        category=args.category,
        out_path=out_path,
        config_path=args.config,
    )
    print(f"Wrote {len(survivors)} candidate(s) to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
