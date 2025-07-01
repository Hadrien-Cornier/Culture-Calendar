"""
Austin Movie Society scraper - scrapes events from website
"""

import re
from datetime import datetime
from typing import Dict, List
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..base_scraper import BaseScraper
from ..schemas import MovieEventSchema


class AFSScraper(BaseScraper):
    """Austin Movie Society scraper - extracts movie screenings from website."""

    def __init__(self):
        super().__init__(
            base_url="https://www.austinfilm.org", venue_name="Austin Movie Society"
        )
        # Set better headers to bypass anti-bot protection
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Cache-Control": "max-age=0",
        }
        self.session.headers.update(headers)

    def get_target_urls(self) -> List[str]:
        """Return list of URLs to scrape"""
        return [
            f"{self.base_url}/screenings/",
            f"{self.base_url}/calendar/",
        ]

    def get_data_schema(self) -> Dict:
        """Return the expected data schema for AFS movie events"""
        return MovieEventSchema.get_schema()

    def scrape_events(self) -> List[Dict]:
        """
        Scrape AFS screenings from the website using BeautifulSoup only.
        Returns empty list if scraping fails.
        """
        try:
            all_events = []
            urls_to_try = [
                f"{self.base_url}/screenings/",
                f"{self.base_url}/calendar/",
                f"{self.base_url}/",  # Main page as fallback
            ]
            for url in urls_to_try:
                try:
                    response = self.session.get(url, timeout=15, allow_redirects=True)
                    if response.status_code == 200:
                        soup = BeautifulSoup(response.text, "html.parser")
                        # If this is a movie page (contains showtime selectors/displays), extract events directly
                        if soup.select(".c-showtime-select__trigger") or soup.select(
                            "div.c-showtime-display"
                        ):
                            # --- BEGIN MOVIE PAGE EXTRACTION ---
                            movie_soup = soup
                            # Title
                            title_elem = movie_soup.find("h1")
                            if not title_elem:
                                title_elem = movie_soup.find("h2")
                            title = (
                                title_elem.get_text(strip=True) if title_elem else None
                            )
                            # Director
                            director = None
                            director_elem = movie_soup.find(
                                string=re.compile(r"Directed by ", re.I)
                            )
                            if director_elem:
                                match = re.search(
                                    r"Directed by ([^\n\r<]+)", director_elem
                                )
                                if match:
                                    director = match.group(1).strip()
                            # Year, Country, Language, Duration
                            info_elem = movie_soup.find("p", class_="t-smaller")
                            year = None
                            country = None
                            language = None
                            duration = None
                            if info_elem:
                                info_text = info_elem.get_text()
                                parts = [p.strip() for p in info_text.split(",")]
                                if len(parts) > 0:
                                    country = parts[0]
                                if len(parts) > 1:
                                    try:
                                        year = int(parts[1])
                                    except Exception:
                                        year = None
                                if len(parts) > 2:
                                    duration = parts[2]
                                for part in parts:
                                    if (
                                        "English" in part
                                        or "French" in part
                                        or "Spanish" in part
                                    ):
                                        language = (
                                            part.replace("In ", "")
                                            .replace("with English subtitles", "")
                                            .strip()
                                        )
                            # Description
                            desc_elem = movie_soup.find(
                                "div", class_="c-screening-content"
                            )
                            description = (
                                desc_elem.get_text(separator=" ", strip=True)
                                if desc_elem
                                else None
                            )
                            # Showtimes
                            date_map = {}
                            for li in movie_soup.select(".c-showtime-select__trigger"):
                                data_target = li.get("data-target")
                                if data_target and len(data_target) == 8:
                                    date_fmt = f"{data_target[:4]}-{data_target[4:6]}-{data_target[6:]}"
                                    date_map[data_target] = date_fmt
                            if not date_map:
                                for div in movie_soup.select("div.c-showtime-display"):
                                    div_id = div.get("id", "")
                                    if (
                                        div_id.startswith("showtime-")
                                        and len(div_id) == 17
                                    ):
                                        data_target = div_id.replace("showtime-", "")
                                        if len(data_target) == 8:
                                            date_fmt = f"{data_target[:4]}-{data_target[4:6]}-{data_target[6:]}"
                                            date_map[data_target] = date_fmt
                            events = []
                            for data_target, date_fmt in date_map.items():
                                showtime_div = movie_soup.find(
                                    "div", id=f"showtime-{data_target}"
                                )
                                if showtime_div:
                                    time_buttons = showtime_div.find_all(
                                        "a", class_="c-button"
                                    )
                                    for btn in time_buttons:
                                        time_str = btn.get_text(strip=True)
                                        if not time_str:
                                            continue
                                        event = {
                                            "title": title,
                                            "director": director,
                                            "year": year,
                                            "country": country,
                                            "language": language,
                                            "duration": duration,
                                            "date": date_fmt,
                                            "time": time_str,
                                            "venue": "AFS Cinema",
                                            "type": "movie",
                                            "description": description,
                                            "url": url,
                                        }
                                        events.append(event)
                            if events:
                                all_events.extend(events)
                                break
                            # --- END MOVIE PAGE EXTRACTION ---
                        # Otherwise, treat as calendar/screenings page and find movie links
                        event_links = soup.find_all("a", href=True)
                        movie_urls = []
                        for link in event_links:
                            href = link.get("href", "")
                            if "/screening/" in href:
                                if href.startswith("/"):
                                    href = f"{self.base_url}{href}"
                                elif not href.startswith("http"):
                                    href = f"{self.base_url}/{href}"
                                if href not in movie_urls:
                                    movie_urls.append(href)
                        for movie_url in movie_urls[:10]:
                            try:
                                movie_response = self.session.get(movie_url, timeout=10)
                                if movie_response.status_code == 200:
                                    movie_soup = BeautifulSoup(
                                        movie_response.text, "html.parser"
                                    )
                                    title_elem = movie_soup.find("h1")
                                    if not title_elem:
                                        title_elem = movie_soup.find("h2")
                                    title = (
                                        title_elem.get_text(strip=True)
                                        if title_elem
                                        else None
                                    )
                                    director = None
                                    director_elem = movie_soup.find(
                                        string=re.compile(r"Directed by ", re.I)
                                    )
                                    if director_elem:
                                        match = re.search(
                                            r"Directed by ([^\n\r<]+)", director_elem
                                        )
                                        if match:
                                            director = match.group(1).strip()
                                    info_elem = movie_soup.find("p", class_="t-smaller")
                                    year = None
                                    country = None
                                    language = None
                                    duration = None
                                    if info_elem:
                                        info_text = info_elem.get_text()
                                        parts = [
                                            p.strip() for p in info_text.split(",")
                                        ]
                                        if len(parts) > 0:
                                            country = parts[0]
                                        if len(parts) > 1:
                                            try:
                                                year = int(parts[1])
                                            except Exception:
                                                year = None
                                        if len(parts) > 2:
                                            duration = parts[2]
                                        for part in parts:
                                            if (
                                                "English" in part
                                                or "French" in part
                                                or "Spanish" in part
                                            ):
                                                language = (
                                                    part.replace("In ", "")
                                                    .replace(
                                                        "with English subtitles", ""
                                                    )
                                                    .strip()
                                                )
                                    desc_elem = movie_soup.find(
                                        "div", class_="c-screening-content"
                                    )
                                    description = (
                                        desc_elem.get_text(separator=" ", strip=True)
                                        if desc_elem
                                        else None
                                    )
                                    date_map = {}
                                    for li in movie_soup.select(
                                        ".c-showtime-select__trigger"
                                    ):
                                        data_target = li.get("data-target")
                                        if data_target and len(data_target) == 8:
                                            date_fmt = f"{data_target[:4]}-{data_target[4:6]}-{data_target[6:]}"
                                            date_map[data_target] = date_fmt
                                    if not date_map:
                                        for div in movie_soup.select(
                                            "div.c-showtime-display"
                                        ):
                                            div_id = div.get("id", "")
                                            if (
                                                div_id.startswith("showtime-")
                                                and len(div_id) == 17
                                            ):
                                                data_target = div_id.replace(
                                                    "showtime-", ""
                                                )
                                                if len(data_target) == 8:
                                                    date_fmt = f"{data_target[:4]}-{data_target[4:6]}-{data_target[6:]}"
                                                    date_map[data_target] = date_fmt
                                    events = []
                                    for data_target, date_fmt in date_map.items():
                                        showtime_div = movie_soup.find(
                                            "div", id=f"showtime-{data_target}"
                                        )
                                        if showtime_div:
                                            time_buttons = showtime_div.find_all(
                                                "a", class_="c-button"
                                            )
                                            for btn in time_buttons:
                                                time_str = btn.get_text(strip=True)
                                                if not time_str:
                                                    continue
                                                event = {
                                                    "title": title,
                                                    "director": director,
                                                    "year": year,
                                                    "country": country,
                                                    "language": language,
                                                    "duration": duration,
                                                    "date": date_fmt,
                                                    "time": time_str,
                                                    "venue": "AFS Cinema",
                                                    "type": "movie",
                                                    "description": description,
                                                    "url": movie_url,
                                                }
                                                events.append(event)
                                    if events:
                                        all_events.extend(events)
                            except Exception as e:
                                continue
                        if all_events:
                            break
                except Exception as e:
                    continue
            return all_events
        except Exception as e:
            return []
