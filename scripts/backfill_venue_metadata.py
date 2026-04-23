#!/usr/bin/env python3
"""Backfill ``venue_display_name`` + ``venue_address`` into ``docs/data.json``.

Why this exists: the venue-metadata plumbing in
``update_website_data._enrich_events_with_venue_metadata`` (added in commit
``b7b36cb``, feat(task-T0.2)) attaches both fields during the full scrape
pipeline. But ``docs/data.json`` was last regenerated on 2026-04-19
(commit ``c45fdfd``), before the plumbing landed. Running the full
pipeline requires live scraper access + API keys; this one-shot reads
existing events, runs the same helper against ``config/master_config.yaml``,
and writes them back.

Idempotent: running twice produces the same output.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config_loader import ConfigLoader  # noqa: E402
from update_website_data import _enrich_events_with_venue_metadata  # noqa: E402

DATA_PATH = ROOT / "docs" / "data.json"


def main() -> int:
    events = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    config = ConfigLoader()
    _enrich_events_with_venue_metadata(events, config)
    with_address = sum(1 for e in events if e.get("venue_address"))
    with_display = sum(1 for e in events if e.get("venue_display_name"))
    total = len(events)
    DATA_PATH.write_text(
        json.dumps(events, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"backfilled {DATA_PATH}: {total} events; "
        f"venue_address set on {with_address}; "
        f"venue_display_name set on {with_display}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
