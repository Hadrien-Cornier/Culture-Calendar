#!/usr/bin/env python3
"""Coverage matrix: every event_category in ontology.labels is represented by
at least one well-formed event in docs/data.json.

Acceptance (task-T4.1):
- For each event_category in ontology.labels, count total and well-formed
  events in docs/data.json.
- An event is well-formed when every template `required_on_publish` field is
  populated (non-empty) and `rating` is numeric and within [0, 10].
- Print a per-category coverage table.
- Exit 0 when every populated category has >=1 well-formed event.
- Empty categories (0 events) are reported as WARN but do not fail the run,
  since some categories (e.g. dance) have no scraper yet and the script is a
  regression guard for categories that already ship events.
- Exit 1 when a populated category has zero well-formed events.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config_loader import ConfigLoader  # noqa: E402

DATA_PATH = ROOT / "docs" / "data.json"

MIN_RATING = 0
MAX_RATING = 10


@dataclass(frozen=True)
class CategoryReport:
    category: str
    total: int
    well_formed: int
    sample_title: str | None

    @property
    def status(self) -> str:
        if self.total == 0:
            return "WARN"
        if self.well_formed == 0:
            return "FAIL"
        return "PASS"


def _is_non_empty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, (list, dict, tuple, set)):
        return len(value) > 0
    return True


def _is_valid_rating(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if not isinstance(value, (int, float)):
        return False
    return MIN_RATING <= value <= MAX_RATING


def _matches_category(event: dict, category: str) -> bool:
    return event.get("type") == category or event.get("event_category") == category


def _is_well_formed(event: dict, required_fields: list[str]) -> bool:
    for field in required_fields:
        if not _is_non_empty(event.get(field)):
            return False
    return _is_valid_rating(event.get("rating"))


def _load_events() -> list[dict]:
    if not DATA_PATH.exists():
        raise SystemExit(f"FAIL: {DATA_PATH} does not exist")
    try:
        payload = json.loads(DATA_PATH.read_text())
    except json.JSONDecodeError as exc:
        raise SystemExit(f"FAIL: {DATA_PATH} is not valid JSON: {exc}")
    if not isinstance(payload, list):
        raise SystemExit("FAIL: docs/data.json is not a list of events")
    return [e for e in payload if isinstance(e, dict)]


def _build_report(
    category: str,
    required_fields: list[str],
    events: list[dict],
) -> CategoryReport:
    matching = [e for e in events if _matches_category(e, category)]
    well_formed = [e for e in matching if _is_well_formed(e, required_fields)]
    sample = well_formed[0].get("title") if well_formed else None
    return CategoryReport(
        category=category,
        total=len(matching),
        well_formed=len(well_formed),
        sample_title=sample,
    )


def _format_table(reports: list[CategoryReport]) -> str:
    header = f"{'category':<14} {'total':>6} {'well-formed':>12}  {'status':<6}  sample"
    divider = "-" * len(header)
    lines = [header, divider]
    for r in reports:
        sample = r.sample_title or "—"
        lines.append(
            f"{r.category:<14} {r.total:>6} {r.well_formed:>12}  {r.status:<6}  {sample}"
        )
    return "\n".join(lines)


def main() -> int:
    config = ConfigLoader().get_config()
    labels = config["ontology"]["labels"]
    templates = config["templates"]
    events = _load_events()

    reports = [
        _build_report(
            category=label,
            required_fields=templates[label].get("required_on_publish", []),
            events=events,
        )
        for label in labels
    ]

    print(_format_table(reports))

    failing = [r for r in reports if r.status == "FAIL"]
    empty = [r for r in reports if r.status == "WARN"]

    if empty:
        print()
        print(
            "WARN: empty categories (no events in docs/data.json): "
            + ", ".join(r.category for r in empty)
        )
    if failing:
        print()
        print(
            "FAIL: categories with events but zero well-formed: "
            + ", ".join(r.category for r in failing)
        )
        return 1

    print()
    print(
        f"PASS: {len(reports) - len(empty)}/{len(reports)} categories covered; "
        f"{len(empty)} empty (warn-only)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
