"""
Hyperreal Movie Club scraper using Beautiful Soup extraction with LLM fallback.

This scraper:
1. Fetches the calendar page for the current month
2. Extracts all movie screening event URLs
3. For each event page, uses Beautiful Soup to extract fields defined in master_config.yaml
4. Falls back to LLM extraction if Beautiful Soup fails
5. Uses configuration-driven field extraction from movie template
"""

from datetime import datetime
from typing import Dict, List, Optional, Any
from bs4 import BeautifulSoup
import re

from src.base_scraper import BaseScraper
from src.schemas import MovieEventSchema


class HyperrealScraper(BaseScraper):
    """
    Scraper for Hyperreal Movie Club events.

    Fetches the calendar page for a specific month and extracts all event URLs,
    then visits each event page to get detailed information using configuration-driven
    field extraction.
    """

    def __init__(self, config=None, venue_key="hyperreal"):
        super().__init__(
            base_url="https://hyperrealfilm.club",
            venue_name="Hyperreal Movie Club",
            venue_key=venue_key,
            config=config,
        )

        # Load template fields from config if available
        self.template_fields = None
        self.required_fields = None
        self.field_defaults = None

        if self.config:
            # Get movie template from config
            template = self.config.get_template("movie")
            self.template_fields = template.get("fields", [])
            self.required_fields = template.get("required_on_publish", [])
            self.field_defaults = self.config.get_field_defaults()

            # Get venue-specific configuration
            self.venue_config = self.config.get_venue_policy(self.venue_key)

    def get_target_urls(self) -> List[str]:
        """Return the current month's calendar URL"""
        now = datetime.now()
        return [
            f"{self.base_url}/events?view=calendar&month={now.month:02d}-{now.year}"
        ]

    def get_data_schema(self) -> Dict:
        """Return the expected data schema for Hyperreal movie events"""
        if self.config:
            # Use config-driven schema
            return self.config.get_extraction_schema(self.venue_key, "movie")
        else:
            # Fallback to hardcoded schema
            return MovieEventSchema.get_schema()

    def get_fallback_data(self) -> List[Dict]:
        """Provide fallback event data when scraping fails"""
        # Return empty list - Hyperreal updates frequently,
        # so we shouldn't use static fallback data
        return []

    def _extract_raw_data_from_html(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract raw data from HTML using existing patterns"""
        raw_data = {}

        # Extract title from h1 tag
        title_elem = soup.find("h1")
        if title_elem:
            # Clean title - remove "at HYPERREAL FILM CLUB" suffix
            title = title_elem.get_text(strip=True)
            title = re.sub(
                r"\s+at\s+HYPERREAL\s+FILM\s+CLUB\s*$", "", title, flags=re.IGNORECASE
            )
            raw_data["title"] = title

        # Extract dates and times from structured HTML first, then fallback to list items
        dates = []
        times = []

        # First, try to extract start time from structured event time elements
        start_time_elem = soup.find("time", class_="event-time-12hr-start")
        if start_time_elem:
            start_time_text = start_time_elem.get_text(strip=True)
            # Clean unicode characters (e.g., thin space \u202f)
            cleaned_time = re.sub(r"[\u202f\u00a0]", " ", start_time_text).strip()
            times.append(cleaned_time)

        # Extract date from structured elements
        date_elem = soup.find("time", class_="event-date")
        if date_elem:
            datetime_attr = date_elem.get("datetime")
            if datetime_attr:
                dates.append(datetime_attr)

        # If no structured times found, fall back to parsing list items
        if not times:
            for li in soup.find_all("li"):
                text = li.get_text(strip=True)

                # Preprocess text to handle cases where year runs into time (e.g. "20259:30 PM")
                # Insert space before time patterns that follow 4 digits (likely a year)
                preprocessed_text = re.sub(
                    r"(\d{4})(\d{1,2}:\d{2}\s*[AP]M)", r"\1 \2", text
                )

                # Look for time pattern but only take the first one (start time)
                time_matches = re.findall(r"(\d{1,2}:\d{2}\s*[AP]M)", preprocessed_text)

                if time_matches:
                    # Only take the first time match to avoid capturing end times
                    first_time = time_matches[0]
                    # Clean unicode characters (e.g., thin space \u202f)
                    cleaned_time = re.sub(r"[\u202f\u00a0]", " ", first_time).strip()
                    times.append(cleaned_time)

        # If no structured dates found, fall back to parsing list items for dates
        if not dates:
            for li in soup.find_all("li"):
                text = li.get_text(strip=True)

                # Look for date pattern (e.g., "Monday, September 8, 2025")
                date_match = re.search(
                    r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+"
                    r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
                    r"(\d{1,2}),?\s+(\d{4})",
                    text,
                )
                if date_match:
                    month_names = {
                        "January": "01",
                        "February": "02",
                        "March": "03",
                        "April": "04",
                        "May": "05",
                        "June": "06",
                        "July": "07",
                        "August": "08",
                        "September": "09",
                        "October": "10",
                        "November": "11",
                        "December": "12",
                    }
                    month = month_names[date_match.group(2)]
                    day = date_match.group(3).zfill(2)
                    year = date_match.group(4)
                    dates.append(f"{year}-{month}-{day}")

        # Store dates and times (use arrays as per config)
        if dates:
            raw_data["dates"] = dates
        if times:
            # Clean unicode characters and validate times before storing
            cleaned_times = []
            for time_str in times:
                cleaned_time = re.sub(r"[\u202f\u00a0]", " ", time_str).strip()

                # Validate time format: hours should be 1-12 for 12-hour format
                if self._is_valid_time(cleaned_time):
                    cleaned_times.append(cleaned_time)
                else:
                    print(
                        f"WARNING: Invalid time extracted '{cleaned_time}' from '{time_str}' - skipping"
                    )

            raw_data["times"] = cleaned_times if cleaned_times else ["TBD"]
        else:
            raw_data["times"] = ["TBD"]

        # Extract description and additional movie metadata
        raw_data.update(
            self._extract_movie_metadata_from_description(
                soup, raw_data.get("title", "")
            )
        )

        return raw_data

    def _is_valid_time(self, time_str: str) -> bool:
        """
        Validate that a time string represents a reasonable 12-hour format time.

        Args:
            time_str: Time string like "9:30 PM" or "11:00 AM"

        Returns:
            True if valid, False otherwise
        """
        # Check basic format with regex
        match = re.match(
            r"^(\d{1,2}):(\d{2})\s*(AM|PM)$", time_str.strip(), re.IGNORECASE
        )
        if not match:
            return False

        hours, minutes, period = match.groups()
        hours = int(hours)
        minutes = int(minutes)

        # Validate hour range (1-12 for 12-hour format)
        if hours < 1 or hours > 12:
            return False

        # Validate minutes (0-59)
        if minutes < 0 or minutes > 59:
            return False

        return True

    def _extract_movie_metadata_from_description(
        self, soup: BeautifulSoup, title: str
    ) -> Dict[str, Any]:
        """Extract movie metadata from description content"""
        metadata = {}
        description = None
        content_texts = []

        # First, try to find "The vitals:" section
        for elem in soup.find_all(text=re.compile(r"The vitals:", re.IGNORECASE)):
            parent = elem.parent
            if parent:
                # Get the parent container and extract all text
                container = (
                    parent.parent if parent.name in ["strong", "b", "em"] else parent
                )
                if container:
                    # Get all text from this container and siblings
                    text_parts = []

                    # Start from the container with "The vitals:"
                    current = container
                    while current:
                        if current.name in ["p", "div"] or (
                            current.string and current.string.strip()
                        ):
                            text = current.get_text(separator=" ", strip=True)
                            if (
                                text
                                and not text.startswith("Earlier Event:")
                                and not text.startswith("Later Event:")
                            ):
                                text_parts.append(text)

                        # Move to next sibling
                        current = current.find_next_sibling()

                        # Stop if we hit navigation elements or event links
                        if current and (
                            "Earlier Event" in current.get_text()
                            or "Later Event" in current.get_text()
                            or "SEE YOU AT THE MOVIES" in current.get_text()
                        ):
                            break

                    if text_parts:
                        description = " ".join(text_parts)
                        break

        # Alternative approach: look for paragraphs with movie descriptions
        if not description:
            # Find paragraphs that look like movie descriptions
            for p in soup.find_all("p"):
                text = p.get_text(strip=True)
                # Look for paragraphs that mention the movie or contain descriptive text
                if len(text) > 100 and (
                    "film" in text.lower()
                    or "movie" in text.lower()
                    or "premiere" in text.lower()
                    or (title and title.lower() in text.lower())
                ):
                    content_texts.append(text)

            # Also check for any text containing "The vitals:"
            for elem in soup.find_all(text=re.compile(r"The vitals:")):
                parent = elem.parent
                while parent and parent.name not in ["body", "html"]:
                    text = parent.get_text(separator=" ", strip=True)
                    if text and len(text) > 50:
                        content_texts.append(text)
                        break
                    parent = parent.parent

            if content_texts:
                # Combine and clean the description
                description = " ".join(content_texts)

        # Clean up the description
        if description:
            # Remove duplicate spaces and clean up
            description = re.sub(r"\s+", " ", description)
            # Remove navigation text
            description = re.sub(r"(Earlier Event:|Later Event:).*", "", description)
            description = description.strip()
            metadata["description"] = description

            # Try to extract additional movie metadata from description
            # Look for director
            director_match = re.search(
                r"(?:directed by|director:|dir\.)\s+([^,\.]+)",
                description,
                re.IGNORECASE,
            )
            if director_match:
                metadata["director"] = director_match.group(1).strip()

            # Look for year
            year_match = re.search(r"\b(19\d{2}|20\d{2})\b", description)
            if year_match:
                metadata["release_year"] = int(year_match.group(1))

            # Look for runtime
            runtime_match = re.search(
                r"(\d{2,3})\s*(?:min|minutes)", description, re.IGNORECASE
            )
            if runtime_match:
                metadata["runtime_minutes"] = int(runtime_match.group(1))

            # Look for country
            country_match = re.search(
                r"(?:Country:|From)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)", description
            )
            if country_match:
                metadata["country"] = country_match.group(1).strip()

            # Look for language
            lang_match = re.search(
                r"(?:Language:|In)\s+(English|Spanish|French|German|Italian|Japanese|Chinese|Korean)",
                description,
                re.IGNORECASE,
            )
            if lang_match:
                metadata["language"] = lang_match.group(1).capitalize()

        return metadata

    def _build_event_from_config(
        self, raw_data: Dict[str, Any], event_url: str
    ) -> Dict[str, Any]:
        """Build event dict using configuration template"""
        event = {}

        # Use template fields if available
        if self.template_fields:
            # Map raw data to config fields
            for field in self.template_fields:
                if field == "occurrences":
                    # Generate occurrences from dates/times
                    event["occurrences"] = self._generate_occurrences(
                        raw_data.get("dates", []), raw_data.get("times", []), event_url
                    )
                elif field == "venue":
                    event["venue"] = self.venue_name
                elif field == "url":
                    event["url"] = event_url
                elif field == "type":
                    event["type"] = "movie"
                elif field == "location":
                    event["location"] = "301 Chicon Street, Austin, TX 78702"
                elif field == "one_liner_summary" and field not in raw_data:
                    # Generate one-liner from title if not present
                    if raw_data.get("title"):
                        event["one_liner_summary"] = (
                            f"Screening of {raw_data['title']} at Hyperreal Film Club"
                        )
                elif field == "rating" and field not in raw_data:
                    # Use default rating if not present
                    event["rating"] = self.field_defaults.get("rating", -1)
                elif field in raw_data:
                    event[field] = raw_data[field]
                elif field in self.field_defaults:
                    # Apply default value from config
                    event[field] = self.field_defaults[field]
        else:
            # Fallback to original hardcoded structure
            event = {
                "title": raw_data.get("title"),
                "date": raw_data.get("dates", [None])[0],
                "venue": "Hyperreal Film Club",
                "type": "movie",
                "url": event_url,
                "location": "301 Chicon Street, Austin, TX 78702",
            }

            if raw_data.get("times"):
                event["time"] = raw_data.get("times", [None])[0]

            if raw_data.get("description"):
                event["description"] = raw_data["description"]

        return event

    def _generate_occurrences(
        self, dates: List[str], times: List[str], url: str
    ) -> List[Dict]:
        """Generate occurrences array from dates and times"""
        occurrences = []

        # Ensure we have at least empty lists
        dates = dates or []
        times = times or ["TBD"]

        # Generate occurrences for each date
        for i, date in enumerate(dates):
            # Use corresponding time or default to first time or 'TBD'
            time = times[i] if i < len(times) else (times[0] if times else "TBD")

            occurrence = {
                "date": date,
                "time": time,
                "url": url,
                "venue": self.venue_name,
            }
            occurrences.append(occurrence)

        return occurrences

    def extract_event_with_beautifulsoup(
        self, html: str, event_url: str
    ) -> Optional[Dict]:
        """
        Extract event data from Hyperreal event page using Beautiful Soup.

        Args:
            html: The HTML content of the event page
            event_url: The URL of the event page

        Returns:
            Dict with extracted event data or None if extraction fails
        """
        try:
            soup = BeautifulSoup(html, "html.parser")

            # Extract raw data using existing patterns
            raw_data = self._extract_raw_data_from_html(soup)

            # Check if we have minimum required data
            if not raw_data.get("title") or not raw_data.get("dates"):
                return None

            # Build event using config template
            event_data = self._build_event_from_config(raw_data, event_url)

            # Apply any field defaults from config
            if self.config and hasattr(self.config, "apply_default_values"):
                event_data = self.config.apply_default_values(
                    event_data, self.venue_key
                )

            return event_data

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
                soup = BeautifulSoup(response.text, "html.parser")
                event_links = set()

                # Find all event links (pattern: /events/*)
                for link in soup.find_all(
                    "a", href=lambda h: h and h.startswith("/events/")
                ):
                    href = link.get("href", "")
                    if href:
                        full_url = f"{self.base_url}{href}"
                        event_links.add(full_url)

                # Filter for movie screenings (skip parties, fundraisers, etc.)
                movie_links = [
                    url
                    for url in event_links
                    if "screening" in url.lower() or "movie" in url.lower()
                ]

                print(f"  Found {len(movie_links)} movie events")

                # Scrape each individual event page
                for event_url in movie_links:
                    try:
                        event_response = self.session.get(event_url, timeout=10)
                        if event_response.status_code == 200:
                            # First try Beautiful Soup extraction
                            event_data = self.extract_event_with_beautifulsoup(
                                html=event_response.text, event_url=event_url
                            )

                            if event_data:
                                all_events.append(event_data)
                                print(
                                    f"    ✓ Extracted with BeautifulSoup: {event_data.get('title')}"
                                )
                            else:
                                # Fallback to LLM extraction if Beautiful Soup fails
                                print(
                                    f"    BeautifulSoup extraction failed, trying LLM for {event_url}"
                                )
                                extraction_result = self.llm_service.extract_data(
                                    content=event_response.text,
                                    schema=self.get_data_schema(),
                                    url=event_url,
                                    content_type="html",
                                )

                                if extraction_result.get("success"):
                                    event_data = extraction_result.get("data", {})

                                    # Ensure we have dates and times as arrays
                                    if (
                                        "date" in event_data
                                        and "dates" not in event_data
                                    ):
                                        event_data["dates"] = [event_data.pop("date")]
                                    if (
                                        "time" in event_data
                                        and "times" not in event_data
                                    ):
                                        event_data["times"] = [event_data.pop("time")]

                                    # Build event using config if available
                                    if self.config:
                                        event_data = self._build_event_from_config(
                                            event_data, event_url
                                        )
                                        # Apply defaults
                                        event_data = self.config.apply_default_values(
                                            event_data, self.venue_key
                                        )
                                    else:
                                        # Ensure required fields for backwards compatibility
                                        if event_data.get("title") and event_data.get(
                                            "dates"
                                        ):
                                            event_data["venue"] = self.venue_name
                                            event_data["type"] = "movie"
                                            event_data["url"] = event_url

                                    if event_data.get("title"):
                                        all_events.append(event_data)
                                        print(
                                            f"    ✓ Extracted with LLM: {event_data.get('title')}"
                                        )
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
