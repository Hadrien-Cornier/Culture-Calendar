"""
Art Austin scraper - extracts art events from artaustin.org via Perplexity.

Art Austin (artaustin.org) is a collective directory of Austin galleries and
art events. The /events/ page lists upcoming gallery receptions, artist talks,
and exhibition events across Austin. The site blocks direct scraping (403),
so events are extracted via Perplexity's domain-restricted search, which can
read the page content and return structured event data.

Each event on artaustin.org has:
  - Event type (e.g. "OPENING RECEPTION", "ARTIST TALK")
  - Title (e.g. "Summer Break")
  - Date/time string (e.g. "Saturday, July 18, 6-8 pm")
  - Venue (e.g. "Ivester Contemporary")
  - External URL (link to the venue's own page)
"""

import json
import re
from datetime import datetime
from typing import Dict, List, Optional

from src.base_scraper import BaseScraper


class ArtAustinScraper(BaseScraper):
    """Art Austin scraper - extracts art events via Perplexity search."""

    def __init__(self, config=None, venue_key="artaustin"):
        super().__init__(
            base_url="https://artaustin.org",
            venue_name="Art Austin",
            venue_key=venue_key,
            config=config,
        )

    def get_target_urls(self) -> List[str]:
        return [f"{self.base_url}/events/"]

    def scrape_events(self) -> List[Dict]:
        """Scrape art events via Perplexity domain-restricted search."""
        all_events: List[Dict] = []
        try:
            print(f"Scraping {self.venue_name} via Perplexity...")

            prompt = self._build_extraction_prompt()
            result = self.llm_service.call_perplexity(
                prompt,
                search_domain_filter=["artaustin.org"],
            )

            if not result:
                print("  Perplexity returned no results")
                return []

            events_data = result.get("events", [])
            if not events_data:
                print("  No events found in Perplexity response")
                return []

            for evt in events_data:
                formatted = self._format_perplexity_event(evt)
                if formatted:
                    all_events.append(formatted)

            print(f"  Found {len(all_events)} events")
            return all_events

        except Exception as e:
            print(f"  Error scraping {self.venue_name}: {e}")
            return []

    def _build_extraction_prompt(self) -> str:
        """Build the Perplexity prompt for extracting events from artaustin.org."""
        today = datetime.now().strftime("%B %d, %Y")
        return f"""Search artaustin.org for ALL current and upcoming art events in Austin.

Today is {today}. Only include events happening today or later.

Art Austin lists gallery receptions, artist talks, exhibition openings/closings,
and other art events across Austin galleries. Look for event listings on their
site, especially on the /events/ and /exhibitions-2/ pages.

For each event found, extract:
- type: event category (e.g. "opening reception", "artist talk", "closing reception", "exhibition")
- title: the event or exhibition title
- date_str: the date/time exactly as shown (e.g. "Saturday, July 18, 6-8 pm")
- venue: the gallery or venue name
- url: the link to learn more

Return ONLY valid JSON:
{{
  "events": [
    {{
      "type": "opening reception",
      "title": "Summer Break",
      "date_str": "Saturday, July 18, 6-8 pm",
      "venue": "Ivester Contemporary",
      "url": "https://..."
    }}
  ]
}}

Important:
- Include ALL events you find, not just the first few
- Only include events at Austin-area venues
- Include the exact date string as shown on the page
- Skip events that have already passed
"""

    def _format_perplexity_event(self, evt: Dict) -> Optional[Dict]:
        """Convert a Perplexity-extracted event into the pipeline schema."""
        title = evt.get("title", "").strip()
        event_type = evt.get("type", "").strip()
        # Perplexity may use 'date' or 'date_str'
        date_str = (evt.get("date_str") or evt.get("date") or "").strip()
        venue = evt.get("venue", "").strip()
        url = evt.get("url", "").strip()

        if not title or not date_str:
            return None

        # Skip events that look like they're in the past
        dates, _ = self._parse_date_time(date_str)
        if dates:
            from datetime import date as date_type
            event_date = date_type.fromisoformat(dates[0])
            if event_date < date_type.today():
                return None

        # Combine type + title if both present, normalizing type casing
        if event_type:
            # Normalize: "closing reception" -> "Closing Reception"
            type_label = event_type.strip().title()
            # Skip if type is already part of the title
            if type_label.lower() not in title.lower():
                full_title = f"{type_label}: {title}"
            else:
                full_title = title
        else:
            full_title = title

        # Parse the date string
        dates, times = self._parse_date_time(date_str)
        if not dates:
            return None

        event = {
            "title": full_title,
            "venue": venue or self.venue_name,
            "url": url or f"{self.base_url}/events/",
            "dates": dates,
            "times": times,
            "type": "visual_arts",
            "source": "artaustin",
        }
        return self.format_event(event)

    def _parse_date_time(self, date_str: str) -> tuple:
        """Parse strings like 'Saturday, July 18, 2-4 pm' into ISO dates/times.

        Returns:
            (dates, times) tuple: dates = ['YYYY-MM-DD'], times = ['HH:MM']
        """
        s = date_str.strip()
        # Normalize dashes (en-dash, em-dash to hyphen)
        s = s.replace("\u2013", "-").replace("\u2014", "-")

        # Date range for exhibitions: "July 16, 2026 - September 13, 2026"
        # Use the start date; exhibitions have no specific time.
        range_m = re.match(
            r"(\w+)\s+(\d{1,2}),\s+(\d{4})\s*-\s*(\w+)\s+(\d{1,2}),\s+(\d{4})",
            s,
            re.IGNORECASE,
        )
        if range_m:
            month_str, day_str, year_str = range_m.group(1), range_m.group(2), range_m.group(3)
            months = {
                "january": 1, "february": 2, "march": 3, "april": 4,
                "may": 5, "june": 6, "july": 7, "august": 8,
                "september": 9, "october": 10, "november": 11, "december": 12,
            }
            month = months.get(month_str.lower())
            if month:
                date_iso = f"{int(year_str):04d}-{month:02d}-{int(day_str):02d}"
                return [date_iso], ["10:00"]  # galleries typically open at 10am
            return [], []

        # Formats to handle:
        #   "Saturday, July 18, 2-4 pm"       (no year)
        #   "Sunday, July 26, 2026, 1-4 pm"   (year before time)
        #   "July 18, 2-4 pm"                 (no day-of-week, no year)
        m = re.match(
            r"(?:\w+day,\s+)?(\w+)\s+(\d{1,2})(?:,\s+(\d{4}))?,\s*(.+)",
            s,
            re.IGNORECASE,
        )
        if not m:
            m = re.match(
                r"(\w+)\s+(\d{1,2})(?:,\s+(\d{4}))?,\s*(.+)",
                s,
                re.IGNORECASE,
            )
            if not m:
                return [], []

        month_str, day_str, year_str, time_str = m.groups()

        months = {
            "january": 1, "february": 2, "march": 3, "april": 4,
            "may": 5, "june": 6, "july": 7, "august": 8,
            "september": 9, "october": 10, "november": 11, "december": 12,
        }
        month = months.get(month_str.lower())
        if not month:
            return [], []

        day = int(day_str)
        year = int(year_str) if year_str else datetime.now().year

        # Parse time - strip trailing year if present (e.g. "1-4 pm, 2026" -> "1-4 pm")
        time_str = time_str.strip()
        time_str = re.sub(r",\s*\d{4}$", "", time_str)
        # Time range: "2-4 pm" or "6-8 pm"
        tm = re.match(
            r"(\d{1,2})(?::(\d{2}))?\s*-\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)",
            time_str,
            re.IGNORECASE,
        )
        if tm:
            hour = int(tm.group(1))
            minute = int(tm.group(2)) if tm.group(2) else 0
            ampm = tm.group(5).lower()
        else:
            tm = re.match(
                r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", time_str, re.IGNORECASE
            )
            if not tm:
                return [], []
            hour = int(tm.group(1))
            minute = int(tm.group(2)) if tm.group(2) else 0
            ampm = tm.group(3).lower()

        if ampm == "pm" and hour != 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0

        date_iso = f"{year:04d}-{month:02d}-{day:02d}"
        time_val = f"{hour:02d}:{minute:02d}"
        return [date_iso], [time_val]
