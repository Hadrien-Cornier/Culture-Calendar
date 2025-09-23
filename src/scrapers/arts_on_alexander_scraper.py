"""
Arts on Alexander scraper using JSON data loading
"""

import json
import os
from typing import Dict, List

from src.base_scraper import BaseScraper


class ArtsOnAlexanderScraper(BaseScraper):
    """Simple scraper for Arts on Alexander events - loads from JSON data"""

    def __init__(self, config=None, venue_key="arts_on_alexander"):
        super().__init__(
            base_url="https://www.artsonalexander.org",
            venue_name="Arts on Alexander",
            venue_key=venue_key,
            config=config,
        )
        self.data_file = self.get_project_path("docs", "classical_data.json")

    def get_target_urls(self) -> List[str]:
        """Return empty list - we load from JSON file"""
        return []

    def scrape_events(self, use_cache: bool = True) -> List[Dict]:
        """Load events from JSON file instead of web scraping"""
        try:
            if not os.path.exists(self.data_file):
                print(f"Classical data file not found: {self.data_file}")
                return []

            with open(self.data_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            arts_events = data.get("artsOnAlexander", [])
            standardized_events = []

            for event in arts_events:
                # Keep dates and times as arrays for consistency
                dates = event.get("dates", [])
                times = event.get("times", [])

                # Ensure dates and times are always arrays
                if not isinstance(dates, list):
                    dates = [dates] if dates else []
                if not isinstance(times, list):
                    times = [times] if times else []

                # Create standardized event
                standardized_event = {
                    "title": event.get("title", ""),
                    "description": event.get("program", ""),
                    "dates": dates,
                    "times": times,
                    "venue": event.get("venue_name", "Arts on Alexander"),
                    "url": self.base_url,
                    "type": event.get("type", "concert"),
                    # Classical music specific fields
                    "program": event.get("program", ""),
                    "series": event.get("series", ""),
                    "featured_artist": event.get("featured_artist", ""),
                    "composers": event.get("composers", []),
                    "works": event.get("works", []),
                }

                standardized_events.append(standardized_event)

            print(
                f"Loaded {len(standardized_events)} Arts on Alexander events from JSON"
            )
            return standardized_events

        except Exception as e:
            print(f"Error loading Arts on Alexander data: {e}")
            return []
