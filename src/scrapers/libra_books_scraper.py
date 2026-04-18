"""Livra Books events scraper.

The venue is officially **Livra Books** (livrabooks.com) — the overnight queue
refers to it as "Libra Books" so the module keeps that name for continuity with
the task id. The events page is a Squarespace event list that renders every
event server-side, so a plain ``requests.get`` + BeautifulSoup parse is
enough; no Playwright/Pyppeteer rendering needed.

Each event is an ``<article class="eventlist-event">`` with a stable skeleton:
``h1.eventlist-title > a.eventlist-title-link`` for title and URL,
``time.event-date[datetime]`` for the ISO start date, and
``time.event-time-localized-start`` for the visible start time. An excerpt (or
fallback full description) is exposed via ``.eventlist-excerpt`` or
``.eventlist-description``. Events are grouped into ``.eventlist--upcoming``
and ``.eventlist--past`` siblings — we walk both so past fixtures still parse.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Dict, List, Optional

from bs4 import BeautifulSoup, Tag

from ..base_scraper import BaseScraper


_TITLE_POP_UP = re.compile(r"pop[-\s]?up", re.IGNORECASE)
_TITLE_THEORY_NIGHT = re.compile(r"theory\s+night", re.IGNORECASE)
_TITLE_BOOK_CLUB = re.compile(r"book\s+club", re.IGNORECASE)
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class LibraBooksScraper(BaseScraper):
    """Scraper for Livra Books events (https://www.livrabooks.com/events)."""

    EVENTS_PATH = "/events"

    def __init__(self, config=None, venue_key: str = "libra_books") -> None:
        super().__init__(
            base_url="https://www.livrabooks.com",
            venue_name="Livra Books",
            venue_key=venue_key,
            config=config,
        )

    # ---------- Public API ----------

    def get_target_urls(self) -> List[str]:
        return [f"{self.base_url}{self.EVENTS_PATH}"]

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
        print(f"Scraped {len(events)} events from {self.venue_name}")
        return events

    def get_event_details(self, event: Dict) -> Dict:
        """Listing parse yields complete events; no per-event detail fetch."""
        return {}

    # ---------- Parsing ----------

    def parse_listing(self, html: str) -> List[Dict]:
        """Parse a Livra Books events HTML document into normalized events."""
        soup = BeautifulSoup(html, "html.parser")
        events: List[Dict] = []
        for article in soup.select("article.eventlist-event"):
            event = self._parse_article(article)
            if event is not None:
                events.append(event)
        return events

    def _parse_article(self, article: Tag) -> Optional[Dict]:
        title, url = self._extract_title_and_url(article)
        if not title or not url:
            return None

        date = self._extract_iso_start_date(article)
        if date is None:
            return None

        time_str = self._extract_start_time(article)
        if time_str is None:
            return None

        description = self._extract_description(article)
        classification = self._classify_title(title)

        event: Dict = {
            "title": title,
            "type": classification,
            "dates": [date],
            "times": [time_str],
            "venue": self.venue_name,
            "url": url,
            "description": description,
        }
        if classification == "book_club":
            event["series"] = self._extract_series(title)
        return event

    # ---------- Field extractors ----------

    def _extract_title_and_url(self, article: Tag) -> tuple[Optional[str], Optional[str]]:
        link = article.select_one("h1.eventlist-title a.eventlist-title-link")
        if link is None:
            return None, None
        title = link.get_text(strip=True)
        href = (link.get("href") or "").strip()
        if not href:
            return title or None, None
        url = href if href.startswith("http") else f"{self.base_url}{href}"
        return (title or None), url

    def _extract_iso_start_date(self, article: Tag) -> Optional[str]:
        time_el = article.select_one("time.event-date")
        if time_el is None:
            return None
        iso = (time_el.get("datetime") or "").strip()
        if _ISO_DATE.match(iso):
            return iso
        text = time_el.get_text(" ", strip=True)
        return self._parse_long_date(text)

    def _extract_start_time(self, article: Tag) -> Optional[str]:
        time_el = article.select_one("time.event-time-localized-start")
        if time_el is None:
            return None
        raw = time_el.get_text(strip=True)
        return self._normalize_time(raw)

    def _extract_description(self, article: Tag) -> str:
        for selector in (".eventlist-excerpt", ".eventlist-description"):
            block = article.select_one(selector)
            if block is None:
                continue
            text = block.get_text(" ", strip=True)
            if text:
                return text
        return ""

    # ---------- Helpers ----------

    @staticmethod
    def _classify_title(title: str) -> str:
        if _TITLE_POP_UP.search(title):
            return "other"
        if _TITLE_THEORY_NIGHT.search(title):
            return "other"
        if _TITLE_BOOK_CLUB.search(title):
            return "book_club"
        return "other"

    @staticmethod
    def _extract_series(title: str) -> str:
        """Series is 'Livra Book Club' / 'Livra Nature Book Club' — the portion
        of the title before the first colon, falling back to a generic label."""
        if ":" in title:
            return title.split(":", 1)[0].strip()
        return title.strip()

    @staticmethod
    def _normalize_time(raw: str) -> Optional[str]:
        cleaned = raw.strip().upper().replace(".", "")
        for fmt in ("%I:%M %p", "%I %p", "%H:%M"):
            try:
                return datetime.strptime(cleaned, fmt).strftime("%H:%M")
            except ValueError:
                continue
        return None

    @staticmethod
    def _parse_long_date(text: str) -> Optional[str]:
        """Fallback: parse 'Tuesday, March 17, 2026' → '2026-03-17'."""
        cleaned = re.sub(r",\s+", ", ", text.strip())
        for fmt in ("%A, %B %d, %Y", "%B %d, %Y"):
            try:
                return datetime.strptime(cleaned, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return None

    def _fetch(self, url: str) -> str:
        try:
            resp = self.session.get(url, timeout=20)
            if resp.status_code != 200:
                print(f"  Livra Books: {url} returned {resp.status_code}")
                return ""
            return resp.text
        except Exception as exc:
            print(f"  Livra Books fetch error for {url}: {exc}")
            return ""
