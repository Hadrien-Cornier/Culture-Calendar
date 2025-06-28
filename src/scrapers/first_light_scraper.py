"""
First Light Austin events and book club scraper using HTML parsing
"""

import re
from datetime import datetime
from typing import Dict, List

from bs4 import BeautifulSoup

from src.base_scraper import BaseScraper


class FirstLightAustinScraper(BaseScraper):
    """Scraper for First Light Austin events and book club events"""

    def __init__(self):
        super().__init__(
            base_url="https://www.firstlightaustin.com", venue_name="FirstLight"
        )

    def get_target_urls(self) -> List[str]:
        """Return list of URLs to scrape"""
        return [
            f"{self.base_url}/book-club",
            f"{self.base_url}/events",
            # Main events page - individual pages will be scraped separately
        ]

    def get_data_schema(self) -> Dict:
        """Return the expected data schema for events and book clubs"""
        return {
            "title": {
                "type": "string",
                "required": True,
                "description": "Event title or book club name",
            },
            "author": {
                "type": "string",
                "required": False,
                "description": "Author name",
            },
            "book": {
                "type": "string",
                "required": False,
                "description": "Book title if applicable",
            },
            "date": {
                "type": "string",
                "required": True,
                "description": "Event date in YYYY-MM-DD format",
            },
            "time": {
                "type": "string",
                "required": True,
                "description": 'Event time (e.g., "7:30 PM")',
            },
            "venue": {"type": "string", "required": False, "description": "Venue name"},
            "host": {
                "type": "string",
                "required": False,
                "description": "Host or facilitator name",
            },
            "description": {
                "type": "string",
                "required": False,
                "description": "Event description",
            },
        }

    def get_fallback_data(self) -> List[Dict]:
        """Return empty list - we only want real data"""
        return []

    def parse_date_time(self, date_time_str):
        """Parse date/time string like '6/30/25 7:00 pm' into separate date and time"""
        try:
            # Handle formats like "6/30/25 7:00 pm"
            parts = date_time_str.strip().split(" ")
            if len(parts) >= 2:
                date_part = parts[0]
                time_part = " ".join(parts[1:])

                # Parse date (M/D/YY format)
                month, day, year = date_part.split("/")
                if len(year) == 2:
                    year = "20" + year

                formatted_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"

                # Format time
                time_formatted = time_part.upper().replace(" ", " ")

                return formatted_date, time_formatted
        except Exception as e:
            print(f"Error parsing date/time '{date_time_str}': {e}")
            return None, None

    def parse_book_club_date(self, date_str):
        """Parse book club date strings like 'Friday, June 27th' into YYYY-MM-DD format"""
        try:
            # Remove 'st', 'nd', 'rd', 'th' from day
            cleaned_date = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", date_str)

            # Assume 2025 since these are future events (adjust as needed)
            current_year = datetime.now().year
            future_year = current_year + 1 if datetime.now().month > 6 else current_year

            # Parse the date (assuming future year since these are future
            # events)
            try:
                date_obj = datetime.strptime(
                    f"{future_year} {cleaned_date}", "%Y %A, %B %d"
                )
            except ValueError:
                # If that fails, try without the day of week
                date_obj = datetime.strptime(
                    f"{future_year} {cleaned_date.split(', ')[-1]}", "%Y %B %d"
                )

            return date_obj.strftime("%Y-%m-%d")
        except Exception as e:
            print(f"Error parsing book club date '{date_str}': {e}")
            return None

    def extract_author_events(self, html_content, url):
        """Extract author events from individual event page HTML"""
        soup = BeautifulSoup(html_content, "html.parser")

        # Find the story content section
        story_content = soup.find("div", class_="story-content")

        # Extract date/time from subtitle within story content
        date_str, time_str = None, None
        if story_content:
            date_time_elem = story_content.find("div", class_="subtitle")
            if date_time_elem:
                date_str, time_str = self.parse_date_time(
                    date_time_elem.get_text().strip()
                )
        else:
            # If no story-content, try finding subtitle directly
            date_time_elems = soup.find_all("div", class_="subtitle")
            for elem in date_time_elems:
                text = elem.get_text().strip()
                if "/" in text and any(x in text.lower() for x in ["pm", "am"]):
                    date_str, time_str = self.parse_date_time(text)
                    break

        # Extract title from div with class 'h2 article'
        title_elem = soup.find("div", class_="h2 article")
        title = title_elem.get_text().strip() if title_elem else None

        # Extract author from title (usually "Author Name: Book Title" format)
        author = None
        book = None
        if title and ":" in title:
            parts = title.split(":", 1)
            author = parts[0].strip()
            if len(parts) > 1:
                # Book title might be in the second part or in the description
                potential_book = parts[1].strip()
                if potential_book and not potential_book.startswith("The "):
                    book = potential_book

        # Extract description from rich text
        description_elem = soup.find("div", class_="body-text article w-richtext")
        description = None
        if description_elem:
            # Get text content and clean it up
            description = description_elem.get_text().strip()
            # Look for book titles in description (usually in caps or
            # emphasized)
            if not book:
                # Look for patterns like "THE 5 TYPES OF WEALTH" in all caps
                book_match = re.search(
                    r"THE\s+[A-Z0-9\s]+?(?:\s+will\s+teach|\.|,|\s+was\s+an\s+instant|\s+and)",
                    description,
                )
                if book_match:
                    book = book_match.group(0).strip()
                    # Clean up the match to remove trailing words
                    book = re.sub(
                        r"\s+(will\s+teach|and|was\s+an\s+instant).*$", "", book
                    )
                else:
                    # Try finding patterns in quotes or after "his book" or
                    # "her book"
                    quote_match = re.search(
                        r"(?:his|her|their)\s+(?:debut\s+)?book,?\s+([A-Z][A-Z\s:]+?)[\.,]",
                        description,
                    )
                    if quote_match:
                        book = quote_match.group(1).strip()

        # Extract RSVP URL
        rsvp_elem = soup.find("a", class_="button _3 tickets w-button")
        rsvp_url = rsvp_elem.get("href") if rsvp_elem else None

        # Determine venue from description or default
        venue = "First Light Books"  # Default venue
        if description:
            if (
                "Central branch of the Austin Public Library" in description
                or "Austin Public Library" in description
            ):
                venue = "Austin Public Library Central Branch"

        # Only return event if we have the essential data
        if title and date_str and time_str:
            return [
                {
                    "title": title,
                    "author": author,
                    "book": book,
                    "date": date_str,
                    "time": time_str,
                    "venue": venue,
                    "description": description,
                    "rsvp_url": rsvp_url,
                    "url": url,
                }
            ]

        return []

    def extract_book_club_events(self, html_content, url):
        """Extract book club events from the book club page HTML by parsing the actual content"""
        soup = BeautifulSoup(html_content, "html.parser")
        events = []

        # Find all book club sections - they are in collection-item-8 divs
        book_club_items = soup.find_all("div", class_="collection-item-8")

        for item in book_club_items:
            try:
                # Extract club name from h1 element
                club_name_elem = item.find(
                    "div", class_="h1 smaller centered book-club"
                )
                if not club_name_elem:
                    continue

                club_short_name = club_name_elem.get_text().strip()

                # Extract description and details from rich text
                description_elem = item.find(
                    "div", class_="body-text center book-club w-richtext"
                )
                if not description_elem:
                    continue

                description_text = description_elem.get_text().strip()
                str(description_elem)

                # Extract full club name from the bold text in description
                full_club_name_match = re.search(
                    r"The\s+([^.]+?Book\s+Club)", description_text
                )
                # Remove "The" prefix for consistency with test expectations
                if full_club_name_match:
                    full_club_name = full_club_name_match.group(
                        1
                    )  # Get the part without "The"
                else:
                    full_club_name = f"{club_short_name} Book Club"

                # Extract book title and author from links and text
                # Look for patterns like "selection: [Book Title] by Author"
                book_info_match = re.search(
                    r"selection:\s*([^b]+?)\s*by\s+([^.()]+?)(?:\s*\([^)]+\))?\.\s*Meets",
                    description_text,
                )

                book_title = None
                author = None

                if book_info_match:
                    book_title = book_info_match.group(1).strip()
                    author = book_info_match.group(2).strip()

                    # Clean up book title (remove extra text like month info)
                    book_title = re.sub(
                        r"^[A-Za-z]+/[A-Za-z]+\s+selection:\s*", "", book_title
                    )
                    book_title = re.sub(r"^\w+\s+selection:\s*", "", book_title)

                    # Remove any HTML artifacts or links
                    book_title = re.sub(r"<[^>]+>", "", book_title)

                # If we didn't find book/author in the expected pattern, try
                # link text
                if not book_title:
                    book_link = description_elem.find("a")
                    if book_link:
                        book_title = book_link.get_text().strip()
                        # Try to find author after "by" in the text
                        link_text = book_link.get_text()
                        remaining_text = description_text.split(link_text)[-1]
                        author_match = re.search(
                            r"\s*by\s+([^.()]+?)(?:\s*\([^)]+\))?\.\s*Meets",
                            remaining_text,
                        )
                        if author_match:
                            author = author_match.group(1).strip()

                # Extract meeting date and time
                # Look for patterns like "Meets Friday, June 27th at 7pm" or
                # "Meets Wednesday, July 30th at 7pm"
                meeting_match = re.search(
                    r"Meets\s+([^.]+?)\s+at\s+(\d+)(?::\d+)?\s*([ap]m)",
                    description_text,
                )

                date_str = None
                time_str = None

                if meeting_match:
                    date_part = meeting_match.group(1).strip()
                    hour = meeting_match.group(2)
                    ampm = meeting_match.group(3)

                    # Parse the date
                    date_str = self.parse_book_club_date(date_part)

                    # Format the time
                    time_str = f"{hour}:00 {ampm.upper()}"

                # Extract host information
                # Look for patterns like "Hosted by [Title] [Name]" and extract
                # just the name
                host_match = re.search(
                    r"Hosted\s+by\s+([^.]+?)(?:\.|$)", description_text
                )
                host = None
                if host_match:
                    host_text = host_match.group(1).strip()
                    # Extract just the person's name (typically the last 1-2 words)
                    # Look for patterns like "First Light [title] Name" or
                    # "Name"
                    name_match = re.search(
                        r"(?:First Light [^\.]+?\s+)([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
                        host_text,
                    )
                    if name_match:
                        host = name_match.group(1)
                    else:
                        # Fallback: take the last 1-2 words as the name
                        words = host_text.split()
                        if len(words) >= 2:
                            host = " ".join(words[-2:])  # Last two words
                        else:
                            host = words[-1] if words else None

                # Get the description up to the host information (excluding selection details)
                # Keep "The" prefix in descriptions (unlike titles)
                main_description = description_text.strip()

                # Find where host information ends and truncate there (before
                # selection details)
                host_end_match = re.search(r"(Hosted\s+by\s+[^.]+\.)", main_description)
                if host_end_match:
                    # Keep everything up to and including the host sentence
                    end_pos = host_end_match.end()
                    main_description = main_description[:end_pos]

                # Normalize smart quotes and apostrophes to regular ASCII characters
                # (but keep dashes as they are expected to remain Unicode)
                main_description = main_description.replace(
                    "\u2019", "'"
                )  # Smart apostrophe to regular
                main_description = main_description.replace(
                    "\u201c", '"'
                )  # Smart quote left to regular
                main_description = main_description.replace(
                    "\u201d", '"'
                )  # Smart quote right to regular

                # Only create event if we have essential data
                if full_club_name and book_title and date_str and time_str:
                    event = {
                        "title": f"{full_club_name} - {book_title}",
                        "author": author,
                        "book": book_title,
                        "date": date_str,
                        "time": time_str,
                        "venue": "First Light Books",
                        "host": host,
                        "series": full_club_name,
                        "description": main_description,
                        "rsvp_url": None,  # Book clubs don't seem to have specific RSVP URLs
                        "url": url,
                    }
                    events.append(event)

            except Exception as e:
                print(f"Error parsing book club item: {e}")
                continue

        return events
