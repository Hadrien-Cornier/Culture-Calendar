"""
Austin Symphony Orchestra scraper using JSON data loading
"""

import json
import os
from typing import Dict, List

from src.base_scraper import BaseScraper


class AustinSymphonyScraper(BaseScraper):
    """Simple scraper for Austin Symphony events - loads from JSON data"""

    def __init__(self, config=None, venue_key="austin_symphony"):
        super().__init__(
            base_url="https://austinsymphony.org",
            venue_name="Symphony",
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

            symphony_events = data.get("austinSymphony", [])
            standardized_events = []

            for event in symphony_events:
                # Keep dates and times as arrays for consistency
                dates = event.get("dates", [])
                times = event.get("times", [])

                # Ensure dates and times are always arrays
                if not isinstance(dates, list):
                    dates = [dates] if dates else []
                if not isinstance(times, list):
                    times = [times] if times else []

                # If no times provided, default to 8:00 PM for all dates
                if not times and dates:
                    times = ["8:00 PM"] * len(dates)

                standardized_event = {
                    "title": event.get("title"),
                    "program": event.get("program"),
                    "featured_artist": event.get("featured_artist"),
                    "composers": event.get("composers", []),
                    "works": event.get("works", []),
                    "series": event.get("series"),
                    "dates": dates,  # Keep as array
                    "times": times,  # Keep as array
                    "venue": self.venue_name,
                    "location": event.get("venue_name", "Dell Hall at Long Center"),
                    "type": "concert",
                    "url": self.base_url,
                }
                standardized_events.append(standardized_event)

            print(f"Loaded {len(standardized_events)} Symphony events from JSON")
            return standardized_events

        except Exception as e:
            print(f"Error loading Symphony events from JSON: {e}")
            return []
