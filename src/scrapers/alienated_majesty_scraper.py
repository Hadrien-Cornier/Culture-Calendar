"""
Alienated Majesty Books scraper using pyppeteer for JS rendering + LLM/BeautifulSoup extraction
"""

import asyncio
import os
import re
import sys
from typing import Dict, List, Optional

from bs4 import BeautifulSoup
from pyppeteer import launch

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

    async def _scrape_with_pyppeteer_async(self, url: str) -> List[Dict]:
        """Use pyppeteer to render JavaScript and extract book club events"""
        browser = None
        try:
            print(f"  Launching browser for {url}")
            browser = await launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-web-security",
                    "--disable-features=VizDisplayCompositor",
                ],
            )

            page = await browser.newPage()

            # Set user agent
            await page.setUserAgent(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )

            print(f"  Navigating to {url}")
            await page.goto(url, {"waitUntil": "networkidle0", "timeout": 30000})

            # Wait for content to load
            print("  Waiting for content to load...")
            await asyncio.sleep(3)

            # Get the rendered HTML
            html_content = await page.content()
            print(f"  Got {len(html_content)} characters of HTML")

            # Extract events using both BeautifulSoup and LLM
            events = self._extract_book_club_events(html_content, url)

            return events

        except Exception as e:
            print(f"  Pyppeteer error: {e}")
            return []
        finally:
            if browser:
                await browser.close()

    def _scrape_with_pyppeteer(self, url: str) -> List[Dict]:
        """Synchronous wrapper for pyppeteer scraping"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(self._scrape_with_pyppeteer_async(url))

            # Wait for all pending tasks to complete before closing the loop
            pending = asyncio.all_tasks(loop)
            if pending:
                print(f"  Waiting for {len(pending)} pending tasks to complete...")
                # Cancel all remaining tasks
                for task in pending:
                    if not task.done():
                        task.cancel()

                # Wait for cancellation to complete
                try:
                    loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
                except Exception:
                    pass

            return result
        except Exception as e:
            print(f"  Pyppeteer wrapper error: {e}")
            return []
        finally:
            try:
                loop.close()
            except BaseException:
                pass

    def _extract_book_club_events(self, html_content: str, url: str) -> List[Dict]:
        """Extract book club events from rendered HTML using LLM"""
        events = []

        try:
            # Use LLM extraction for dynamic content
            print("  Using LLM extraction...")
            events = self._extract_with_llm(html_content, url)

            if events:
                print(f"  ✓ LLM extracted {len(events)} events")
                return events
            else:
                print("  LLM extraction returned no events")

        except Exception as e:
            print(f"  LLM extraction error: {e}")

        return events

    def _extract_with_beautifulsoup(self, soup: BeautifulSoup, url: str) -> List[Dict]:
        """Extract events using BeautifulSoup pattern matching"""
        events = []

        try:
            # Look for book club h2 headers
            book_club_headers = soup.find_all("h2", class_="bm-txt-1")

            for header in book_club_headers:
                series_name = header.get_text().strip()

                # Skip if not a book club series we recognize
                if series_name not in [
                    "NYRB Book Club",
                    "Subculture Lit",
                    "A Season Of",
                    "Voyage Out",
                    "Apricot Trees Exist",
                ]:
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
        """Extract content while preserving section separators between book clubs"""
        try:
            # Look for book club headers to identify sections
            book_club_headers = main_content.find_all("h2", class_="bm-txt-1")

            if not book_club_headers:
                # Fallback to regular text extraction
                return main_content.get_text(separator=" ", strip=True)

            sections = []

            # Process each book club section
            for i, header in enumerate(book_club_headers):

                # Find the container for this section
                container = header.find_parent()
                while container and not container.find_all("p"):
                    container = container.find_parent()

                if container:
                    # Extract text from this section
                    section_text = container.get_text(separator=" ", strip=True)
                    sections.append(section_text)

            # Join sections with clear separators
            if sections:
                separator = "\n\n" + "=" * 50 + "\n\n"
                return separator.join(sections)
            else:
                # Fallback to regular extraction
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
