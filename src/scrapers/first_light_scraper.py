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

    def __init__(self, config=None, venue_key="first_light"):
        super().__init__(
            base_url="https://www.firstlightaustin.com",
            venue_name="FirstLight",
            venue_key=venue_key,
            config=config,
        )

    def get_target_urls(self) -> List[str]:
        """Return list of URLs to scrape"""
        return [
            f"{self.base_url}/book-club",
            f"{self.base_url}/events",
            # Main events page - individual pages will be scraped separately
        ]

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
        """Parse book club date like 'Friday, June 27th' or 'April 13' into YYYY-MM-DD.

        Year inference: today is the anchor. If the parsed month is < current
        month, the event is next year; otherwise it's this year. This is the
        same dynamic-guidance rule the AlienatedMajesty scraper config uses.
        """
        try:
            cleaned_date = date_str.strip().rstrip(",").strip()
            cleaned_date = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", cleaned_date)

            today = datetime.now()
            for fmt in ("%Y %A, %B %d", "%Y %B %d"):
                try:
                    base = cleaned_date.split(", ")[-1] if fmt == "%Y %B %d" else cleaned_date
                    date_obj = datetime.strptime(f"{today.year} {base}", fmt)
                    if date_obj.month < today.month:
                        date_obj = date_obj.replace(year=today.year + 1)
                    return date_obj.strftime("%Y-%m-%d")
                except ValueError:
                    continue
            print(f"Error parsing book club date '{date_str}': unrecognized format")
            return None
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
                    "dates": [date_str],  # Use dates array
                    "times": [time_str],  # Use times array
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

                # Extract book title + author from a "<Month> selection: <Book> by <Author>"
                # span. The first " by " in the full description is usually
                # "Hosted by …", so we MUST anchor on "selection:" before splitting.
                book_title = None
                author = None
                sel_match = re.search(
                    r"[A-Z][a-z]+\s+selection:\s*(.+?)(?:\s*\.?\s*Meeting|\s*\.?\s*Meets|$)",
                    description_text,
                    flags=re.DOTALL,
                )
                if sel_match:
                    selection_text = sel_match.group(1).strip().rstrip(".")
                    by_split = re.split(r"\s+by\s+", selection_text, maxsplit=1)
                    if len(by_split) == 2:
                        book_title = by_split[0].strip()
                        # Strip a trailing 'Meeting' fragment that crept in when there's no
                        # period between author name and the 'Meeting…' sentence.
                        author = re.sub(r"\s*Meeting\s+the\b.*$", "", by_split[1]).strip()
                    else:
                        book_title = selection_text

                # Fallback: anchor link in the description
                if not book_title:
                    book_link = description_elem.find("a")
                    if book_link:
                        book_title = book_link.get_text().strip()

                # Extract meeting date and time. The site uses two phrasings:
                #   old:  "Meets <date> at <H>(:<MM>)?<ampm>"
                #   new:  "Meeting the <ordinal> <day> of the month, <Month> <D>, at <H>(:<MM>)?\s*<ampm>"
                #         e.g. "Meeting the second Monday of the month, April 13, at 7 p.m."
                date_str = None
                time_str = None

                meeting_match = re.search(
                    r"Meeting\s+the\s+(?:first|second|third|fourth|fifth|last)\s+\w+\s+of\s+the\s+month,\s+"
                    r"([A-Za-z]+\s+\d{1,2})\s*,?\s*at\s+(\d+)(?::(\d{2}))?\s*([ap]\.?m)",
                    description_text,
                    flags=re.IGNORECASE,
                )
                if not meeting_match:
                    meeting_match = re.search(
                        r"Meets\s+([^.]+?)\s+at\s+(\d+)(?::(\d{2}))?\s*([ap]\.?m)",
                        description_text,
                        flags=re.IGNORECASE,
                    )

                if meeting_match:
                    date_part = meeting_match.group(1).strip()
                    hour = meeting_match.group(2)
                    minutes = meeting_match.group(3) or "00"
                    ampm = meeting_match.group(4).replace(".", "").upper()
                    date_str = self.parse_book_club_date(date_part)
                    time_str = f"{hour}:{minutes} {ampm}"

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
                        "type": "book_club",
                        "author": author,
                        "book": book_title,
                        "dates": [date_str],
                        "times": [time_str],
                        "venue": "First Light Books",
                        "host": host,
                        "series": full_club_name,
                        "description": main_description,
                        "rsvp_url": None,
                        "url": url,
                    }
                    events.append(event)

            except Exception as e:
                print(f"Error parsing book club item: {e}")
                continue

        return events

    def scrape_events(self) -> List[Dict]:
        """
        Adhoc scraping implementation for First Light Austin.
        Falls back to static data if scraping fails.
        """
        try:
            all_events = []

            # Try to scrape book club events
            book_club_url = f"{self.base_url}/book-club"
            response = self.session.get(book_club_url, timeout=15)

            if response.status_code == 200:
                book_club_events = self.extract_book_club_events(
                    response.text, book_club_url
                )
                all_events.extend(book_club_events)

            # Note: General events scraping not implemented yet
            # Focus on book club events for now

            if all_events:
                print(f"Scraped {len(all_events)} events from First Light Austin")
                return all_events

        except Exception as e:
            print(f"First Light Austin scraping failed: {e}")

        # Return empty list if scraping fails
        print("First Light Austin scraping failed, returning empty list")
        return []

    def get_event_details(self, event: Dict) -> Dict:
        """Get additional details for a book club event - returns empty dict since details are already complete"""
        return {}
