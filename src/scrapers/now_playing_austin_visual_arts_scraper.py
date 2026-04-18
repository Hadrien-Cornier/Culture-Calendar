"""NowPlayingAustin visual-arts scraper.

Scrapes https://nowplayingaustin.com/categories/visual-art/ and related
paginated listing pages. The listing is static HTML (no JS rendering
required), so we use requests + BeautifulSoup.

Each event in the listing is an ``<li>`` containing an anchor tagged
``event-slug-on-date``. Specific dated occurrences are rendered inside
``.show-events .item`` as strings such as ``"Apr 17, 2026 at 10:00am -
6:00pm  (Fri)"``. When no itemized occurrences are present we fall back
to the date-bubble range in ``.left-event-time``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from bs4 import BeautifulSoup, Tag

from ..base_scraper import BaseScraper


MONTH_NAMES = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}


@dataclass(frozen=True)
class Occurrence:
    date: str  # YYYY-MM-DD
    time: str  # HH:mm (24h)


class NowPlayingAustinVisualArtsScraper(BaseScraper):
    """Scraper for visual-arts events on nowplayingaustin.com."""

    LISTING_PATH = "/categories/visual-art/"

    def __init__(self, config=None, venue_key: str = "now_playing_austin_visual_arts"):
        super().__init__(
            base_url="https://nowplayingaustin.com",
            venue_name="NowPlayingAustin — Visual Arts",
            venue_key=venue_key,
            config=config,
        )

    # ---------- Public API ----------

    def get_target_urls(self) -> List[str]:
        return [f"{self.base_url}{self.LISTING_PATH}"]

    def scrape_events(self) -> List[Dict]:
        print(f"Scraping {self.venue_name}...")
        events: List[Dict] = []
        seen_urls: set[str] = set()
        for url in self.get_target_urls():
            html = self._fetch(url)
            if not html:
                continue
            for event in self.parse_listing(html):
                event_url = event.get("url", "")
                if event_url in seen_urls:
                    continue
                seen_urls.add(event_url)
                events.append(event)
        print(f"Successfully scraped {len(events)} visual-arts events")
        return events

    # ---------- Parsing ----------

    def parse_listing(self, html: str) -> List[Dict]:
        """Parse a listing page's HTML into a list of normalized events."""
        soup = BeautifulSoup(html, "html.parser")
        events: List[Dict] = []
        for anchor in soup.select("a.event-slug-on-date"):
            li = anchor.find_parent("li")
            if not li:
                continue
            event = self._parse_event(li, anchor)
            if event is not None:
                events.append(event)
        return events

    def _parse_event(self, li: Tag, anchor: Tag) -> Optional[Dict]:
        url = (anchor.get("href") or "").strip()
        title_el = li.select_one(".ev-tt")
        title = title_el.get_text(strip=True) if title_el else ""
        if not (url and title):
            return None

        venue = self._extract_venue(li)
        occurrences = self._extract_occurrences(li, anchor)
        if not occurrences:
            return None

        dates = [occ.date for occ in occurrences]
        times = [occ.time for occ in occurrences]

        return {
            "title": title,
            "venue": venue or self.venue_name,
            "url": url,
            "dates": dates,
            "times": times,
            "type": "visual_arts",
            "event_category": "visual_arts",
            "description": "",
        }

    def _extract_venue(self, li: Tag) -> str:
        venue_block = li.select_one(".venue-event")
        if not venue_block:
            return ""
        link = venue_block.find("a")
        if link:
            return link.get_text(strip=True)
        return venue_block.get_text(" ", strip=True)

    def _extract_occurrences(self, li: Tag, anchor: Tag) -> List[Occurrence]:
        """Prefer itemized occurrences; fall back to the date-bubble range."""
        occurrences: List[Occurrence] = []
        for item in li.select(".show-events .item"):
            parsed = self._parse_show_event_item(item.get_text(" ", strip=True))
            if parsed is not None:
                occurrences.append(parsed)
        if occurrences:
            return occurrences

        # Fallback: the date bubble provides a start date only (single-day
        # events) or a range. Ranges describe an exhibition window; without
        # specific times we cannot enumerate every day, so we return a single
        # placeholder occurrence on the start date.
        start_date = self._parse_date_bubble_start(anchor)
        if start_date is None:
            return []
        return [Occurrence(date=start_date, time="00:00")]

    # ---------- Helpers ----------

    _ITEM_RE = re.compile(
        r"""
        (?P<month>[A-Za-z]+)\s+
        (?P<day>\d{1,2}),\s+
        (?P<year>\d{4})
        \s+at\s+
        (?P<hour>\d{1,2})
        (?::(?P<minute>\d{2}))?
        \s*(?P<meridiem>[AaPp][Mm])
        """,
        re.VERBOSE,
    )

    def _parse_show_event_item(self, text: str) -> Optional[Occurrence]:
        match = self._ITEM_RE.search(text)
        if not match:
            return None
        month = MONTH_NAMES.get(match.group("month")[:3].lower())
        if month is None:
            return None
        day = int(match.group("day"))
        year = int(match.group("year"))
        hour = int(match.group("hour"))
        minute = int(match.group("minute") or 0)
        meridiem = match.group("meridiem").lower()
        if meridiem == "pm" and hour < 12:
            hour += 12
        elif meridiem == "am" and hour == 12:
            hour = 0
        try:
            dt = datetime(year, month, day, hour, minute)
        except ValueError:
            return None
        return Occurrence(date=dt.strftime("%Y-%m-%d"), time=dt.strftime("%H:%M"))

    def _parse_date_bubble_start(self, anchor: Tag) -> Optional[str]:
        bubble = anchor.select_one(".left-event-time .month")
        if bubble is None:
            return None
        spans = [s.get_text(strip=True) for s in bubble.find_all("span")]
        if len(spans) < 3:
            return None
        month = MONTH_NAMES.get(spans[0][:3].lower())
        if month is None:
            return None
        try:
            day = int(spans[1])
            year = int(spans[2])
            return datetime(year, month, day).strftime("%Y-%m-%d")
        except ValueError:
            return None

    def _fetch(self, url: str) -> str:
        try:
            resp = self.session.get(url, timeout=20)
            if resp.status_code != 200:
                print(f"  NowPlayingAustin: {url} returned {resp.status_code}")
                return ""
            return resp.text
        except Exception as exc:
            print(f"  NowPlayingAustin fetch error for {url}: {exc}")
            return ""
