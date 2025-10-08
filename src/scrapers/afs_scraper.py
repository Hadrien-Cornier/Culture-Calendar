"""
Austin Movie Society scraper - scrapes events from website
"""

import re
from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from src.base_scraper import BaseScraper


class AFSScraper(BaseScraper):
    """Austin Movie Society scraper - extracts movie screenings from website."""

    def __init__(self, config=None, venue_key='afs'):
        super().__init__(
            base_url="https://www.austinfilm.org", 
            venue_name="Austin Movie Society",
            venue_key=venue_key,
            config=config
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
                                # Extract languages from the full info text (handles multi-language entries)
                                language = self._parse_languages_from_info(info_text, country)
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
                                        # Build event in snake_case format
                                        event = {
                                            "title": title,
                                            "director": director,
                                            "release_year": year,  # Changed from "year" to "release_year" per template
                                            "country": country,
                                            "language": language,
                                            "runtime_minutes": self._parse_duration_to_minutes(duration),  # Convert to minutes
                                            "dates": [date_fmt],  # Use dates array
                                            "times": [time_str],  # Use times array
                                            "venue": "AFS Cinema",
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
                        for movie_url in movie_urls:  # Increased limit to get more movies
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
                                        # Extract languages from the full info text (handles multi-language entries)
                                        language = self._parse_languages_from_info(info_text, country)
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
                                                # Build event in snake_case format
                                                event = {
                                                    "title": title,
                                                    "director": director,
                                                    "release_year": year,  # Changed from "year" to "release_year" per template
                                                    "country": country,
                                                    "language": language,
                                                    "runtime_minutes": self._parse_duration_to_minutes(duration),  # Convert to minutes
                                                    "dates": [date_fmt],  # Use dates array
                                                    "times": [time_str],  # Use times array
                                                    "venue": "AFS Cinema",
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
    
    def _parse_duration_to_minutes(self, duration_str):
        """Parse duration string into total minutes.

        Supports common formats found on AFS pages, including:
        - "1h 38min", "2h 8min", "1 h 38 m"
        - "1 hr 50 min", "2 hrs, 5 mins"
        - "90 min", "105m", "120 minutes"
        - "1:50" (hh:mm)
        - "2h" (hours only) or "45m" (minutes only)
        Returns an integer number of minutes, or None when unparseable.
        """
        if duration_str is None:
            return None

        text = str(duration_str).strip()
        if not text:
            return None

        s = text.lower()
        # Normalize punctuation/abbreviations
        s = s.replace("\u00A0", " ")  # non-breaking space
        s = s.replace(".", "")
        s = s.replace("mins", "min")
        s = s.replace("minutes", "min")
        s = s.replace("hrs", "hr")

        # 1) hh:mm format
        m = re.fullmatch(r"\s*(\d{1,2})\s*:\s*(\d{1,2})\s*", s)
        if m:
            hours = int(m.group(1))
            minutes = int(m.group(2))
            return hours * 60 + minutes

        # 2) Explicit hours and/or minutes tokens
        hours = 0
        minutes = 0

        mh = re.search(r"(\d+)\s*(?:h|hr|hour)\b", s)
        if mh:
            hours = int(mh.group(1))

        mm = re.search(r"(\d+)\s*(?:m|min)\b", s)
        if mm:
            minutes = int(mm.group(1))

        if mh or mm:
            return hours * 60 + minutes

        # 3) Compact hour-minute without trailing unit on minutes (e.g., "1h 50")
        m = re.search(r"(\d+)\s*h\s*(\d{1,2})\b", s)
        if m:
            return int(m.group(1)) * 60 + int(m.group(2))

        # 4) Bare number interpreted as minutes (e.g., "90")
        m = re.fullmatch(r"\s*(\d{2,3})\s*", s)
        if m:
            return int(m.group(1))

        return None

    def _parse_languages_from_info(self, info_text: str, country: Optional[str]) -> Optional[str]:
        """Extract language(s) from the info text.

        Examples handled:
        - "In French with English subtitles" -> "French"
        - "In German, English, and Romany with English subtitles." -> "German, English, Romany"
        - "In Spanish" -> "Spanish"
        If no language is specified and the country is USA/UK, default to English
        as an explicit business requirement.
        """
        if not info_text:
            # Business requirement: default language to English for USA/UK when unspecified
            if country and str(country).strip().lower() in {
                "usa",
                "united states",
                "us",
                "u.s.",
                "u.s.a.",
                "united states of america",
                "america",
                "uk",
                "u.k.",
                "united kingdom",
                "england",
                "great britain",
                "britain",
            }:
                return "English"
            return None

        s = info_text.replace("\u00A0", " ")
        # Look for a segment beginning with "In "
        m = re.search(r"\bIn\s+(.+)$", s, re.IGNORECASE)
        lang_segment = None
        if m:
            lang_segment = m.group(1)
            # Cut off subtitles or trailing punctuation after languages
            lang_segment = re.split(r"\s+with\s+[^.]*?subtitles?", lang_segment, flags=re.IGNORECASE)[0]
            lang_segment = re.split(r"[.;\n\r]", lang_segment)[0]

        if lang_segment:
            # Tokenize on commas, slashes, ampersands and the word 'and'
            tokens = re.split(r",|/|&|\band\b", lang_segment, flags=re.IGNORECASE)
            cleaned: list[str] = []
            for token in tokens:
                t = token.strip()
                if not t:
                    continue
                # Remove leading 'In '
                t = re.sub(r"^in\s+", "", t, flags=re.IGNORECASE)
                # Remove residual punctuation
                t = t.strip(" .")
                if not t:
                    continue
                # Skip known non-language tokens
                if t.lower() in {"dcp"}:
                    continue
                cleaned.append(t)
            if cleaned:
                # Title-case languages and deduplicate preserving order
                result: list[str] = []
                seen: set[str] = set()
                for t in cleaned:
                    name = re.sub(r"\s+", " ", t).strip().title()
                    key = name.lower()
                    if key not in seen:
                        seen.add(key)
                        result.append(name)
                if result:
                    return ", ".join(result)

        # Business requirement: default English for USA/UK when language not specified
        if country and str(country).strip().lower() in {
            "usa",
            "united states",
            "us",
            "u.s.",
            "u.s.a.",
            "united states of america",
            "america",
            "uk",
            "u.k.",
            "united kingdom",
            "england",
            "great britain",
            "britain",
        }:
            return "English"

        return None
