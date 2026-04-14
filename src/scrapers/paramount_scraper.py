"""
Paramount Theatre scraper.

Tries static HTML first via BeautifulSoup; falls back to Playwright
(Chromium, sync API) when the listing is JS-rendered. Replaced
pyppeteer in 2026-04 because pyppeteer's Chromium crashes on Python 3.13.
"""

import re
from datetime import datetime
from typing import Dict, List

from bs4 import BeautifulSoup

from ..base_scraper import BaseScraper
from ..schemas import MovieEventSchema


class ParamountScraper(BaseScraper):
    """Scraper for Paramount Theatre (Austin) movie events."""

    def __init__(self, config=None, venue_key="paramount"):
        super().__init__(
            base_url="https://tickets.austintheatre.org",
            venue_name="Paramount Theatre",
            venue_key=venue_key,
            config=config,
        )

    # ---------- Public helpers ----------

    def get_target_urls(self) -> List[str]:
        """Return the starting URL(s) for scraping"""
        return [f"{self.base_url}/events"]

    def get_data_schema(self) -> Dict:
        """Return schema for movie events"""
        return MovieEventSchema.get_schema()

    # ---------- Core scraping ----------

    def scrape_events(self) -> List[Dict]:
        """Main entrypoint – fetch Paramount events from the JSON API.

        The ticketing site loads events via POST /api/products/productionseasons.
        We hit it directly with a 90-day window and translate each performance
        into a (title, date, time) event the rest of the pipeline expects.
        """
        print(f"Scraping {self.venue_name}...")
        events = self._fetch_via_api()
        if events:
            print(f"Successfully scraped {len(events)} Paramount events total")
            return events

        # API miss → fall back to old listing approach (kept for safety).
        print("  API returned 0 events; trying static HTML fallback")
        events_page_url = self.get_target_urls()[0]
        event_links = self._extract_event_links(events_page_url)
        if not event_links:
            event_links = self._extract_event_links_with_pyppeteer(events_page_url)
        print(f"  Found {len(event_links)} potential event pages")
        all_events: List[Dict] = []
        for url in event_links:
            try:
                event_data = self._scrape_event_page(url)
                if event_data and event_data.get("title") and event_data.get("date"):
                    event_data.setdefault("venue", self.venue_name)
                    event_data.setdefault("type", "movie")
                    event_data["url"] = url
                    all_events.append(event_data)
            except Exception as exc:
                print(f"    Error extracting {url}: {exc}")
        print(f"Successfully scraped {len(all_events)} Paramount events total")
        return all_events

    def _fetch_via_api(self) -> List[Dict]:
        """POST to the productions API and translate each performance to an event."""
        from datetime import timedelta
        try:
            today = datetime.now()
            payload = {
                "startDate": today.strftime("%Y-%m-%d"),
                "endDate": (today + timedelta(days=90)).strftime("%Y-%m-%d"),
            }
            # BaseScraper sets Accept: text/html, but the productionseasons API
            # returns 500 unless Accept allows JSON. Override per-request.
            resp = self.session.post(
                f"{self.base_url}/api/products/productionseasons",
                json=payload,
                timeout=20,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/plain, */*",
                },
            )
            if resp.status_code != 200:
                print(f"  Paramount API error: {resp.status_code}")
                return []
            data = resp.json()
        except Exception as exc:
            print(f"  Paramount API error: {exc}")
            return []

        events: List[Dict] = []
        for production in data:
            title = (production.get("productionTitle") or "").strip()
            description = (production.get("description") or "").strip()
            if not title:
                continue
            for perf in production.get("performances", []):
                if not perf.get("isPerformanceVisible", True):
                    continue
                iso = perf.get("iso8601DateString") or perf.get("performanceDate")
                if not iso:
                    continue
                try:
                    dt = datetime.fromisoformat(iso.split("+")[0].rstrip("Z"))
                except ValueError:
                    continue
                date_iso = dt.strftime("%Y-%m-%d")
                # Display time like '7:30PM' or '12:00AM'
                display_time = (perf.get("displayTime") or "").upper().replace(" ", "")
                if not display_time:
                    continue
                m = re.fullmatch(r"(\d{1,2}):(\d{2})(AM|PM)", display_time)
                time_str = f"{int(m.group(1))}:{m.group(2)} {m.group(3)}" if m else display_time
                action_url = perf.get("actionUrl") or production.get("actionUrl") or ""
                events.append({
                    "title": title,
                    "type": "movie",
                    "dates": [date_iso],
                    "times": [time_str],
                    "venue": self.venue_name,
                    "url": action_url or f"{self.base_url}/{production.get('productionSeasonId','')}",
                    "description": description or f"{title} at the Paramount Theatre",
                })
        return events

    # ---------- Internal helpers ----------

    def _extract_event_links(self, url: str) -> List[str]:
        """Try to extract event links from a page using static HTML."""
        try:
            resp = self.session.get(url, timeout=15)
            if resp.status_code != 200:
                print(f"  Failed to fetch listing page (status {resp.status_code})")
                return []

            soup = BeautifulSoup(resp.text, "html.parser")
            links = []

            for a in soup.find_all("a", href=True):
                href = a["href"]
                # Paramount event pages are numeric ids like '/12540'
                if re.match(r"^/\d{4,}$", href):
                    full = f"{self.base_url}{href}" if href.startswith("/") else href
                    if full not in links:
                        links.append(full)

            return links
        except Exception as exc:
            print(f"  Error extracting links via BeautifulSoup: {exc}")
            return []

    def _extract_event_links_with_pyppeteer(self, url: str) -> List[str]:
        """Render the listing in Playwright Chromium and extract event links.

        (Method name kept for backward compatibility; routes to Playwright now.)
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            print("  playwright not installed; cannot render Paramount listing")
            return []

        try:
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
                    html = page.content()
                finally:
                    browser.close()
        except Exception as exc:
            print(f"  Playwright link extraction error: {exc}")
            return []

        soup = BeautifulSoup(html, "html.parser")
        links: List[str] = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if re.match(r"^/\d{4,}$", href):
                full = f"{self.base_url}{href}" if href.startswith("/") else href
                if full not in links:
                    links.append(full)
        return links

    # -- Individual event page parsing

    def _scrape_event_page(self, url: str) -> Dict:
        """Scrape a single event page (HTML already rendered server-side)."""
        resp = self.session.get(url, timeout=15)
        if resp.status_code != 200:
            return {}

        # First attempt: use LLM extraction for maximum recall
        try:
            extraction_result = self.llm_service.extract_data(
                content=resp.text,
                schema=self.get_data_schema(),
                url=url,
                content_type="html",
            )
            if extraction_result.get("success"):
                data = extraction_result.get("data", {})
                if data:
                    return data
        except Exception as exc:
            print(f"  LLM extraction error for {url}: {exc}")

        # Fallback: manual BeautifulSoup parsing
        return self._manual_parse_event(resp.text, url)

    def _manual_parse_event(self, html: str, url: str) -> Dict:
        """Very lightweight manual parsing as a fallback when LLM fails."""
        soup = BeautifulSoup(html, "html.parser")
        title = None
        desc = None
        date_str = None
        time_str = None

        # Title – choose the last h1 text as it usually contains the movie title
        h1_tags = soup.find_all("h1")
        if h1_tags:
            title = h1_tags[-1].get_text(strip=True)

        # Description – first couple paragraphs after main heading
        paragraphs = soup.find_all("p")
        if paragraphs:
            desc = paragraphs[0].get_text(separator=" ", strip=True)

        # Search for date/time patterns in plain text
        text_content = soup.get_text(separator=" ", strip=True)
        date_match = re.search(
            r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}",
            text_content,
        )
        if date_match:
            try:
                dt = datetime.strptime(date_match.group(0), "%B %d, %Y")
                date_str = dt.strftime("%Y-%m-%d")
            except Exception:
                pass

        # Time
        time_match = re.search(r"\b\d{1,2}:\d{2}\s*[APMapm]{2}\b", text_content)
        if time_match:
            time_str = time_match.group(0).upper()
        else:
            # Another pattern like "7:30PM" (no space)
            time_match = re.search(r"\b\d{1,2}:\d{2}[APMapm]{2}\b", text_content)
            if time_match:
                # Insert space before AM/PM
                raw = time_match.group(0)
                time_str = re.sub(r"([APMapm]{2})$", r" \1", raw).upper()

        return {
            "title": title,
            "date": date_str,
            "time": time_str,
            "description": desc,
            "venue": self.venue_name,
            "type": "movie",
            "url": url,
        }

    # -- Public details fetch

    def get_event_details(self, event: Dict) -> Dict:
        """Return extra details for a Paramount event (not needed currently)."""
        return {} 