"""Base class for venue scrapers backed by a static JSON file.

Five classical-music venues plus Ballet Austin ship their season as a
hand-curated JSON payload (``docs/classical_data.json`` /
``docs/ballet_data.json``) rather than scraping a live site. The
per-venue scrapers were near-duplicates that all hardcoded an event
``type`` at scrape time — the bug from CLAUDE.md task-2.1 was Ballet
Austin emitting ``type=concert`` instead of ``dance``. This class
collapses that duplication and resolves the event ``type`` from data
and config rather than baking it into Python.

Type resolution order (first match wins):

1. ``event["type"]`` from the source JSON (matches what the JSON
   files already carry for Symphony / Opera / Ballet today).
2. ``ConfigLoader.get_assumed_event_category(venue_key)`` if a config
   is wired in — keeps the venue's declared category in
   ``master_config.yaml`` authoritative.
3. ``default_event_type`` constructor argument as a final fallback.

Two layouts are supported via ``expand_dates``:

- ``True`` (default) — fan a multi-date production into one event per
  date, with a scalar ``date`` and ``time``. Used by Ballet, Opera,
  Early Music, La Follia, Chamber Music.
- ``False`` — preserve the parallel ``dates`` / ``times`` arrays on
  the standardized event. Used by Austin Symphony, whose downstream
  consumer iterates the arrays itself.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from src.base_scraper import BaseScraper


class StaticJsonScraper(BaseScraper):
    """Read events from a static JSON file; never hardcode event type."""

    def __init__(
        self,
        *,
        base_url: str,
        venue_name: str,
        data_file: str,
        top_level_key: str,
        default_event_type: str,
        venue_key: Optional[str] = None,
        default_time: str = "7:30 PM",
        default_location: str = "",
        expand_dates: bool = True,
        config: Optional[Any] = None,
    ):
        super().__init__(
            base_url=base_url,
            venue_name=venue_name,
            venue_key=venue_key,
            config=config,
        )
        self.data_file = data_file
        self.top_level_key = top_level_key
        self.default_event_type = default_event_type
        self.default_time = default_time
        self.default_location = default_location
        self.expand_dates = expand_dates

    def get_target_urls(self) -> List[str]:
        return []

    def _resolve_event_type(self, event: Dict) -> str:
        per_event = event.get("type")
        if per_event:
            return per_event

        if (
            self.config is not None
            and self.venue_key
            and hasattr(self.config, "get_assumed_event_category")
        ):
            from_config = self.config.get_assumed_event_category(self.venue_key)
            if from_config:
                return from_config

        return self.default_event_type

    def _build_event(
        self,
        event: Dict,
        *,
        date: Optional[str] = None,
        time: Optional[str] = None,
        dates: Optional[List[str]] = None,
        times: Optional[List[str]] = None,
    ) -> Dict:
        out = {
            "title": event.get("title"),
            "program": event.get("program"),
            "featured_artist": event.get("featured_artist"),
            "composers": event.get("composers", []),
            "works": event.get("works", []),
            "series": event.get("series"),
            "venue": self.venue_name,
            "location": event.get("venue_name", self.default_location),
            "type": self._resolve_event_type(event),
            "url": self.base_url,
        }
        if self.expand_dates:
            out["date"] = date
            out["time"] = time
        else:
            out["dates"] = list(dates or [])
            out["times"] = list(times or [])
        return out

    def scrape_events(self, use_cache: bool = True) -> List[Dict]:
        if not os.path.exists(self.data_file):
            print(f"{self.venue_name} data file not found: {self.data_file}")
            return []

        try:
            with open(self.data_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            print(f"Error loading {self.venue_name} events from JSON: {exc}")
            return []

        raw_events = data.get(self.top_level_key, []) or []
        standardized: List[Dict] = []

        for event in raw_events:
            dates = event.get("dates", [])
            times = event.get("times", [])
            if not isinstance(dates, list):
                dates = [dates] if dates else []
            if not isinstance(times, list):
                times = [times] if times else []

            if self.expand_dates:
                for i, date in enumerate(dates):
                    if i < len(times):
                        time = times[i]
                    elif times:
                        time = times[0]
                    else:
                        time = self.default_time
                    standardized.append(self._build_event(event, date=date, time=time))
            else:
                if not times and dates:
                    times = [self.default_time] * len(dates)
                standardized.append(
                    self._build_event(event, dates=dates, times=times)
                )

        print(f"Loaded {len(standardized)} {self.venue_name} events from JSON")
        return standardized
