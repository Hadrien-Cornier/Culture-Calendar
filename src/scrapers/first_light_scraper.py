"""
First Light Austin book club scraper using simple LLM extraction
"""

from typing import Dict, List
from src.base_scraper import BaseScraper


class FirstLightAustinScraper(BaseScraper):
    """Simple scraper for First Light Austin book club events - real data only"""

    def __init__(self):
        super().__init__(
            base_url="https://www.firstlightaustin.com", venue_name="FirstLight"
        )

    def get_target_urls(self) -> List[str]:
        """Return list of URLs to scrape"""
        return [f"{self.base_url}/book-club"]

    def get_data_schema(self) -> Dict:
        """Return the expected data schema for book club events"""
        return {
            "title": {
                "type": "string",
                "required": True,
                "description": "Book club name",
            },
            "book": {
                "type": "string",
                "required": True,
                "description": "Book title being discussed",
            },
            "author": {
                "type": "string",
                "required": True,
                "description": "Book author name",
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
            "host": {
                "type": "string",
                "required": False,
                "description": "Host or facilitator name",
            },
            "description": {
                "type": "string",
                "required": False,
                "description": "Event description",
            },
        }

    def get_fallback_data(self) -> List[Dict]:
        """Return empty list - we only want real data"""
        return []
