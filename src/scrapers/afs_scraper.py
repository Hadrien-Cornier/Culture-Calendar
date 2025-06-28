"""
Austin Film Society scraper using the BaseScraper pattern
"""

from datetime import datetime
from typing import Dict, List

from ..base_scraper import BaseScraper
from ..schemas import FilmEventSchema


class AFSScraper(BaseScraper):
    """Austin Film Society scraper following BaseScraper pattern."""

    def __init__(self):
        super().__init__(
            base_url="https://www.austinfilm.org", 
            venue_name="Austin Film Society"
        )

    def get_target_urls(self) -> List[str]:
        """Return the list of target URLs to scrape."""
        return ["https://www.austinfilm.org/calendar"]

    def get_data_schema(self) -> Dict:
        """Return the expected data schema for AFS events."""
        return FilmEventSchema.get_schema()

    def get_fallback_data(self) -> List[Dict]:
        """Return fallback data when all scraping methods fail."""
        return [
            {
                "title": "Regular Film Screening",
                "date": datetime.now().strftime("%Y-%m-%d"),
                "time": "7:00 PM", 
                "venue": "AFS Cinema",
                "type": "screening",
                "description": "Austin Film Society presents carefully curated independent and international films.",
                "url": "https://www.austinfilm.org"
            }
        ]