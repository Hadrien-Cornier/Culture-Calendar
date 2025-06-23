"""
Alienated Majesty Books scraper using simple LLM extraction
"""

from typing import Dict, List
from src.base_scraper import BaseScraper


class AlienatedMajestyBooksScraper(BaseScraper):
    """Simple scraper for Alienated Majesty Books events - real data only"""
    
    def __init__(self):
        super().__init__(
            base_url="https://www.alienatedmajestybooks.com",
            venue_name="AlienatedMajesty"
        )
    
    def get_target_urls(self) -> List[str]:
        """Return list of URLs to scrape"""
        return [f"{self.base_url}/book-clubs"]
    
    def get_data_schema(self) -> Dict:
        """Return the expected data schema for book club events"""
        return {
            'title': {'type': 'string', 'required': True, 'description': 'Book club name or event title'},
            'book': {'type': 'string', 'required': True, 'description': 'Book title being discussed'},
            'author': {'type': 'string', 'required': True, 'description': 'Book author name'},
            'date': {'type': 'string', 'required': True, 'description': 'Event date in YYYY-MM-DD format'},
            'time': {'type': 'string', 'required': True, 'description': 'Event time (e.g., "7:00 PM")'},
            'venue': {'type': 'string', 'required': False, 'description': 'Venue name'},
            'host': {'type': 'string', 'required': False, 'description': 'Host or facilitator name'},
            'description': {'type': 'string', 'required': False, 'description': 'Event description'},
            'series': {'type': 'string', 'required': False, 'description': 'Book club series name'},
        }
    
    def get_fallback_data(self) -> List[Dict]:
        """Return empty list - we only want real data"""
        return []