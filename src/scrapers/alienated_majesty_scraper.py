"""
Alienated Majesty Books scraper.

Uses Playwright (sync API) for the JS-rendered book-clubs page, then a
BeautifulSoup + LLM pass to extract per-book-club events. Replaced
pyppeteer in 2026-04 because pyppeteer's bundled Chromium crashes on
Python 3.13.
"""

import os
import re
import sys
from datetime import datetime
from typing import Dict, List, Optional

from bs4 import BeautifulSoup

from src.base_scraper import BaseScraper

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))


class AlienatedMajestyBooksScraper(BaseScraper):
    """Scraper for Alienated Majesty Books events using pyppeteer for JS rendering"""

    def __init__(self, config=None, venue_key="alienated_majesty"):
        super().__init__(
            base_url="https://www.alienatedmajestybooks.com",
            venue_name="AlienatedMajesty",
            venue_key=venue_key,
            config=config,
        )

    def get_target_urls(self) -> List[str]:
        """Return list of URLs to scrape"""
        return [f"{self.base_url}/book-clubs"]

    def _render_with_playwright(self, url: str) -> str:
        """Render the URL with Playwright Chromium and return the post-JS HTML.

        Returns an empty string on failure so callers can fall back without
        raising. Playwright's sync API runs in this thread; it manages its own
        event loop, so this is safe to call inside MultiVenueScraper's loop.
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            print("  playwright not installed; cannot render JS-heavy page")
            return ""

        try:
            print(f"  Launching Playwright for {url}")
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                try:
                    page = browser.new_page(
                        user_agent=(
                            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/120.0.0.0 Safari/537.36"
                        )
                    )
                    page.goto(url, wait_until="networkidle", timeout=30000)
                    html_content = page.content()
                    print(f"  Got {len(html_content)} chars from Playwright")
                    return html_content
                finally:
                    browser.close()
        except Exception as e:
            print(f"  Playwright error: {e}")
            return ""

    def _scrape_with_pyppeteer(self, url: str) -> List[Dict]:
        """Backwards-compatible name; routes to Playwright now."""
        html_content = self._render_with_playwright(url)
        if not html_content:
            return []
        return self._extract_book_club_events(html_content, url)

    def _extract_book_club_events(self, html_content: str, url: str) -> List[Dict]:
        """Extract book club events from rendered HTML.

        Strategy: parse 'UPCOMING CLUBS' / 'UPCOMING SCREENINGS' sections
        directly from BeautifulSoup. The page lists each upcoming meeting as
        '<Weekday>, <Month> <Day> - <Book> by <Author>' under the series
        header. LLM extraction is a fallback.
        """
        events: List[Dict] = []
        soup = BeautifulSoup(html_content, "html.parser")
        try:
            events = self._extract_upcoming_meetings(soup, url)
            if events:
                print(f"  ✓ Parsed {len(events)} upcoming meetings from HTML")
                return events
        except Exception as e:
            print(f"  Direct HTML extraction error: {e}")

        try:
            print("  Falling back to LLM extraction…")
            events = self._extract_with_llm(html_content, url)
            if events:
                print(f"  ✓ LLM extracted {len(events)} events")
                return events
        except Exception as e:
            print(f"  LLM extraction error: {e}")

        print("  No events extracted from Alienated Majesty")
        return events

    def _extract_upcoming_meetings(self, soup: BeautifulSoup, url: str) -> List[Dict]:
        """Parse 'UPCOMING CLUBS / UPCOMING SCREENINGS' blocks into events.

        Walk every h2 in document order, tracking the current series name
        (h2.bm-txt-1 or h2.bm-txt-2). When an UPCOMING h2 (h2.bm-txt-0 with
        text 'UPCOMING …') is hit, parse the text from that h2 up to the next
        series h2 as that series' meetings. Each entry: '<Weekday>, <Mon> <D>
        - <Book> by <Author>'.
        """
        events: List[Dict] = []
        today = datetime.now()
        SERIES_CLASSES = {"bm-txt-1", "bm-txt-2"}
        all_h2 = soup.find_all("h2")
        current_series: Optional[str] = None

        entry_re = re.compile(
            r"(Sunday|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday)"
            r",\s*([A-Za-z]+\.?)\s+(\d{1,2})"
            r"\s*[-–—]\s*(.+?)(?=(?:Sunday|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday),|\Z)",
            re.IGNORECASE | re.DOTALL,
        )

        for idx, header in enumerate(all_h2):
            classes = set(header.get("class") or [])
            text = header.get_text().strip()

            if classes & SERIES_CLASSES:
                current_series = text
                continue

            if not text.upper().startswith("UPCOMING"):
                continue
            if not current_series:
                continue

            # Collect text after this h2 up to the next series h2 (or end).
            next_series = None
            for j in range(idx + 1, len(all_h2)):
                if set(all_h2[j].get("class") or []) & SERIES_CLASSES:
                    next_series = all_h2[j]
                    break

            collected: list[str] = []
            for sib in header.next_elements:
                if sib is next_series:
                    break
                if hasattr(sib, "name") and sib is not header:
                    pass  # tag — text already captured by string nodes
                if isinstance(sib, str):
                    s = sib.strip()
                    if s:
                        collected.append(s)
            tail = " ".join(collected)
            # Trim everything after a 'View all' / 'View more' marker that the
            # site appends to each section.
            tail = re.split(r"\bView\s+all\b|\bView\s+more\b", tail, maxsplit=1)[0]

            for m in entry_re.finditer(tail):
                month_token = m.group(2).rstrip(".")
                day = int(m.group(3))
                title_part = m.group(4).strip().rstrip(".").rstrip()
                month = self._month_number(month_token)
                if not month:
                    continue
                year = today.year if month >= today.month else today.year + 1
                date_iso = f"{year:04d}-{month:02d}-{day:02d}"

                book_title, author = self._split_title_by_author(title_part)
                if not book_title:
                    continue
                events.append({
                    "title": f"{current_series} - {book_title}",
                    "type": "book_club",
                    "series": current_series,
                    "book": book_title,
                    "author": author,
                    "dates": [date_iso],
                    "times": ["7:00 PM"],
                    "venue": "Alienated Majesty Books",
                    "url": url,
                    "description": (
                        f"{current_series} discussion of {book_title}"
                        + (f" by {author}" if author else "")
                        + ". Hosted at Alienated Majesty Books, 613 W 29th St, Austin TX."
                    ),
                })
        return events

    @staticmethod
    def _month_number(token: str) -> Optional[int]:
        months = {
            "jan": 1, "january": 1,
            "feb": 2, "february": 2,
            "mar": 3, "march": 3,
            "apr": 4, "april": 4,
            "may": 5,
            "jun": 6, "june": 6,
            "jul": 7, "july": 7,
            "aug": 8, "august": 8,
            "sep": 9, "sept": 9, "september": 9,
            "oct": 10, "october": 10,
            "nov": 11, "november": 11,
            "dec": 12, "december": 12,
        }
        return months.get(token.lower())

    @staticmethod
    def _split_title_by_author(text: str) -> tuple[Optional[str], Optional[str]]:
        """Split 'Book Title by Author Name' on the LAST ' by ' occurrence."""
        parts = re.split(r"\s+by\s+", text)
        if len(parts) >= 2:
            book = " by ".join(parts[:-1]).strip()
            author = parts[-1].strip()
            return (book or None), (author or None)
        return text.strip() or None, None

    def _extract_with_beautifulsoup(self, soup: BeautifulSoup, url: str) -> List[Dict]:
        """Extract events using BeautifulSoup pattern matching"""
        events = []

        try:
            book_club_headers = soup.find_all(
                "h2", class_=lambda c: c in {"bm-txt-1", "bm-txt-2"}
            )

            recognised = {
                "NYRB Book Club",
                "Subculture Lit",
                "A Season Of",
                "Voyage Out",
                "Apricot Trees Exist",
                "Art Sex Magic",
                "Paper Cuts @ AFS Cinema",
            }
            for header in book_club_headers:
                series_name = header.get_text().strip()
                if series_name not in recognised:
                    continue

                # Find the parent container with the book club content
                container = header.find_parent()
                while container and not container.find_all("p"):
                    container = container.find_parent()

                if not container:
                    continue

                # Extract all text content from the container
                text_content = container.get_text()

                # Parse meeting information from the text
                meeting_events = self._parse_series_text(text_content, series_name, url)
                events.extend(meeting_events)

            return events

        except Exception as e:
            print(f"  BeautifulSoup extraction error: {e}")
            return []

    def _extract_with_llm(self, html_content: str, url: str) -> List[Dict]:
        """Extract events using LLM with enhanced prompting"""
        try:
            # First, let's simplify the HTML content for better LLM processing
            # Extract just the main content section
            soup = BeautifulSoup(html_content, "html.parser")

            # Find the main content area
            main_content = soup.find("main")
            if main_content:
                # Get text content from main area with section separators preserved
                simplified_content = self._extract_content_with_separators(main_content)
            else:
                # Fallback to full text but truncated
                simplified_content = soup.get_text(separator=" ", strip=True)

            # Truncate if too long
            if len(simplified_content) > 6000:
                simplified_content = simplified_content[:6000] + "..."

            print(
                f"  Using simplified content with separators ({len(simplified_content)} chars)"
            )

            from datetime import datetime

            # Get current date information
            now = datetime.now()
            current_year = now.year
            current_month = now.month
            current_month_name = now.strftime("%B")

            # Generate dynamic date guidance
            date_guidance = f"IMPORTANT: We are currently in {current_month_name} {current_year}. All book club events are future events. For dates without years: use {current_year} for {current_month_name}-December, use {current_year + 1} for January-{now.strftime('%B')}."

            # Get extraction schema from ConfigLoader (handles all overrides)
            if not self.config:
                raise ValueError("Configuration is required for scraper operation")

            # Get complete extraction schema with all overrides applied
            extraction_schema = self.config.get_extraction_schema(self.venue_key)

            # Build items schema for LLM extraction
            items_schema = {}
            for field_name, field_def in extraction_schema["fields"].items():
                field_schema = {
                    "type": field_def.get("type", "string"),
                    "required": field_def.get("required", False),
                    "description": field_def.get("description", ""),
                }

                # Handle dynamic date guidance
                if field_name == "dates" and field_def.get("dynamic_guidance"):
                    # Replace YYYY placeholder and add runtime date guidance
                    field_schema["description"] = field_schema["description"].replace(
                        "YYYY", str(current_year)
                    )
                    field_schema["description"] += f" {date_guidance}"

                items_schema[field_name] = field_schema

            # Get batch description and add dynamic date guidance
            batch_description = extraction_schema.get(
                "batch_description", "List of events extracted from the webpage."
            )
            if date_guidance:
                batch_description = f"{batch_description} {date_guidance}"

            schema = {
                "events": {
                    "type": "array",
                    "description": batch_description,
                    "items": items_schema,
                }
            }

            # Enhanced extraction with simplified content
            extraction_result = self.llm_service.extract_data(
                content=simplified_content, schema=schema, url=url, content_type="text"
            )

            print(f"  LLM service returned: success={extraction_result.get('success')}")
            if not extraction_result.get("success"):
                print(f"  Error: {extraction_result.get( 'error','Unknown error')}")

            if extraction_result.get("success", False):
                data = extraction_result.get("data", {})
                events = data.get("events", [])

                print(f"  Raw events from LLM: {len(events)}")

                # Debug: show what fields the LLM is actually returning
                if events:
                    print(f"  Sample event fields: {list(events[0].keys())}")
                    print(f"  Raw LLM event: {events[0]}")

                # Post-process events to ensure proper formatting
                processed_events = []

                for event in events:
                    # Apply default values from configuration
                    if self.config:
                        mapped_event = self.config.apply_default_values(
                            event, self.venue_key
                        )
                    else:
                        mapped_event = event

                    # Debug: show corrected event after mapping
                    if len(processed_events) == 0:  # Only show first event
                        print(f"  Corrected event: {mapped_event}")

                    # Ensure URL is set (this is runtime data, not config)
                    if not mapped_event.get("url"):
                        mapped_event["url"] = url

                    # Set event type based on venue's assumed category from config
                    mapped_event["type"] = (
                        self.config.get_assumed_event_category(self.venue_key)
                        if self.config
                        else None
                    )
                    processed_events.append(mapped_event)

                return processed_events

        except Exception as e:
            print(f"  LLM extraction error: {e}")
            import traceback

            traceback.print_exc()

        return []

    def _extract_content_with_separators(self, main_content) -> str:
        """Extract content while preserving section separators between book clubs.

        Site layout migrated in 2026: most book-club series headers are now
        h2.bm-txt-2 (only legacy 'Voyage Out' / 'Apricot Trees Exist' / new
        'Art Sex Magic' still use bm-txt-1). Match either class.
        """
        try:
            book_club_headers = main_content.find_all(
                "h2", class_=lambda c: c in {"bm-txt-1", "bm-txt-2"}
            )

            if not book_club_headers:
                return main_content.get_text(separator=" ", strip=True)

            sections = []
            for header in book_club_headers:
                container = header.find_parent()
                while container and not container.find_all("p"):
                    container = container.find_parent()
                if container:
                    sections.append(container.get_text(separator=" ", strip=True))

            if sections:
                separator = "\n\n" + "=" * 50 + "\n\n"
                return separator.join(sections)
            return main_content.get_text(separator=" ", strip=True)

        except Exception as e:
            print(f"  Error extracting content with separators: {e}")
            # Fallback to regular extraction
            return main_content.get_text(separator=" ", strip=True)

    def _parse_series_text(
        self, text_content: str, series_name: str, url: str
    ) -> List[Dict]:
        """Parse series text content to extract all meeting events"""
        events = []

        try:
            # Find all meeting lines with day of week, month, and date
            meeting_pattern = r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s*(\w+)\s*(\d+)\s*—\s*(.+?)\s*by\s+(.+?)(?=(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)|$)"
            meetings = re.findall(
                meeting_pattern, text_content, re.IGNORECASE | re.DOTALL
            )

            for day_name, month_name, day_num, book_title, author in meetings:
                # Clean up book title and author
                book_title = re.sub(
                    r"<[^>]+>", "", book_title
                ).strip()  # Remove HTML tags
                book_title = book_title.strip().strip('"').strip("'").strip()

                author = re.sub(r"<[^>]+>", "", author).strip()  # Remove HTML tags
                author = author.strip()

                # Remove any trailing text after author (like publisher info)
                author = re.split(r"\s*\(", author)[0].strip()

                # Convert to proper date format
                date_str = self._convert_to_date_format(month_name, day_num)
                if not date_str:
                    continue

                # Determine time and other details based on series
                time_str, host, description = self._get_series_details(series_name)

                event = {
                    "title": f"{series_name} - {book_title}",
                    "book": book_title,
                    "author": author,
                    "dates": [date_str],  # Use dates array
                    "times": [time_str],  # Use times array
                    "venue": "Alienated Majesty Books",
                    "host": host,
                    "description": description,
                    "series": series_name,
                    "url": url,
                }
                events.append(event)

        except Exception as e:
            print(f"  Error parsing series text for '{series_name}': {e}")

        return events

    def _parse_meeting_text(
        self, meeting_text: str, series_name: str, url: str
    ) -> Optional[Dict]:
        """Parse individual meeting text to extract event details (legacy method)"""
        try:
            text = str(meeting_text).strip()

            # Skip if not a meeting line
            if not re.search(
                r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)",
                text,
                re.IGNORECASE,
            ):
                return None

            # Extract date pattern
            date_match = re.search(r"(\w+),\s*(\w+)\s*(\d+)", text)
            if not date_match:
                return None

            day_name, month_name, day_num = date_match.groups()

            # Extract book and author
            book_match = re.search(r"—\s*(.+?)\s*by\s+(.+?)(?:\s*\(|$)", text)
            if not book_match:
                return None

            book_title, author = book_match.groups()
            book_title = book_title.strip().strip('"').strip("'")
            author = author.strip()

            # Convert to proper date format
            date_str = self._convert_to_date_format(month_name, day_num)
            if not date_str:
                return None

            # Determine time and other details based on series
            time_str, host, description = self._get_series_details(series_name)

            return {
                "title": f"{series_name} - {book_title}",
                "book": book_title,
                "author": author,
                "date": date_str,
                "time": time_str,
                "venue": "Alienated Majesty Books",
                "type": "book_club",
                "host": host,
                "description": description,
                "series": series_name,
                "url": url,
            }

        except Exception as e:
            print(f"  Error parsing meeting text '{meeting_text}': {e}")
            return None

    def _convert_to_date_format(self, month_name: str, day_num: str) -> Optional[str]:
        """Convert month name and day to YYYY-MM-DD format with smart year detection"""
        try:
            from datetime import datetime

            month_map = {
                "january": 1,
                "february": 2,
                "march": 3,
                "april": 4,
                "may": 5,
                "june": 6,
                "july": 7,
                "august": 8,
                "september": 9,
                "october": 10,
                "november": 11,
                "december": 12,
            }

            month_num = month_map.get(month_name.lower())
            if not month_num:
                return None

            day = int(day_num)

            # Get current date
            now = datetime.now()
            current_year = now.year
            current_month = now.month

            # Determine the correct year for the event
            if month_num >= current_month:
                # If the event month is >= current month, it's likely this year
                year = current_year
            else:
                # If the event month is < current month, it's likely next year
                year = current_year + 1

            return f"{year:04d}-{month_num:02d}-{day:02d}"

        except BaseException:
            return None

    def _get_series_details(self, series_name: str) -> tuple:
        """Get time, host, and description for each series with full descriptions"""
        series_info = {
            "NYRB Book Club": (
                "11:00 AM",
                "Austin NYRB Book Club",
                "Only the (NYRB) Classics. Meets the 1st Saturday of every month at 11am. Run by the Austin NYRB Book Club.",
            ),
            "Subculture Lit": (
                "3:00 PM",
                "East Austin Writing Project",
                "Small presses, experimental and transgressive writers and work. Meets the 2nd Sunday of every month at 3pm. Run by East Austin Writing Project.",
            ),
            "A Season Of": (
                "11:00 AM",
                "Austin NYRB Book Club",
                "Reading a single author or title for a season. Meets the 3rd Saturday of every month at 11am. Run by the Austin NYRB Book Club.",
            ),
            "Voyage Out": (
                "5:00 PM",
                None,
                "A regional reading series. Meets the 3rd Sunday of every month at 5pm.",
            ),
            "Apricot Trees Exist": (
                "3:00 PM",
                None,
                "Reading poems for generative inspiration. Meets the 4th Sunday of every month at 3pm.",
            ),
        }

        return series_info.get(series_name, ("7:00 PM", None, "Book club meeting"))

    def scrape_events(self) -> List[Dict]:
        """Scrape book club events from Alienated Majesty Books website"""
        print("Loading Alienated Majesty Books club...")
        events = []

        for url in self.get_target_urls():
            try:
                # Use pyppeteer for JavaScript rendering
                events = self._scrape_with_pyppeteer(url)
                if events:
                    break
            except Exception as e:
                print(f"  Error scraping {url}: {e}")

        print(f"Scraped {len(events)} events from Alienated Majesty")
        return events

    def get_event_details(self, event: Dict) -> Dict:
        """Get additional details for a book club event - returns empty dict since details are already complete"""
        return {}
