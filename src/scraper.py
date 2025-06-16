"""
Web scraper for Austin Film Society calendar
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import re
from typing import List, Dict, Optional
import time

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
            
            # Add small delay to be respectful
            time.sleep(0.5)
            
            return {
                'description': description,
                'is_special_screening': is_special,
                'full_html': str(soup)
            }
            
        except requests.RequestException as e:
            print(f"Failed to fetch event details from {event_url}: {e}")
            return {'description': '', 'is_special_screening': False}
    
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