"""
Hyperreal Movie Club scraper for extracting movie screening events.
"""

import asyncio
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from pyppeteer import launch

from ..base_scraper import BaseScraper
from ..schemas import MovieEventSchema


class HyperrealScraper(BaseScraper):
    """Scraper for Hyperreal Movie Club events."""

    def __init__(self):
        super().__init__(
            base_url="https://hyperrealfilm.club", venue_name="Hyperreal Movie Club"
        )
        self.venue_address = "301 Chicon Street, Austin, TX, 78702"

    def get_calendar_url(self, year: int, month: int) -> str:
        """Generate calendar URL for a specific month."""
        month_str = f"{month:02d}-{year}"
        return f"{self.base_url}/events?view=calendar&month={month_str}"

    async def _scrape_with_pyppeteer_async(self, url: str) -> str:
        """Use pyppeteer to render JavaScript-heavy pages."""
        browser = await launch(headless=True)
        try:
            page = await browser.newPage()
            await page.goto(url, {"waitUntil": "networkidle0"})
            content = await page.content()
            return content
        finally:
            await browser.close()

    def _scrape_with_pyppeteer(self, url: str) -> str:
        """Synchronous wrapper for pyppeteer scraping."""
        return asyncio.get_event_loop().run_until_complete(
            self._scrape_with_pyppeteer_async(url)
        )

    def _extract_event_links_from_calendar(self, html_content: str) -> List[str]:
        """Extract individual event page links from calendar HTML."""
        soup = BeautifulSoup(html_content, "html.parser")
        event_links = []
        
        # Get current year for dynamic filtering
        current_year = datetime.now().year

        # Find all event links in the calendar
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            # Check for events with current year in URL
            if f"/events/{current_year}/" in href:
                full_url = urljoin(self.base_url, href)
                event_links.append(full_url)

        return list(set(event_links))  # Remove duplicates

    def _extract_event_data_from_page(
        self, html_content: str, url: str
    ) -> Optional[Dict[str, Any]]:
        """Extract event data from an individual event page."""
        soup = BeautifulSoup(html_content, "html.parser")

        try:
            # Extract title
            title_elem = soup.find("h1", class_="eventitem-title")
            if not title_elem:
                return None

            title = title_elem.get_text(strip=True)

            # Clean up title - extract movie name
            movie_title = self._extract_movie_title(title)

            # Extract date
            date_elem = soup.find("time", class_="event-date")
            if not date_elem:
                return None

            date_str = date_elem.get("datetime")
            if not date_str:
                return None

            # Extract time
            start_time_elem = soup.find("time", class_="event-time-12hr-start")
            end_time_elem = soup.find("time", class_="event-time-12hr-end")

            start_time = (
                start_time_elem.get_text(strip=True) if start_time_elem else None
            )
            end_time = end_time_elem.get_text(strip=True) if end_time_elem else None

            # Extract description
            description = self._extract_description(soup)

            # Extract venue info
            venue_elem = soup.find("span", class_="eventitem-meta-address-line--title")
            venue = venue_elem.get_text(strip=True) if venue_elem else self.venue_name

            # Extract trailer link
            trailer_link = self._extract_trailer_link(soup)

            # Extract presenter/series info
            presenter = self._extract_presenter(title)

            return {
                "title": movie_title,
                "full_title": title,
                "presenter": presenter,
                "dates": [date_str],
                "times": [start_time] if start_time else [],
                "end_times": [end_time] if end_time else [],
                "venue": venue,
                "description": description,
                "trailer_url": trailer_link,
                "url": url,
                "is_special_screening": self._is_special_screening(title),
            }

        except Exception as e:
            print(f"Error extracting data from {url}: {e}")
            return None

    def _extract_movie_title(self, full_title: str) -> str:
        """Extract the actual movie title from the full event title."""
        # Remove common prefixes and suffixes
        title = full_title

        # Remove presenter info (e.g., "A Woman of Taste Presents ~ ")
        if " Presents ~ " in title:
            title = title.split(" Presents ~ ")[-1]
        elif " presents " in title.lower():
            title = title.split(" presents ")[-1]
        elif " ~ " in title:
            title = title.split(" ~ ")[-1]

        # Remove "at HYPERREAL MOVIE CLUB" suffix
        if " at HYPERREAL MOVIE CLUB" in title:
            title = title.replace(" at HYPERREAL MOVIE CLUB", "")

        # Remove other common suffixes
        suffixes_to_remove = [
            " at Hyperreal Movie Club",
            " presented by Queertopia",
            " free screening",
        ]

        for suffix in suffixes_to_remove:
            if suffix in title:
                title = title.replace(suffix, "")

        return title.strip()

    def _extract_presenter(self, full_title: str) -> Optional[str]:
        """Extract presenter/series information from the title."""
        presenters = []

        # Look for common presenter patterns
        if " Presents ~ " in full_title:
            presenter = full_title.split(" Presents ~ ")[0]
            presenters.append(presenter)
        elif " presents " in full_title.lower():
            presenter = full_title.lower().split(" presents ")[0]
            presenters.append(presenter.title())

        # Look for series names
        series_patterns = [
            r"Sad Girl Cinema",
            r"First Times",
            r"Freaks Only",
            r"Fangoria presents",
            r"presented by Queertopia",
        ]

        for pattern in series_patterns:
            if re.search(pattern, full_title, re.IGNORECASE):
                match = re.search(pattern, full_title, re.IGNORECASE)
                presenters.append(match.group())

        return ", ".join(presenters) if presenters else None

    def _extract_description(self, soup: BeautifulSoup) -> str:
        """Extract event description from the page."""
        description_parts = []

        # Look for HTML content blocks
        html_blocks = soup.find_all("div", class_="sqs-html-content")
        for block in html_blocks:
            text = block.get_text(strip=True)
            if text and len(text) > 50:  # Only substantial content
                description_parts.append(text)

        return " ".join(description_parts)

    def _extract_trailer_link(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract trailer link if available."""
        trailer_links = soup.find_all("a", string=re.compile(r"Trailer", re.IGNORECASE))
        for link in trailer_links:
            href = link.get("href")
            if href:
                return href
        return None

    def _is_special_screening(self, title: str) -> bool:
        """Determine if this is a special screening."""
        special_indicators = [
            "free screening",
            "presents",
            "Presents",
            "First Times",
            "Sad Girl Cinema",
            "Freaks Only",
            "Fangoria",
        ]

        return any(indicator in title for indicator in special_indicators)

    def scrape_events(self, days_ahead: int = None) -> List[Dict[str, Any]]:
        """Main scraping method to get all events for specified date range."""
        now = datetime.now()
        all_events = []

        # Determine which months to scrape
        if days_ahead:
            # Calculate end date
            end_date = now + timedelta(days=days_ahead)
            months_to_scrape = []

            # Get all months between now and end_date
            current_date = now.replace(day=1)  # Start of current month
            while current_date <= end_date:
                months_to_scrape.append((current_date.year, current_date.month))
                # Move to next month
                if current_date.month == 12:
                    current_date = current_date.replace(
                        year=current_date.year + 1, month=1
                    )
                else:
                    current_date = current_date.replace(month=current_date.month + 1)

            print(
                f"Scraping Hyperreal events for {len(months_to_scrape)} months (next {days_ahead} days)"
            )
        else:
            # Default: just current month
            months_to_scrape = [(now.year, now.month)]
            print(
                f"Scraping Hyperreal events for current month {now.year}-{now.month:02d}"
            )

        for year, month in months_to_scrape:
            calendar_url = self.get_calendar_url(year, month)
            print(f"  Scraping {year}-{month:02d}...")

            try:
                # Get calendar page (may need JavaScript rendering)
                calendar_html = self._scrape_with_pyppeteer(calendar_url)

                # Extract event links
                event_links = self._extract_event_links_from_calendar(calendar_html)
                print(f"    Found {len(event_links)} event links")

                for event_url in event_links:
                    try:
                        # Get individual event page
                        event_html = self.session.get(event_url).text

                        # Extract event data
                        event_data = self._extract_event_data_from_page(
                            event_html, event_url
                        )
                        if event_data:
                            # Convert to standard format
                            standardized_event = {
                                "title": event_data.get("title", ""),
                                "date": event_data.get("dates", [None])[0],
                                "time": event_data.get("times", [None])[0],
                                "venue": "Hyperreal Movie Club",
                                "location": event_data.get(
                                    "venue", "301 Chicon Street, Austin, TX"
                                ),
                                "type": "movie",
                                "description": event_data.get("description", ""),
                                "url": event_url,
                                "presenter": event_data.get("presenter"),
                                "trailer_url": event_data.get("trailer_url"),
                                "is_special_screening": event_data.get(
                                    "is_special_screening", False
                                ),
                            }
                            all_events.append(standardized_event)
                            print(f"    Extracted: {standardized_event['title']}")

                    except Exception as e:
                        print(f"    Error scraping event {event_url}: {e}")
                        continue

            except Exception as e:
                print(f"    Error scraping Hyperreal calendar {calendar_url}: {e}")
                continue

        print(f"Successfully scraped {len(all_events)} Hyperreal events total")
        return all_events
