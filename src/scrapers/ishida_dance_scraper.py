"""ISHIDA Dance Company scraper.

ISHIDA (https://www.ishidadance.org) is a nationally touring Austin
contemporary-dance company. Its own site is a single-page Squarespace blurb
that lists the current production and venues but **publishes no show times**;
the only authoritative source for per-performance dates/times is the company's
own ticketing subdomain ``ishida.thundertix.com``, which it links from the
homepage. ThunderTix exposes clean schema.org ``Event`` JSON-LD plus a
``#performances`` table with one ``<time>`` row per show, so this scraper:

1. fetches the company homepage and harvests the ThunderTix event links it
   advertises (no hard-coded event IDs — they change every season);
2. fetches each ThunderTix event page and reads the JSON-LD for the title,
   description, and venue/city;
3. reads the ``#performances`` table for the exact per-show date + time
   (times genuinely vary — e.g. evening shows plus a Sunday matinee);
4. keeps only the **Austin** run (``addressLocality == "Austin"``) so the
   company's Houston/touring dates stay off this Austin-focused calendar.

Each production becomes a single ``type=dance`` event carrying parallel
``dates`` / ``times`` arrays (the shape ``BaseScraper.format_event`` and the
``dance`` template expect — screenings are generated downstream).
"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime
from typing import Dict, List, Optional

from bs4 import BeautifulSoup

from ..base_scraper import BaseScraper

_THUNDERTIX_EVENT = re.compile(
    r"https?://[\w.-]*thundertix\.com/events/\d+", re.IGNORECASE
)

# "Thursday, June 18, 2026 - 08:00 PM" — full weekday + clock time. Requiring a
# clock time excludes the run-range header (e.g. "Thu Jun 18, 2026 - Sat Jun
# 20, 2026"), which carries no time.
_PERF_DATETIME = re.compile(
    r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+"
    r"(January|February|March|April|May|June|July|August|September|October|"
    r"November|December)\s+(\d{1,2}),\s+(\d{4})\s*[-–]\s*"
    r"(\d{1,2}:\d{2}\s*[AP]M)",
    re.IGNORECASE,
)

_AUSTIN = "austin"


class IshidaDanceScraper(BaseScraper):
    """Scraper for ISHIDA Dance Company (homepage → ThunderTix JSON-LD)."""

    def __init__(self, config=None, venue_key: str = "ishida_dance") -> None:
        super().__init__(
            base_url="https://www.ishidadance.org",
            venue_name="ISHIDA Dance Company",
            venue_key=venue_key,
            config=config,
        )

    # ---------- Public API ----------

    def get_target_urls(self) -> List[str]:
        return [f"{self.base_url}/"]

    def scrape_events(self) -> List[Dict]:
        print(f"Scraping {self.venue_name}...")
        events: List[Dict] = []
        seen: set[str] = set()
        for home_url in self.get_target_urls():
            home_html = self._fetch(home_url)
            if not home_html:
                continue
            for event_url in self._find_thundertix_links(home_html):
                if event_url in seen:
                    continue
                seen.add(event_url)
                page = self._fetch(event_url)
                if not page:
                    continue
                event = self._parse_thundertix_event(page, event_url)
                if event is not None:
                    events.append(event)
        print(f"Scraped {len(events)} events from {self.venue_name}")
        return events

    def get_event_details(self, event: Dict) -> Dict:
        """Listing parse yields complete events; no per-event detail fetch."""
        return {}

    # ---------- Parsing ----------

    def _find_thundertix_links(self, home_html: str) -> List[str]:
        """Unique ThunderTix event URLs advertised on the homepage, in order."""
        ordered: List[str] = []
        seen: set[str] = set()
        for match in _THUNDERTIX_EVENT.finditer(html.unescape(home_html)):
            url = match.group(0)
            if url not in seen:
                seen.add(url)
                ordered.append(url)
        return ordered

    def _parse_thundertix_event(self, page: str, event_url: str) -> Optional[Dict]:
        soup = BeautifulSoup(page, "html.parser")
        ld = self._extract_event_jsonld(soup)
        if not ld:
            return None

        # Austin-only: drop Houston / other touring stops.
        locality = self._locality(ld)
        if locality and locality.strip().lower() != _AUSTIN:
            return None

        dates, times = self._extract_performances(soup)
        if not dates:
            return None

        title = self._clean_title(ld.get("name", ""))
        if not title:
            return None

        program = self._clean_text(ld.get("description", ""))
        location = ""
        loc = ld.get("location")
        if isinstance(loc, dict):
            location = str(loc.get("name") or "").strip()

        return {
            "title": title,
            "type": "dance",
            "dates": dates,
            "times": times,
            "venue": self.venue_name,
            "location": location,
            "url": event_url,
            "program": program,
            "description": program,
            "series": "ISHIDA Dance Company",
        }

    def _extract_event_jsonld(self, soup: BeautifulSoup) -> Optional[Dict]:
        """Return the first schema.org ``Event`` object across all ld+json blocks."""
        for tag in soup.find_all("script", type="application/ld+json"):
            raw = tag.string or tag.get_text() or ""
            if not raw.strip():
                continue
            try:
                data = json.loads(raw)
            except (ValueError, TypeError):
                continue
            for node in self._iter_jsonld_nodes(data):
                node_type = node.get("@type")
                types = node_type if isinstance(node_type, list) else [node_type]
                if any(str(t).lower() == "event" for t in types):
                    return node
        return None

    @staticmethod
    def _iter_jsonld_nodes(data):
        """Yield candidate dict nodes from a dict / list / @graph payload."""
        stack = [data]
        while stack:
            item = stack.pop()
            if isinstance(item, list):
                stack.extend(item)
            elif isinstance(item, dict):
                yield item
                graph = item.get("@graph")
                if isinstance(graph, list):
                    stack.extend(graph)

    @staticmethod
    def _locality(ld: Dict) -> str:
        loc = ld.get("location")
        if isinstance(loc, list):
            loc = loc[0] if loc else None
        if isinstance(loc, dict):
            address = loc.get("address")
            if isinstance(address, dict):
                return str(address.get("addressLocality") or "")
        return ""

    def _extract_performances(self, soup: BeautifulSoup) -> tuple[List[str], List[str]]:
        """Pull per-show (date, time) pairs from the ``#performances`` table.

        Falls back to scanning the whole document if the table id ever changes,
        so a Squarespace/ThunderTix tweak degrades to "still finds the shows"
        rather than "finds nothing".
        """
        table = soup.find(id="performances")
        scope = table if table is not None else soup
        text = scope.get_text(" ", strip=True)

        # Dedupe on (date, time), NOT date alone — a single day can hold both a
        # matinee and an evening show (Ishida does this on tour), and collapsing
        # by date would silently drop one. Sort chronologically via a 24h key.
        rows: List[tuple[str, str, str]] = []  # (date, sort_key_24h, display_time)
        seen: set[tuple[str, str]] = set()
        for month, day, year, clock in _PERF_DATETIME.findall(text):
            iso = self._to_iso(month, day, year)
            time_str = self._normalize_time(clock)
            key24 = self._to_24h(clock)
            if iso is None or time_str is None or key24 is None:
                continue
            if (iso, key24) in seen:
                continue
            seen.add((iso, key24))
            rows.append((iso, key24, time_str))

        rows.sort(key=lambda r: (r[0], r[1]))
        dates = [r[0] for r in rows]
        times = [r[2] for r in rows]
        return dates, times

    # ---------- Helpers ----------

    @staticmethod
    def _clean_title(name: str) -> str:
        """'ISHIDA - waiting / REX' → 'waiting / REX'."""
        cleaned = html.unescape(name or "").strip()
        cleaned = re.sub(r"^ISHIDA\s*[-–:]\s*", "", cleaned, flags=re.IGNORECASE)
        return cleaned.strip()

    @staticmethod
    def _clean_text(text: str) -> str:
        unescaped = html.unescape(text or "").replace(" ", " ")
        return re.sub(r"\s+", " ", unescaped).strip()

    @staticmethod
    def _to_iso(month: str, day: str, year: str) -> Optional[str]:
        try:
            dt = datetime.strptime(f"{month} {int(day)} {year}", "%B %d %Y")
        except ValueError:
            return None
        return dt.strftime("%Y-%m-%d")

    @staticmethod
    def _normalize_time(clock: str) -> Optional[str]:
        cleaned = re.sub(r"\s+", " ", clock.strip().upper())
        try:
            return datetime.strptime(cleaned, "%I:%M %p").strftime("%-I:%M %p")
        except ValueError:
            return None

    @staticmethod
    def _to_24h(clock: str) -> Optional[str]:
        """Sortable 24h key ('08:00 PM' -> '20:00') for chronological ordering."""
        cleaned = re.sub(r"\s+", " ", clock.strip().upper())
        try:
            return datetime.strptime(cleaned, "%I:%M %p").strftime("%H:%M")
        except ValueError:
            return None

    def _fetch(self, url: str) -> str:
        try:
            resp = self.session.get(url, timeout=20)
            if resp.status_code != 200:
                print(f"  {self.venue_name}: {url} returned {resp.status_code}")
                return ""
            return resp.text
        except Exception as exc:  # pragma: no cover - network failure path
            print(f"  {self.venue_name} fetch error for {url}: {exc}")
            return ""
