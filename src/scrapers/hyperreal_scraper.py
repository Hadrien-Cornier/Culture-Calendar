"""
Hyperreal Movie Club scraper using Beautiful Soup extraction with LLM fallback.

This scraper:
1. Fetches the calendar page for the current month
2. Extracts all movie screening event URLs 
3. For each event page, uses Beautiful Soup to extract:
   - Title (from h1 tag, cleaned of venue suffix)
   - Date (from list items, formatted as YYYY-MM-DD)
   - Time (from list items)
   - Description (from "The vitals:" section and movie description)
   - Venue (always "Hyperreal Film Club")
4. Falls back to LLM extraction if Beautiful Soup fails
"""

from datetime import datetime
from typing import Dict, List, Optional
from bs4 import BeautifulSoup
import re

from src.base_scraper import BaseScraper
from src.schemas import MovieEventSchema


class HyperrealScraper(BaseScraper):
    """
    Scraper for Hyperreal Movie Club events.
    
    Fetches the calendar page for a specific month and extracts all event URLs,
    then visits each event page to get detailed information.
    """

    def __init__(self):
        super().__init__(
            base_url="https://hyperrealfilm.club", 
            venue_name="Hyperreal Movie Club"
        )

    def get_target_urls(self) -> List[str]:
        """Return the current month's calendar URL"""
        now = datetime.now()
        return [f"{self.base_url}/events?view=calendar&month={now.month:02d}-{now.year}"]

    def get_data_schema(self) -> Dict:
        """Return the expected data schema for Hyperreal movie events"""
        return MovieEventSchema.get_schema()

    def get_fallback_data(self) -> List[Dict]:
        """Provide fallback event data when scraping fails"""
        # Return empty list - Hyperreal updates frequently, 
        # so we shouldn't use static fallback data
        return []
    
    def extract_event_with_beautifulsoup(self, html: str, event_url: str) -> Optional[Dict]:
        """
        Extract event data from Hyperreal event page using Beautiful Soup.
        
        Args:
            html: The HTML content of the event page
            event_url: The URL of the event page
            
        Returns:
            Dict with extracted event data or None if extraction fails
        """
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Extract title from h1 tag
            title_elem = soup.find('h1')
            if not title_elem:
                return None
            
            # Clean title - remove "at HYPERREAL FILM CLUB" suffix
            title = title_elem.get_text(strip=True)
            title = re.sub(r'\s+at\s+HYPERREAL\s+FILM\s+CLUB\s*$', '', title, flags=re.IGNORECASE)
            
            # Extract date - look for list items with date information
            date_str = None
            time_str = None
            
            # Find the date/time list items (usually in a ul with date and time info)
            for li in soup.find_all('li'):
                text = li.get_text(strip=True)
                
                # Look for date pattern (e.g., "Monday, September 8, 2025")
                date_match = re.search(
                    r'(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+'
                    r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+'
                    r'(\d{1,2}),?\s+(\d{4})',
                    text
                )
                if date_match:
                    month_names = {
                        'January': '01', 'February': '02', 'March': '03', 'April': '04',
                        'May': '05', 'June': '06', 'July': '07', 'August': '08',
                        'September': '09', 'October': '10', 'November': '11', 'December': '12'
                    }
                    month = month_names[date_match.group(2)]
                    day = date_match.group(3).zfill(2)
                    year = date_match.group(4)
                    date_str = f"{year}-{month}-{day}"
                
                # Look for time pattern (e.g., "7:30 PM 11:00 PM")
                time_match = re.search(r'(\d{1,2}:\d{2}\s*[AP]M)', text)
                if time_match and not time_str:
                    time_str = time_match.group(1).strip()
            
            # Extract description
            description = None
            
            # Look for the main content area with "The vitals:" and movie description
            # Usually in paragraph tags or div elements
            content_texts = []
            
            # First, try to find "The vitals:" section
            for elem in soup.find_all(text=re.compile(r'The vitals:', re.IGNORECASE)):
                parent = elem.parent
                if parent:
                    # Get the parent container and extract all text
                    container = parent.parent if parent.name in ['strong', 'b', 'em'] else parent
                    if container:
                        # Get all text from this container and siblings
                        text_parts = []
                        
                        # Start from the container with "The vitals:"
                        current = container
                        while current:
                            if current.name in ['p', 'div'] or (current.string and current.string.strip()):
                                text = current.get_text(separator=' ', strip=True)
                                if text and not text.startswith('Earlier Event:') and not text.startswith('Later Event:'):
                                    text_parts.append(text)
                            
                            # Move to next sibling
                            current = current.find_next_sibling()
                            
                            # Stop if we hit navigation elements or event links
                            if current and ('Earlier Event' in current.get_text() or 
                                          'Later Event' in current.get_text() or
                                          'SEE YOU AT THE MOVIES' in current.get_text()):
                                break
                        
                        if text_parts:
                            description = ' '.join(text_parts)
                            break
            
            # Alternative approach: look for paragraphs with movie description
            if not description:
                # Find paragraphs that look like movie descriptions
                for p in soup.find_all('p'):
                    text = p.get_text(strip=True)
                    # Look for paragraphs that mention the movie or contain descriptive text
                    if len(text) > 100 and (
                        'film' in text.lower() or 
                        'movie' in text.lower() or 
                        'premiere' in text.lower() or
                        title.lower() in text.lower()
                    ):
                        content_texts.append(text)
                
                # Also check for any text containing "The vitals:"
                for elem in soup.find_all(text=re.compile(r'The vitals:')):
                    parent = elem.parent
                    while parent and parent.name not in ['body', 'html']:
                        text = parent.get_text(separator=' ', strip=True)
                        if text and len(text) > 50:
                            content_texts.append(text)
                            break
                        parent = parent.parent
                
                if content_texts:
                    # Combine and clean the description
                    description = ' '.join(content_texts)
            
            # Clean up the description
            if description:
                # Remove duplicate spaces and clean up
                description = re.sub(r'\s+', ' ', description)
                # Remove navigation text
                description = re.sub(r'(Earlier Event:|Later Event:).*', '', description)
                description = description.strip()
            
            # Build the event data
            if title and date_str:
                event_data = {
                    'title': title,
                    'date': date_str,
                    'venue': 'Hyperreal Film Club',
                    'type': 'movie',
                    'url': event_url,
                    'location': '301 Chicon Street, Austin, TX 78702'
                }
                
                if time_str:
                    event_data['time'] = time_str
                
                if description:
                    event_data['description'] = description
                
                return event_data
            
            return None
            
        except Exception as e:
            print(f"    Error parsing event with BeautifulSoup: {e}")
            return None
    
    def scrape_events(self, days_ahead: int = None) -> List[Dict]:
        """Scrape Hyperreal events from the current month's calendar"""
        print(f"Scraping {self.venue_name}...")
        all_events = []
        
        # Get the calendar URL (current month by default)
        for url in self.get_target_urls():
            try:
                # Fetch the page
                response = self.session.get(url, timeout=15)
                if response.status_code != 200:
                    print(f"  Failed to fetch {url}: Status {response.status_code}")
                    continue
                
                # Extract event links from the calendar page
                soup = BeautifulSoup(response.text, 'html.parser')
                event_links = set()
                
                # Find all event links (pattern: /events/*)
                for link in soup.find_all('a', href=lambda h: h and h.startswith('/events/')):
                    href = link.get('href', '')
                    if href:
                        full_url = f"{self.base_url}{href}"
                        event_links.add(full_url)
                
                # Filter for movie screenings (skip parties, fundraisers, etc.)
                movie_links = [
                    url for url in event_links 
                    if 'screening' in url.lower() or 'movie' in url.lower()
                ]
                
                print(f"  Found {len(movie_links)} movie events")
                
                # Scrape each individual event page
                for event_url in movie_links:
                    try:
                        event_response = self.session.get(event_url, timeout=10)
                        if event_response.status_code == 200:
                            # First try Beautiful Soup extraction
                            event_data = self.extract_event_with_beautifulsoup(
                                html=event_response.text,
                                event_url=event_url
                            )
                            
                            if event_data:
                                all_events.append(event_data)
                                print(f"    ✓ Extracted with BeautifulSoup: {event_data.get('title')}")
                            else:
                                # Fallback to LLM extraction if Beautiful Soup fails
                                print(f"    BeautifulSoup extraction failed, trying LLM for {event_url}")
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
                                        print(f"    ✓ Extracted with LLM: {event_data.get('title')}")
                    except Exception as e:
                        print(f"    Error extracting from {event_url}: {e}")
                        continue
                
            except Exception as e:
                print(f"  Error scraping {url}: {e}")
                continue
        
        print(f"Successfully scraped {len(all_events)} Hyperreal events total")
        return all_events
    
    def get_event_details(self, url: str) -> Dict:
        """Get additional details for a specific event - returns empty dict since details are already complete"""
        return {}