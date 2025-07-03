"""
Ballet Austin scraper using JSON data loading.
Loads slow-changing season events from docs/ballet_data.json so we don't have to scrape the website.
"""

import json
import os
from typing import Dict, List

from src.base_scraper import BaseScraper


class BalletAustinScraper(BaseScraper):
    """Simple scraper for Ballet Austin season events – loads from JSON data"""

    def __init__(self):
        super().__init__(base_url="https://balletaustin.org", venue_name="BalletAustin")
        # Hard-coded JSON file (slow-changing, edited manually)
        self.data_file = (
            "/Users/HCornier/Documents/Github/Culture-Calendar/docs/ballet_data.json"
        )

    # ---------------------------------------------------------------------
    # Nothing to scrape – we just read the static JSON
    # ---------------------------------------------------------------------
    def get_target_urls(self) -> List[str]:  # noqa: D401
        """Return empty list – we load from JSON file"""
        return []

    def get_data_schema(self) -> Dict:  # noqa: D401
        """Return the expected data schema for Ballet Austin events"""
        return {
            "title": {"type": "string", "required": True},
            "program": {"type": "string", "required": False},
            "dates": {"type": "array", "required": True},
            "times": {"type": "array", "required": True},
            "venue_name": {"type": "string", "required": False},
            "series": {"type": "string", "required": False},
            "type": {"type": "string", "required": False},
        }

    def get_fallback_data(self) -> List[Dict]:  # noqa: D401
        """Return empty list – we only want real data"""
        return []

    # ------------------------------------------------------------------
    # Public scrape method (actually just load the JSON)
    # ------------------------------------------------------------------
    def scrape_events(self, use_cache: bool = True) -> List[Dict]:  # noqa: D401
        """Load Ballet Austin events from the static JSON file."""
        try:
            if not os.path.exists(self.data_file):
                print(f"Ballet Austin data file not found: {self.data_file}")
                return []

            with open(self.data_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            ba_events = data.get("balletAustin", [])
            standardized_events: List[Dict] = []

            for event in ba_events:
                dates = event.get("dates", [])
                times = event.get("times", [])

                for i, date in enumerate(dates):
                    time = times[i] if i < len(times) else times[0] if times else "7:30 PM"

                    standardized_event = {
                        "title": event.get("title"),
                        "program": event.get("program"),
                        "series": event.get("series"),
                        "date": date,
                        "time": time,
                        "venue": self.venue_name,
                        "location": event.get("venue_name", "The Long Center"),
                        "type": "concert",  # Treat ballet performances as concerts for pipeline
                        "url": self.base_url,
                    }
                    standardized_events.append(standardized_event)

            print(f"Loaded {len(standardized_events)} Ballet Austin events from JSON")
            return standardized_events

        except Exception as e:
            print(f"Error loading Ballet Austin events from JSON: {e}")
            return [] 