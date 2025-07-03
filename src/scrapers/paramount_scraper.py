"""
Paramount Theatre scraper - scrapes movie events listing at tickets.austintheatre.org
Uses BeautifulSoup for static parsing and pyppeteer when JavaScript rendering is required.
"""

import re
import asyncio
from datetime import datetime
from typing import Dict, List

from bs4 import BeautifulSoup

from pyppeteer import launch

from ..base_scraper import BaseScraper
from ..schemas import MovieEventSchema


class ParamountScraper(BaseScraper):
    """Scraper for Paramount Theatre (Austin) movie events."""

    def __init__(self):
        super().__init__(
            base_url="https://tickets.austintheatre.org",
            venue_name="Paramount Theatre",
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
        """Main entrypoint – scrape Paramount events"""
        print(f"Scraping {self.venue_name}...")
        events_page_url = self.get_target_urls()[0]
        event_links = self._extract_event_links(events_page_url)

        # Fallback to pyppeteer if no links were found via static HTML
        if not event_links:
            print("  No links found in static HTML – falling back to pyppeteer JS rendering")
            event_links = self._extract_event_links_with_pyppeteer(events_page_url)

        print(f"  Found {len(event_links)} potential event pages")

        all_events: List[Dict] = []
        for url in event_links:
            try:
                event_data = self._scrape_event_page(url)
                if event_data and event_data.get("title") and event_data.get("date"):
                    # Ensure required/common fields
                    event_data.setdefault("venue", self.venue_name)
                    event_data.setdefault("type", "movie")
                    event_data["url"] = url
                    all_events.append(event_data)
                    print(f"    ✓ Extracted {event_data.get('title')} ({event_data.get('date')})")
            except Exception as exc:
                print(f"    Error extracting {url}: {exc}")

        print(f"Successfully scraped {len(all_events)} Paramount events total")
        return all_events

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

    # -- pyppeteer variant

    async def _extract_links_pyppeteer_async(self, url: str) -> List[str]:
        """Render page in headless browser and extract event links"""
        browser = None
        try:
            browser = await launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ],
            )
            page = await browser.newPage()
            await page.setUserAgent(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            await page.goto(url, {"waitUntil": "networkidle0", "timeout": 30000})
            await asyncio.sleep(3)
            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")
            links: List[str] = []

            for a in soup.find_all("a", href=True):
                href = a["href"]
                if re.match(r"^/\d{4,}$", href):
                    full = f"{self.base_url}{href}" if href.startswith("/") else href
                    if full not in links:
                        links.append(full)
            return links
        except Exception as exc:
            print(f"  pyppeteer link extraction error: {exc}")
            return []
        finally:
            if browser:
                try:
                    await browser.close()
                except BaseException:
                    pass

    def _extract_event_links_with_pyppeteer(self, url: str) -> List[str]:
        """Synchronous wrapper around async pyppeteer extraction"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(self._extract_links_pyppeteer_async(url))
        except Exception as exc:
            print(f"  pyppeteer wrapper error: {exc}")
            return []
        finally:
            try:
                loop.close()
            except BaseException:
                pass

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