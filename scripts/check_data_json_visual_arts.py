#!/usr/bin/env python3
"""Smoke-test: docs/data.json contains at least one well-formed visual_arts event.

Acceptance (task-T1.7):
- docs/data.json contains >=1 event with type=visual_arts
- that event has rating != null
- that event has a non-empty description
- that event has a non-empty one_liner_summary

Exit 0 on pass, 1 on fail. Prints a one-line summary either way.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parent.parent / "docs" / "data.json"


def _is_non_empty(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    return True


def main() -> int:
    if not DATA_PATH.exists():
        print(f"FAIL: {DATA_PATH} does not exist")
        return 1

    try:
        events = json.loads(DATA_PATH.read_text())
    except json.JSONDecodeError as exc:
        print(f"FAIL: {DATA_PATH} is not valid JSON: {exc}")
        return 1

    if not isinstance(events, list):
        print("FAIL: docs/data.json is not a list of events")
        return 1

    visual_arts = [
        e
        for e in events
        if isinstance(e, dict) and (e.get("type") == "visual_arts" or e.get("event_category") == "visual_arts")
    ]
    if not visual_arts:
        print("FAIL: no events with type=visual_arts in docs/data.json")
        return 1

    well_formed = [
        e
        for e in visual_arts
        if e.get("rating") is not None
        and _is_non_empty(e.get("description"))
        and _is_non_empty(e.get("one_liner_summary"))
    ]

    if not well_formed:
        missing = []
        for e in visual_arts:
            problems = []
            if e.get("rating") is None:
                problems.append("rating is null")
            if not _is_non_empty(e.get("description")):
                problems.append("description is empty")
            if not _is_non_empty(e.get("one_liner_summary")):
                problems.append("one_liner_summary is empty")
            missing.append(f"  - {e.get('title', '?')}: {', '.join(problems)}")
        print(
            "FAIL: no well-formed visual_arts event (need rating!=null, non-empty description, non-empty one_liner_summary)"
        )
        print("\n".join(missing))
        return 1

    sample = well_formed[0]
    print(
        "PASS: "
        f"{len(well_formed)} well-formed visual_arts event(s); "
        f"first = {sample.get('title', '?')!r} (rating={sample.get('rating')})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
