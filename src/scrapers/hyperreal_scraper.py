"""
Hyperreal Film Club scraper using simple LLM extraction
"""

from typing import Dict, List
from src.base_scraper import BaseScraper


class HyperrealScraper(BaseScraper):
    """Simple scraper for Hyperreal Film Club events - real data only"""
    
    def __init__(self):
        super().__init__(
            base_url="https://hyperrealfilm.club",
            venue_name="Hyperreal"
        )
    
    def get_target_urls(self) -> List[str]:
        """Return list of URLs to scrape"""
        # For now, just get current month - LLM can adapt to any month format
        return [f"{self.base_url}/events?view=calendar"]
    
    def get_data_schema(self) -> Dict:
        """Return the expected data schema for film events"""
        return {
            'title': {'type': 'string', 'required': True, 'description': 'Film or event title'},
            'director': {'type': 'string', 'required': False, 'description': 'Film director name'},
            'year': {'type': 'integer', 'required': False, 'description': 'Film release year'},
            'country': {'type': 'string', 'required': False, 'description': 'Country of origin'},
            'duration': {'type': 'string', 'required': False, 'description': 'Film duration (e.g., "120 min")'},
            'date': {'type': 'string', 'required': True, 'description': 'Event date in YYYY-MM-DD format'},
            'time': {'type': 'string', 'required': True, 'description': 'Event time (e.g., "7:30 PM")'},
            'venue': {'type': 'string', 'required': False, 'description': 'Venue name'},
            'description': {'type': 'string', 'required': False, 'description': 'Event description'},
            'is_special_screening': {'type': 'boolean', 'required': False, 'description': 'Whether this is a special screening'},
        }
    
    def get_fallback_data(self) -> List[Dict]:
        """Return empty list - we only want real data"""
        return []