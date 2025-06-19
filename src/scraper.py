"""
Web scraper for Austin Film Society calendar, Hyperreal Film Club, and other venues
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import re
from typing import List, Dict, Optional
import time
import json
import os

import asyncio
from pyppeteer import launch
from firecrawl import FirecrawlApp
from dotenv import load_dotenv

load_dotenv()
class AFSScraper:
    def __init__(self):
        self.base_url = "https://www.austinfilm.org"
        self.calendar_url = f"{self.base_url}/calendar/"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
    
    def scrape_calendar(self) -> List[Dict]:
        """Scrape events from AFS calendar page"""
        try:
            response = self.session.get(self.calendar_url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            events = self._parse_calendar_events(soup)
            
            return events
            
        except requests.RequestException as e:
            raise Exception(f"Failed to fetch calendar: {e}")
    
    def _parse_calendar_events(self, soup: BeautifulSoup) -> List[Dict]:
        """Parse events from calendar HTML"""
        events = []
        
        # Find all calendar cells with events
        calendar_cells = soup.find_all('td')
        
        for cell in calendar_cells:
            # Look for event links in each cell
            event_links = cell.find_all('a', href=True)
            
            for link in event_links:
                # Skip if not an event/screening link
                if not ('/screening/' in link['href'] or '/event/' in link['href']):
                    continue
                
                event_data = self._extract_event_data(cell, link)
                if event_data:
                    events.append(event_data)
        
        return events
    
    def _extract_event_data(self, cell, link) -> Optional[Dict]:
        """Extract event data from calendar cell and link"""
        try:
            # Get event title
            title = link.get_text(strip=True)
            if not title:
                return None
            
            # Get event URL
            url = link['href']
            if not url.startswith('http'):
                url = self.base_url + url
            
            # Extract date from cell
            date_header = cell.find('h4')
            if not date_header:
                return None
            
            date_text = date_header.get_text(strip=True)
            event_date = self._parse_date(date_text)
            
            # Extract time from text near the link
            time_text = self._extract_time_from_cell(cell, link)
            
            # Determine event type
            event_type = 'screening' if '/screening/' in url else 'event'
            
            return {
                'title': title,
                'url': url,
                'date': event_date,
                'time': time_text,
                'type': event_type,
                'location': 'Austin Film Society',
                'raw_html': str(cell)
            }
            
        except Exception as e:
            print(f"Error extracting event data: {e}")
            return None
    
    def _parse_date(self, date_text: str) -> Optional[str]:
        """Parse date from header text like 'Sunday, June 15'"""
        try:
            # Extract month and day
            match = re.search(r'(\w+),\s+(\w+)\s+(\d+)', date_text)
            if not match:
                return None
            
            day_name, month_name, day = match.groups()
            
            # Map month names to numbers
            month_map = {
                'January': 1, 'February': 2, 'March': 3, 'April': 4,
                'May': 5, 'June': 6, 'July': 7, 'August': 8,
                'September': 9, 'October': 10, 'November': 11, 'December': 12
            }
            
            month_num = month_map.get(month_name)
            if not month_num:
                return None
            
            # Assume current year, but check if we need next year
            year = datetime.now().year
            try_date = datetime(year, month_num, int(day))
            
            # If date is in the past and we're in December, try next year
            if try_date < datetime.now() and datetime.now().month == 12:
                year += 1
                try_date = datetime(year, month_num, int(day))
            
            return try_date.strftime('%Y-%m-%d')
            
        except Exception as e:
            print(f"Error parsing date '{date_text}': {e}")
            return None
    
    def _extract_time_from_cell(self, cell, link) -> Optional[str]:
        """Extract time information from calendar cell"""
        try:
            # Get all text from the cell
            cell_text = cell.get_text()
            
            # Find the line containing the event link
            lines = cell_text.split('\n')
            link_text = link.get_text(strip=True)
            
            for i, line in enumerate(lines):
                if link_text in line:
                    # Check current line and next line for time
                    time_line = line
                    if i + 1 < len(lines):
                        time_line += ' ' + lines[i + 1]
                    
                    # Look for time patterns like "8:00 PM", "3:30 PM", etc.
                    time_match = re.search(r'(\d{1,2}:\d{2}\s*[AP]M)', time_line, re.IGNORECASE)
                    if time_match:
                        return time_match.group(1)
            
            return None
            
        except Exception as e:
            print(f"Error extracting time: {e}")
            return None
    
    def get_event_details(self, event_url: str) -> Dict:
        """Get detailed information from event page"""
        try:
            response = self.session.get(event_url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract description
            description = ""
            desc_div = soup.find('div', class_='entry-content') or soup.find('div', class_='content')
            if desc_div:
                description = desc_div.get_text(strip=True)
            
            # Check for special screening indicators
            is_special = self._detect_special_screening(soup, description)
            
            # Extract movie metadata (duration and director)
            metadata = self._extract_movie_metadata(soup, description)
            
            # Detect if this is actually a movie using the page structure
            is_movie = self._detect_movie_format(soup)
            
            # Add small delay to be respectful
            time.sleep(0.5)
            
            return {
                'description': description,
                'is_special_screening': is_special,
                'duration': metadata.get('duration'),
                'director': metadata.get('director'),
                'country': metadata.get('country'),
                'year': metadata.get('year'),
                'language': metadata.get('language'),
                'is_movie': is_movie,
                'full_html': str(soup)
            }
            
        except requests.RequestException as e:
            print(f"Failed to fetch event details from {event_url}: {e}")
            return {'description': '', 'is_special_screening': False, 'duration': None, 'director': None, 'country': None, 'year': None, 'language': None, 'is_movie': False}
    
    def _detect_special_screening(self, soup: BeautifulSoup, description: str) -> bool:
        """Detect if this is a special screening (Q&A, 35mm, etc.)"""
        special_indicators = [
            'q&a', 'q and a', 'discussion', 'director', 'filmmaker',
            '35mm', '16mm', '70mm', 'film print', 'print',
            'world premiere', 'premiere', 'special screening',
            'in person', 'live', 'conversation', 'introduction'
        ]
        
        # Check in description
        text_to_check = description.lower()
        
        # Also check page title and other elements
        title = soup.find('title')
        if title:
            text_to_check += ' ' + title.get_text().lower()
        
        # Check for any special indicators
        for indicator in special_indicators:
            if indicator in text_to_check:
                return True
        
        return False
    
    def _extract_movie_metadata(self, soup: BeautifulSoup, description: str) -> Dict:
        """Extract movie metadata from the structured AFS format"""
        metadata = {}
        
        # Get all text content from the page
        full_text = soup.get_text()
        
        # Extract director (look for "Directed by" pattern)
        director_match = re.search(r'Directed by\s+([^\n]+)', full_text, re.IGNORECASE)
        if director_match:
            metadata['director'] = director_match.group(1).strip()
        
        # Find the metadata line pattern: "Country, Year, Duration, Format[, Language info]"
        # Look for lines that match: Word(s), 4-digit year, duration
        metadata_pattern = r'([^,\n]+),\s*(\d{4}),\s*([^,\n]+)(?:,\s*[^,\n]*)?(?:,\s*In\s+([^,\n]+)\s+with[^,\n]*)?'
        metadata_match = re.search(metadata_pattern, full_text)
        
        if metadata_match:
            country = metadata_match.group(1).strip()
            year = metadata_match.group(2).strip()
            duration_raw = metadata_match.group(3).strip()
            language_line = metadata_match.group(4) if len(metadata_match.groups()) >= 4 else None
            
            # Store country and year
            metadata['country'] = country
            metadata['year'] = int(year)
            
            # Parse duration (e.g., "1h 7min" -> "67 min")
            duration_match = re.search(r'(\d+)h?\s*(\d*)m?i?n?', duration_raw)
            if duration_match:
                hours = int(duration_match.group(1)) if duration_match.group(1) else 0
                minutes = int(duration_match.group(2)) if duration_match.group(2) else 0
                
                if 'h' in duration_raw:  # Format like "1h 7min"
                    total_minutes = hours * 60 + minutes
                else:  # Format like "90min"
                    total_minutes = hours  # hours is actually minutes in this case
                
                metadata['duration'] = f"{total_minutes} min"
            
            # Extract language from "In [Language] with" pattern
            if language_line:
                # Extract the language name after "In "
                metadata['language'] = language_line.strip()
            else:
                # No explicit language - assume English for US/UK, leave empty for others
                if country.upper() in ['USA', 'US', 'UK', 'UNITED STATES', 'UNITED KINGDOM']:
                    metadata['language'] = 'English'
                else:
                    metadata['language'] = None  # Let frontend handle display
        
        return metadata
    
    def _detect_movie_format(self, soup: BeautifulSoup) -> bool:
        """Detect if this is a movie based on the consistent AFS movie page format"""
        try:
            # Get all text content from the page
            full_text = soup.get_text()
            
            # Look for the movie format pattern:
            # MOVIE TITLE
            # Directed by [Director Name]
            # Country, Year, Duration, Format
            
            # Check for "Directed by" - this is the most reliable indicator
            directed_by_pattern = r'Directed by\s+([^.\n]+)'
            if not re.search(directed_by_pattern, full_text, re.IGNORECASE):
                return False
            
            # Check for the country/year/duration pattern
            # Examples: "USA, 1985, 1h 31min, DCP" or "France, 1985, 1h 7min, DCP"
            country_year_pattern = r'[A-Z]{2,}[^,]*,\s*\d{4},\s*\d+h?\s*\d*m?i?n'
            if not re.search(country_year_pattern, full_text):
                return False
            
            print(f"✓ Detected movie format in page")
            return True
            
        except Exception as e:
            print(f"Error detecting movie format: {e}")
            return False


class HyperrealScraper:
    def __init__(self):
        self.base_url = "https://hyperrealfilm.club"
        self.calendar_url = f"{self.base_url}/events?view=calendar"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
    
    def scrape_calendar(self, target_month: str = None) -> List[Dict]:
        """Scrape events from Hyperreal Film Club calendar"""
        try:
            # If target_month provided, use it (format: MM-YYYY)
            if target_month:
                url = f"{self.calendar_url}&month={target_month}"
            else:
                # Default to current month
                now = datetime.now()
                current_month = now.strftime("%m-%Y")
                url = f"{self.calendar_url}&month={current_month}"
            
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            events = self._parse_calendar_events(soup)
            
            return events
            
        except requests.RequestException as e:
            print(f"Failed to fetch Hyperreal calendar: {e}")
            return []
    
    def _parse_calendar_events(self, soup: BeautifulSoup) -> List[Dict]:
        """Parse events from Hyperreal calendar HTML"""
        events = []
        
        # Find all event list items
        event_items = soup.find_all('li')
        
        for item in event_items:
            event_data = self._extract_event_data(item)
            if event_data:
                events.append(event_data)
        
        return events
    
    def _extract_event_data(self, item) -> Optional[Dict]:
        """Extract event data from list item"""
        try:
            # Look for event link
            link = item.find('a', href=True)
            if not link:
                return None
            
            # Get event title
            title = link.get_text(strip=True)
            if not title:
                return None
            
            # Get event URL
            url = link['href']
            if not url.startswith('http'):
                url = self.base_url + url
            
            # Extract date and time from item text
            item_text = item.get_text()
            
            # Look for date pattern like "Monday, June 3, 2025"
            date_match = re.search(r'(\w+),\s+(\w+)\s+(\d+),\s+(\d{4})', item_text)
            if not date_match:
                return None
            
            day_name, month_name, day, year = date_match.groups()
            event_date = self._parse_date(month_name, day, year)
            
            # Look for time pattern like "7:30 PM – 11:00 PM"
            time_match = re.search(r'(\d+:\d+\s*[AP]M)\s*[–-]\s*(\d+:\d+\s*[AP]M)', item_text)
            start_time = time_match.group(1) if time_match else "7:30 PM"
            
            return {
                'title': title,
                'url': url,
                'date': event_date,
                'time': start_time,
                'type': 'screening',
                'location': 'Hyperreal Film Club',
                'venue': 'Hyperreal'
            }
            
        except Exception as e:
            print(f"Error extracting Hyperreal event data: {e}")
            return None
    
    def _parse_date(self, month_name: str, day: str, year: str) -> Optional[str]:
        """Parse date components into YYYY-MM-DD format"""
        try:
            # Map month names to numbers
            month_map = {
                'January': 1, 'February': 2, 'March': 3, 'April': 4,
                'May': 5, 'June': 6, 'July': 7, 'August': 8,
                'September': 9, 'October': 10, 'November': 11, 'December': 12
            }
            
            month_num = month_map.get(month_name)
            if not month_num:
                return None
            
            event_date = datetime(int(year), month_num, int(day))
            return event_date.strftime('%Y-%m-%d')
            
        except Exception as e:
            print(f"Error parsing Hyperreal date: {e}")
            return None
    
    def get_event_details(self, event_url: str) -> Dict:
        """Get detailed information from Hyperreal event page"""
        try:
            response = self.session.get(event_url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract description
            description = ""
            desc_div = soup.find('div', class_='entry-content') or soup.find('div', class_='content')
            if desc_div:
                description = desc_div.get_text(strip=True)
            
            # Hyperreal events are typically special screenings
            is_special = True
            
            # Default metadata for Hyperreal (often unknown)
            time.sleep(0.5)  # Be respectful
            
            return {
                'description': description,
                'is_special_screening': is_special,
                'duration': None,  # Often unknown
                'director': None,  # Often unknown  
                'country': None,   # Often unknown
                'year': None,      # Often unknown
                'language': None,  # Often unknown
                'is_movie': True,  # Assume all Hyperreal events are movies
                'venue': 'Hyperreal'
            }
            
        except requests.RequestException as e:
            print(f"Failed to fetch Hyperreal event details from {event_url}: {e}")
            return {
                'description': '', 
                'is_special_screening': True, 
                'duration': None, 
                'director': None, 
                'country': None, 
                'year': None, 
                'language': None, 
                'is_movie': True,
                'venue': 'Hyperreal'
            }


class EarlyMusicAustinScraper:
    """Scraper for Texas Early Music Project events"""
    
    def __init__(self):
        self.base_url = "https://www.early-music.org"
    
    def scrape_calendar(self) -> List[Dict]:
        """Return empty list - classical data now loaded from docs/classical_data.json"""
        return []
    
    def get_event_details(self, event: Dict) -> Dict:
        """Return detailed information for early music events"""
        return {
            'description': f"Texas Early Music Project presents {event['title']}.\n\nProgram:\n{event['program']}\n\nFeaturing: {event['featured_artist']}",
            'is_special_screening': False,
            'duration': '90 min',
            'director': None,
            'country': 'USA',
            'year': int(event['date'][:4]),
            'language': None,
            'is_movie': False,
            'venue': 'EarlyMusic',
            'series': event.get('series'),
            'composers': event.get('composers', []),
            'works': event.get('works', []),
            'featured_artist': event.get('featured_artist')
        }


class LaFolliaAustinScraper:
    """Scraper for La Follia Austin chamber music events"""
    
    def __init__(self):
        self.base_url = "https://www.lafolliaaustin.org"
    
    def scrape_calendar(self) -> List[Dict]:
        """Return empty list - classical data now loaded from docs/classical_data.json"""
        return []
    
    def get_event_details(self, event: Dict) -> Dict:
        """Return detailed information for chamber music events"""
        return {
            'description': f"La Follia Austin presents {event['title']}.\n\nProgram:\n{event['program']}\n\nFeaturing: {event['featured_artist']}",
            'is_special_screening': False,
            'duration': '75 min',
            'director': None,
            'country': 'USA',
            'year': int(event['date'][:4]),
            'language': None,
            'is_movie': False,
            'venue': 'LaFollia',
            'series': event.get('series'),
            'composers': event.get('composers', []),
            'works': event.get('works', []),
            'featured_artist': event.get('featured_artist')
        }


class AlienatedMajestyBooksScraper:
    """Scraper for Alienated Majesty Books book club events"""
    
    def __init__(self):
        self.base_url = "https://www.alienatedmajestybooks.com"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        # Initialize Firecrawl client
        firecrawl_api_key = os.getenv('FIRECRAWL_API_KEY')
        self.firecrawl = FirecrawlApp(api_key=firecrawl_api_key) if firecrawl_api_key else None
    
    def _get_rendered_html(self, url: str) -> Optional[str]:
        """Fetch page content using headless Chrome"""
        async def fetch():
            browser = await launch(headless=True, args=['--no-sandbox'])
            page = await browser.newPage()
            await page.goto(url, {'waitUntil': 'networkidle2'})
            content = await page.content()
            await browser.close()
            return content

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            html = loop.run_until_complete(fetch())
            return html
        except Exception as e:
            print(f"Pyppeteer failed: {e}")
            return None
        finally:
            try:
                loop.close()
            except Exception:
                pass

    def _parse_book_club_html(self, html: str) -> List[Dict]:
        """Parse rendered HTML for book club events"""
        soup = BeautifulSoup(html, 'html.parser')
        events = []

        text_lines = [line.strip() for line in soup.get_text('\n').split('\n') if line.strip()]
        current = None
        for line in text_lines:
            lower = line.lower()
            if 'book club' in lower and not line.startswith('http'):
                if current:
                    events.append(current)
                current = {
                    'title': line,
                    'book': '',
                    'author': '',
                    'dates': [],
                    'times': ['7:00 PM'],
                    'venue_name': 'Alienated Majesty Books',
                    'series': 'Book Club',
                    'description': line,
                }
            elif current and 'by' in lower and not current['author']:
                parts = line.split('by', 1)
                if len(parts) == 2:
                    book = parts[0].strip(' "')
                    author = parts[1].strip()
                    current['book'] = book
                    current['author'] = author
            elif current:
                date_match = re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+(\d{4})?', line)
                if date_match:
                    month = date_match.group(1)
                    day = re.search(r'\d{1,2}', line).group(0)
                    year = date_match.group(2) or str(datetime.now().year)
                    try:
                        dt = datetime.strptime(f"{month} {day} {year}", "%B %d %Y")
                        current['dates'].append(dt.strftime("%Y-%m-%d"))
                    except Exception:
                        pass

        if current:
            events.append(current)

        return [e for e in events if e['dates']]

    def _scrape_book_club_page(self):
        """Scrape the book club page for current events"""
        url = f"{self.base_url}/book-clubs"
        
        # Try Firecrawl first if available
        if self.firecrawl:
            try:
                print("Using Firecrawl for JavaScript rendering")
                scrape_result = self.firecrawl.scrape_url(url, params={'formats': ['markdown', 'html']})
                if scrape_result and 'html' in scrape_result:
                    events = self._parse_book_club_html(scrape_result['html'])
                    if events:
                        return events
                    print("Firecrawl succeeded but no events found")
                else:
                    print("Firecrawl failed to return HTML")
            except Exception as e:
                print(f"Firecrawl error: {e}")
        
        # Try Pyppeteer as fallback
        html = self._get_rendered_html(url)
        if html:
            events = self._parse_book_club_html(html)
            if events:
                return events
            print("Pyppeteer succeeded but no events found")
        
        # Try regular requests as last resort
        try:
            print("Falling back to requests scraping")
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            events = self._parse_book_club_html(response.text)
            if events:
                return events
            print("Requests succeeded but no events found")
        except Exception as e:
            print(f"Error with requests scraping: {e}")
        
        # Return empty list if all methods fail
        print("All scraping methods failed - returning empty list")
        return []
    
    
    def scrape_calendar(self) -> List[Dict]:
        """Return book club events as standardized event data"""
        events = []
        
        # Get current book club data from website
        book_clubs = self._scrape_book_club_page()
        
        # Return empty list if no book clubs found
        if not book_clubs:
            print("No book club events found for Alienated Majesty Books")
            return []
        
        for club in book_clubs:
            for i, date in enumerate(club['dates']):
                time = club['times'][i] if i < len(club['times']) else club['times'][0]
                
                event = {
                    'title': f"{club['title']}: {club['book']}",
                    'url': f"{self.base_url}/book-clubs",
                    'date': date,
                    'time': time,
                    'type': 'book_club',
                    'location': club['venue_name'],
                    'venue': 'AlienatedMajesty',
                    'series': club['series'],
                    'book': club['book'],
                    'author': club['author'],
                    'description': club['description']
                }
                events.append(event)
        
        return events
    
    def get_event_details(self, event: Dict) -> Dict:
        """Return detailed information for book club events"""
        return {
            'description': f"Book club discussion of '{event['book']}' by {event['author']}.\n\n{event['description']}",
            'is_special_screening': False,
            'duration': '90 min',
            'director': None,
            'country': 'USA',
            'year': int(event['date'][:4]),
            'language': 'English',
            'is_movie': False,
            'venue': 'AlienatedMajesty',
            'series': event.get('series'),
            'book': event.get('book'),
            'author': event.get('author')
        }


class FirstLightAustinScraper:
    """Scraper for First Light Austin book club events"""
    
    def __init__(self):
        self.base_url = "https://www.firstlightaustin.com"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        # Initialize Firecrawl client
        firecrawl_api_key = os.getenv('FIRECRAWL_API_KEY')
        self.firecrawl = FirecrawlApp(api_key=firecrawl_api_key) if firecrawl_api_key else None
    
    def _parse_book_club_text(self, text: str) -> List[Dict]:
        """Parse book club information from page text"""
        import re
        
        book_clubs = []
        lines = text.split('\n')
        current_club = None
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Look for book club names
            if 'book club' in line.lower() and any(keyword in line.lower() for keyword in ['world wide', 'motherhood', 'small', 'future']):
                if current_club:
                    book_clubs.append(current_club)
                current_club = {
                    'title': line,
                    'book': '',
                    'author': '',
                    'dates': [],
                    'times': ['7:00 PM'],
                    'venue_name': 'First Light Austin',
                    'series': 'Book Club',
                    'host': '',
                    'description': ''
                }
            
            # Look for book titles
            elif current_club and (line.startswith('"') and line.endswith('"')):
                current_club['book'] = line.strip('"')
            
            # Look for authors
            elif current_club and 'by ' in line.lower() and len(line.split()) <= 4:
                current_club['author'] = line.replace('by ', '').strip()
            
            # Look for dates
            elif current_club and any(month in line.lower() for month in ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december']):
                # Parse date from text like "Friday, June 27th"
                date_match = re.search(r'(\w+),?\s+(\w+)\s+(\d+)', line)
                if date_match:
                    month_str = date_match.group(2)
                    day = int(date_match.group(3))
                    
                    # Convert month name to number
                    months = {
                        'january': 1, 'february': 2, 'march': 3, 'april': 4,
                        'may': 5, 'june': 6, 'july': 7, 'august': 8,
                        'september': 9, 'october': 10, 'november': 11, 'december': 12
                    }
                    
                    month_num = months.get(month_str.lower())
                    if month_num:
                        # Assume current year, but if month has passed, use next year
                        from datetime import datetime
                        current_year = datetime.now().year
                        current_month = datetime.now().month
                        
                        year = current_year if month_num >= current_month else current_year + 1
                        date_str = f"{year}-{month_num:02d}-{day:02d}"
                        current_club['dates'].append(date_str)
        
        # Add the last club if it exists
        if current_club and current_club['book']:
            book_clubs.append(current_club)
        
        return [club for club in book_clubs if club['dates']]

    def _scrape_book_club_page(self):
        """Scrape the First Light Austin book club page"""
        url = f"{self.base_url}/book-club"
        
        # Try Firecrawl first if available
        if self.firecrawl:
            try:
                print("Using Firecrawl for First Light Austin")
                scrape_result = self.firecrawl.scrape_url(url, params={'formats': ['markdown', 'html']})
                if scrape_result and 'html' in scrape_result:
                    soup = BeautifulSoup(scrape_result['html'], 'html.parser')
                    events = self._parse_book_club_text(soup.get_text())
                    if events:
                        return events
                    print("Firecrawl succeeded but no events found")
                elif scrape_result and 'markdown' in scrape_result:
                    events = self._parse_book_club_text(scrape_result['markdown'])
                    if events:
                        return events
                    print("Firecrawl markdown succeeded but no events found")
                else:
                    print("Firecrawl failed to return content")
            except Exception as e:
                print(f"Firecrawl error: {e}")
        
        # Try regular requests as fallback
        try:
            print("Falling back to requests scraping for First Light Austin")
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            events = self._parse_book_club_text(soup.get_text())
            if events:
                return events
            print("Requests succeeded but no events found")
        except Exception as e:
            print(f"Error scraping First Light Austin: {e}")
        
        # Return empty list if all methods fail
        print("All scraping methods failed for First Light Austin - returning empty list")
        return []
    
    
    def scrape_calendar(self) -> List[Dict]:
        """Return book club events as standardized event data"""
        events = []
        
        # Get current book club data from website
        book_clubs = self._scrape_book_club_page()
        
        # Return empty list if no book clubs found
        if not book_clubs:
            print("No book club events found for First Light Austin")
            return []
        
        for club in book_clubs:
            for i, date in enumerate(club['dates']):
                time = club['times'][i] if i < len(club['times']) else club['times'][0]
                
                event = {
                    'title': f"{club['title']}: {club['book']}",
                    'url': f"{self.base_url}/book-club",
                    'date': date,
                    'time': time,
                    'type': 'book_club',
                    'location': club['venue_name'],
                    'venue': 'FirstLight',
                    'series': club['series'],
                    'book': club['book'],
                    'author': club['author'],
                    'host': club.get('host', ''),
                    'description': club['description']
                }
                events.append(event)
        
        return events
    
    def get_event_details(self, event: Dict) -> Dict:
        """Return detailed information for book club events"""
        return {
            'description': f"Book club discussion of '{event['book']}' by {event['author']}.\n\nHosted by {event['host']}.\n\n{event['description']}",
            'is_special_screening': False,
            'duration': '90 min',
            'director': None,
            'country': 'USA',
            'year': int(event['date'][:4]),
            'language': 'English',
            'is_movie': False,
            'venue': 'FirstLight',
            'series': event.get('series'),
            'book': event.get('book'),
            'author': event.get('author'),
            'host': event.get('host')
        }


class AustinSymphonyScraper:
    """Austin Symphony Orchestra season scraper"""
    
    def __init__(self):
        self.base_url = "https://austinsymphony.org"
    
    def scrape_calendar(self) -> List[Dict]:
        """Return empty list - classical data now loaded from docs/classical_data.json"""
        return []
    
    def get_event_details(self, event: Dict) -> Dict:
        """Return detailed information for symphony events"""
        # For symphony events, we already have comprehensive data
        return {
            'description': f"Austin Symphony Orchestra presents {event['title']}.\n\nProgram:\n{event['program']}\n\nFeaturing: {event['featured_artist']}",
            'is_special_screening': False,  # Not applicable to concerts
            'duration': '120 min',  # Typical symphony concert length
            'director': None,  # Not applicable
            'country': 'USA',  # Austin Symphony is US-based
            'year': int(event['date'][:4]),  # Extract year from date
            'language': None,  # Not applicable to instrumental music
            'is_movie': False,  # These are concerts, not movies
            'venue': 'Symphony',
            'series': event.get('series'),
            'composers': event.get('composers', []),
            'works': event.get('works', []),
            'featured_artist': event.get('featured_artist')
        }


class MultiVenueScraper:
    """Unified scraper for all supported venues"""

    def __init__(self):
        self.afs_scraper = AFSScraper()
        self.hyperreal_scraper = HyperrealScraper()
        self.symphony_scraper = AustinSymphonyScraper()
        self.early_music_scraper = EarlyMusicAustinScraper()
        self.la_follia_scraper = LaFolliaAustinScraper()
        self.alienated_majesty_scraper = AlienatedMajestyBooksScraper()
        self.first_light_scraper = FirstLightAustinScraper()
        self.existing_events_cache = set()  # Cache for duplicate detection
        self.last_updated = {}
    
    def scrape_all_venues(self, target_week: bool = False) -> List[Dict]:
        """Scrape events from all supported venues"""
        all_events = []
        self.last_updated = {}
        
        # Scrape AFS
        print("Scraping Austin Film Society...")
        try:
            afs_events = self.afs_scraper.scrape_calendar()
            for event in afs_events:
                event['venue'] = 'AFS'
                all_events.append(event)
            print(f"Found {len(afs_events)} AFS events")
            self.last_updated['AFS'] = datetime.now().isoformat()
        except Exception as e:
            print(f"Error scraping AFS: {e}")
            self.last_updated['AFS'] = None
        
        # Scrape Hyperreal
        print("Scraping Hyperreal Film Club...")
        try:
            if target_week:
                # For testing, just get current month
                current_month = datetime.now().strftime("%m-%Y")
                hyperreal_events = self.hyperreal_scraper.scrape_calendar(current_month)
            else:
                hyperreal_events = self.hyperreal_scraper.scrape_calendar()

            for event in hyperreal_events:
                event['venue'] = 'Hyperreal'
                all_events.append(event)
            print(f"Found {len(hyperreal_events)} Hyperreal events")
            self.last_updated['Hyperreal'] = datetime.now().isoformat()
        except Exception as e:
            print(f"Error scraping Hyperreal: {e}")
            self.last_updated['Hyperreal'] = None
        
        # Scrape Austin Symphony
        print("Loading Austin Symphony season...")
        try:
            symphony_events = self.symphony_scraper.scrape_calendar()
            for event in symphony_events:
                event['venue'] = 'Symphony'
                all_events.append(event)
            print(f"Found {len(symphony_events)} Symphony events")
            self.last_updated['Symphony'] = datetime.now().isoformat()
        except Exception as e:
            print(f"Error loading Symphony events: {e}")
            self.last_updated['Symphony'] = None
        
        # Scrape Texas Early Music Project
        print("Loading Early Music Austin season...")
        try:
            early_music_events = self.early_music_scraper.scrape_calendar()
            for event in early_music_events:
                event['venue'] = 'EarlyMusic'
                all_events.append(event)
            print(f"Found {len(early_music_events)} Early Music events")
            self.last_updated['EarlyMusic'] = datetime.now().isoformat()
        except Exception as e:
            print(f"Error loading Early Music events: {e}")
            self.last_updated['EarlyMusic'] = None
        
        # Scrape La Follia Austin
        print("Loading La Follia Austin events...")
        try:
            la_follia_events = self.la_follia_scraper.scrape_calendar()
            for event in la_follia_events:
                event['venue'] = 'LaFollia'
                all_events.append(event)
            print(f"Found {len(la_follia_events)} La Follia events")
            self.last_updated['LaFollia'] = datetime.now().isoformat()
        except Exception as e:
            print(f"Error loading La Follia events: {e}")
            self.last_updated['LaFollia'] = None
        
        # Scrape Alienated Majesty Books
        print("Loading Alienated Majesty Books club...")
        try:
            alienated_majesty_events = self.alienated_majesty_scraper.scrape_calendar()
            for event in alienated_majesty_events:
                event['venue'] = 'AlienatedMajesty'
                all_events.append(event)
            print(f"Found {len(alienated_majesty_events)} Alienated Majesty events")
            self.last_updated['AlienatedMajesty'] = datetime.now().isoformat()
        except Exception as e:
            print(f"Error loading Alienated Majesty events: {e}")
            self.last_updated['AlienatedMajesty'] = None
        
        # Scrape First Light Austin
        print("Loading First Light Austin book clubs...")
        try:
            first_light_events = self.first_light_scraper.scrape_calendar()
            for event in first_light_events:
                event['venue'] = 'FirstLight'
                all_events.append(event)
            print(f"Found {len(first_light_events)} First Light events")
            self.last_updated['FirstLight'] = datetime.now().isoformat()
        except Exception as e:
            print(f"Error loading First Light events: {e}")
            self.last_updated['FirstLight'] = None
        
        # Filter to current week if requested
        if target_week:
            all_events = self._filter_to_current_week(all_events)
            print(f"Filtered to {len(all_events)} events for current week")
        
        return all_events
    
    def _filter_to_current_week(self, events: List[Dict]) -> List[Dict]:
        """Filter events to current week only"""
        now = datetime.now()
        # Get start of current week (Monday)
        start_of_week = now - timedelta(days=now.weekday())
        end_of_week = start_of_week + timedelta(days=6)
        
        filtered_events = []
        for event in events:
            try:
                event_date = datetime.strptime(event['date'], '%Y-%m-%d')
                if start_of_week <= event_date <= end_of_week:
                    filtered_events.append(event)
            except (ValueError, KeyError):
                continue
        
        return filtered_events
    
    def load_existing_events(self, existing_data_path: str = None) -> None:
        """Load existing events to cache for duplicate detection"""
        if not existing_data_path:
            existing_data_path = "/Users/HCornier/Documents/Github/Culture-Calendar/docs/data.json"
        
        try:
            if os.path.exists(existing_data_path):
                with open(existing_data_path, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
                
                # Create cache of event identifiers
                for event in existing_data:
                    if 'screenings' in event:
                        for screening in event['screenings']:
                            event_id = self._create_event_id(event['title'], screening['date'], screening['time'], event.get('venue', ''))
                            self.existing_events_cache.add(event_id)
                
                print(f"Loaded {len(self.existing_events_cache)} existing events for duplicate detection")
        except Exception as e:
            print(f"Warning: Could not load existing events for duplicate detection: {e}")
    
    def _create_event_id(self, title: str, date: str, time: str, venue: str) -> str:
        """Create a unique identifier for an event"""
        # Normalize data for consistent comparison
        normalized_title = (title or '').strip().lower()
        normalized_venue = (venue or '').strip().lower()
        normalized_time = (time or '').strip().lower()
        return f"{normalized_title}_{date}_{normalized_time}_{normalized_venue}"
    
    def _is_duplicate_event(self, title: str, date: str, time: str, venue: str) -> bool:
        """Check if an event is a duplicate of an existing event"""
        event_id = self._create_event_id(title, date, time, venue)
        return event_id in self.existing_events_cache
    
    def scrape_new_events_only(self, target_week: bool = False, existing_data_path: str = None) -> List[Dict]:
        """Scrape only new events that don't already exist"""
        # Load existing events for duplicate detection
        self.load_existing_events(existing_data_path)
        
        # Get all events
        all_events = self.scrape_all_venues(target_week)
        
        # Filter out duplicates
        new_events = []
        duplicate_count = 0
        
        for event in all_events:
            if not self._is_duplicate_event(event['title'], event['date'], event['time'], event.get('venue', '')):
                new_events.append(event)
                # Add to cache to prevent duplicates within this run
                event_id = self._create_event_id(event['title'], event['date'], event['time'], event.get('venue', ''))
                self.existing_events_cache.add(event_id)
            else:
                duplicate_count += 1
        
        print(f"Found {len(new_events)} new events ({duplicate_count} duplicates filtered out)")
        return new_events
    
    def get_event_details(self, event: Dict) -> Dict:
        """Get event details using appropriate scraper based on venue"""
        venue = event.get('venue', 'AFS')
        
        if venue == 'Hyperreal':
            return self.hyperreal_scraper.get_event_details(event['url'])
        elif venue == 'Symphony':
            return self.symphony_scraper.get_event_details(event)
        elif venue == 'EarlyMusic':
            return self.early_music_scraper.get_event_details(event)
        elif venue == 'LaFollia':
            return self.la_follia_scraper.get_event_details(event)
        elif venue == 'AlienatedMajesty':
            return self.alienated_majesty_scraper.get_event_details(event)
        elif venue == 'FirstLight':
            return self.first_light_scraper.get_event_details(event)
        else:
            return self.afs_scraper.get_event_details(event['url'])