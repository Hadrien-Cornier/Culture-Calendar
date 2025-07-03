"""
Hyperreal Movie Club scraper using LLM-powered architecture
"""

from datetime import datetime
from typing import Dict, List
from bs4 import BeautifulSoup

from ..base_scraper import BaseScraper
from ..schemas import MovieEventSchema


class HyperrealScraper(BaseScraper):
    """Scraper for Hyperreal Movie Club events using LLM extraction."""

    def __init__(self):
        super().__init__(
            base_url="https://hyperrealfilm.club", 
            venue_name="Hyperreal Movie Club"
        )

    def get_target_urls(self) -> List[str]:
        """Return list of URLs to scrape"""
        # Get current year and month for calendar URL
        now = datetime.now()
        current_month_url = f"{self.base_url}/events?view=calendar&month={now.month:02d}-{now.year}"
        
        # Also check main events page
        return [
            current_month_url,
            f"{self.base_url}/events",
            f"{self.base_url}/"
        ]

    def get_data_schema(self) -> Dict:
        """Return the expected data schema for Hyperreal movie events"""
        return MovieEventSchema.get_schema()

    def get_fallback_data(self) -> List[Dict]:
        """Provide fallback event data when scraping fails"""
        # Return empty list - Hyperreal updates frequently, 
        # so we shouldn't use static fallback data
        return []
    
    def scrape_events(self, days_ahead: int = None) -> List[Dict]:
        """Scrape Hyperreal events using LLM extraction"""
        print(f"Scraping {self.venue_name}...")
        all_events = []
        
        for url in self.get_target_urls():
            try:
                # Fetch the page
                response = self.session.get(url, timeout=15)
                if response.status_code != 200:
                    print(f"  Failed to fetch {url}: Status {response.status_code}")
                    continue
                
                # Try to extract event links from the calendar page
                soup = BeautifulSoup(response.text, 'html.parser')
                event_links = []
                
                # Find event links - looking for links that contain "/events/2025/" or current year
                current_year = datetime.now().year
                for link in soup.find_all('a', href=True):
                    href = link.get('href', '')
                    if f'/events/{current_year}/' in href:
                        full_url = href if href.startswith('http') else f"{self.base_url}{href}"
                        if full_url not in event_links:
                            event_links.append(full_url)
                
                print(f"  Found {len(event_links)} event links on {url}")
                
                # If we found individual event pages, scrape them
                if event_links:
                    for event_url in event_links:
                        try:
                            event_response = self.session.get(event_url, timeout=10)
                            if event_response.status_code == 200:
                                # Use LLM to extract event data
                                extraction_result = self.llm_service.extract_data(
                                    content=event_response.text,
                                    schema=self.get_data_schema(),
                                    url=event_url,
                                    content_type='html'
                                )
                                
                                if extraction_result.get('success'):
                                    event_data = extraction_result.get('data', {})
                                    # Ensure required fields
                                    if event_data.get('title') and event_data.get('date'):
                                        event_data['venue'] = self.venue_name
                                        event_data['type'] = 'movie'
                                        event_data['url'] = event_url
                                        all_events.append(event_data)
                                        print(f"    ✓ Extracted: {event_data.get('title')}")
                        except Exception as e:
                            print(f"    Error extracting event from {event_url}: {e}")
                            continue
                
                # If no individual event links found, try to extract events from the main page
                elif 'calendar' in url or 'events' in url:
                    print(f"  No individual event links found, trying to extract events from page content...")
                    # Use LLM to extract multiple events from the page
                    schema = {
                        "events": {
                            "type": "array",
                            "description": "List of movie screening events at Hyperreal Movie Club",
                            "items": self.get_data_schema()
                        }
                    }
                    
                    extraction_result = self.llm_service.extract_data(
                        content=response.text,
                        schema=schema,
                        url=url,
                        content_type='html'
                    )
                    
                    if extraction_result.get('success'):
                        events = extraction_result.get('data', {}).get('events', [])
                        for event_data in events:
                            if event_data.get('title') and event_data.get('date'):
                                event_data['venue'] = self.venue_name
                                event_data['type'] = 'movie'
                                event_data['url'] = url
                                all_events.append(event_data)
                                print(f"    ✓ Extracted: {event_data.get('title')}")
                        
                        if events:
                            break  # Found events, don't need to try other URLs
                
            except Exception as e:
                print(f"  Error scraping {url}: {e}")
                continue
        
        print(f"Successfully scraped {len(all_events)} Hyperreal events total")
        return all_events
    
    def get_event_details(self, url: str) -> Dict:
        """Get additional details for a specific event - returns empty dict since details are already complete"""
        return {}