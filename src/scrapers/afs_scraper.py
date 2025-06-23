"""
Austin Film Society scraper using simple LLM extraction
"""

from typing import Dict, List
from src.base_scraper import BaseScraper
from src.schemas import get_venue_schema


class AFSScraper(BaseScraper):
    """Simple scraper for Austin Film Society events - real data only"""
    
    def __init__(self):
        super().__init__(
            base_url="https://www.austinfilm.org",
            venue_name="AFS"
        )
    
    def get_target_urls(self) -> List[str]:
        """Return list of URLs to scrape"""
        return [f"{self.base_url}/calendar/"]
    
    def get_data_schema(self) -> Dict:
        """Return the expected data schema for film events"""
        return {
            'title': {'type': 'string', 'required': True, 'description': 'Film or event title'},
            'director': {'type': 'string', 'required': False, 'description': 'Film director name'},
            'year': {'type': 'integer', 'required': False, 'description': 'Film release year'},
            'country': {'type': 'string', 'required': False, 'description': 'Country of origin'},
            'language': {'type': 'string', 'required': False, 'description': 'Film language'},
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