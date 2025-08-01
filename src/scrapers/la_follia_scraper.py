"""
La Follia Austin chamber music scraper using JSON data loading
"""

import json
import os
from typing import Dict, List

from src.base_scraper import BaseScraper


class LaFolliaAustinScraper(BaseScraper):
    """Simple scraper for La Follia events - loads from JSON data"""

    def __init__(self):
        super().__init__(
            base_url="https://www.lafolliaaustin.org", venue_name="LaFollia"
        )
        self.data_file = (
            "/Users/HCornier/Documents/Github/Culture-Calendar/docs/classical_data.json"
        )

    def get_target_urls(self) -> List[str]:
        """Return empty list - we load from JSON file"""
        return []

    def get_data_schema(self) -> Dict:
        """Return the expected data schema for chamber music events"""
        return {
            "title": {
                "type": "string",
                "required": True,
                "description": "Concert title",
            },
            "program": {
                "type": "string",
                "required": False,
                "description": "Concert program",
            },
            "featured_artist": {
                "type": "string",
                "required": False,
                "description": "Featured artist or ensemble",
            },
            "composers": {
                "type": "array",
                "required": False,
                "description": "List of composer names",
            },
            "works": {
                "type": "array",
                "required": False,
                "description": "List of musical works",
            },
            "series": {
                "type": "string",
                "required": False,
                "description": "Concert series name",
            },
            "date": {
                "type": "string",
                "required": True,
                "description": "Event date in YYYY-MM-DD format",
            },
            "time": {
                "type": "string",
                "required": True,
                "description": 'Event time (e.g., "7:30 PM")',
            },
            "venue": {"type": "string", "required": False, "description": "Venue name"},
        }

    def get_fallback_data(self) -> List[Dict]:
        """Return empty list - we only want real data"""
        return []

    def scrape_events(self, use_cache: bool = True) -> List[Dict]:
        """Load events from JSON file instead of web scraping"""
        try:
            if not os.path.exists(self.data_file):
                print(f"Classical data file not found: {self.data_file}")
                return []

            with open(self.data_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            la_follia_events = data.get("laFollia", [])
            standardized_events = []

            for event in la_follia_events:
                # Handle multiple dates for the same concert
                dates = event.get("dates", [])
                times = event.get("times", [])

                for i, date in enumerate(dates):
                    time = (
                        times[i] if i < len(times) else times[0] if times else "7:30 PM"
                    )

                    standardized_event = {
                        "title": event.get("title"),
                        "program": event.get("program"),
                        "featured_artist": event.get("featured_artist"),
                        "composers": event.get("composers", []),
                        "works": event.get("works", []),
                        "series": event.get("series"),
                        "date": date,
                        "time": time,
                        "venue": self.venue_name,
                        "location": event.get("venue_name", "Various Austin Venues"),
                        "type": "concert",
                        "url": self.base_url,
                    }
                    standardized_events.append(standardized_event)

            print(f"Loaded {len(standardized_events)} La Follia events from JSON")
            return standardized_events

        except Exception as e:
            print(f"Error loading La Follia events from JSON: {e}")
            return []
