#!/usr/bin/env python3
"""
Comprehensive Austin Film Society Scraper
Step 1: Extract all screening URLs from calendar
Step 2: Follow each URL to get detailed movie information
Filters out film festivals and extracts structured data
"""

from bs4 import BeautifulSoup
import json
import re
import requests
from datetime import datetime
from typing import Dict, List, Optional
import time


class ComprehensiveAFSScraper:
    """Comprehensive scraper for Austin Film Society"""

    def __init__(self):
        self.base_url = "https://www.austinfilm.org"
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
        )

    def extract_screening_urls(self, html_file_path: str) -> List[Dict]:
        """Step 1: Extract all screening URLs from calendar HTML"""
        with open(html_file_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        soup = BeautifulSoup(html_content, "html.parser")
        screening_links = soup.find_all("a", class_="afs_screening_link")

        screenings = []
        for link in screening_links:
            title = link.get_text().strip()
            url = link.get("href", "")

            # Filter out film festivals
            if self._is_film_festival(title):
                print(f"🚫 Skipping film festival: {title}")
                continue

            screenings.append({"title": title, "url": url})

        return screenings

    def _is_film_festival(self, title: str) -> bool:
        """Check if title indicates a film festival"""
        festival_keywords = [
            "film festival",
            "festival day",
            "austin asian american film festival",
            "pan african film festival",
            "sxsw",
        ]

        title_lower = title.lower()
        return any(keyword in title_lower for keyword in festival_keywords)

    def parse_movie_page(self, html_content: str, url: str = "") -> Optional[Dict]:
        """Step 2: Parse individual movie page to extract detailed information"""
        soup = BeautifulSoup(html_content, "html.parser")

        try:
            # Extract basic movie info
            title = self._extract_title(soup)
            if not title:
                return None

            # Check if this is actually a festival page (double-check)
            if self._is_film_festival(title):
                return None

            director = self._extract_director(soup)
            year, country = self._extract_year_country(soup)
            language = self._extract_language(soup)
            duration = self._extract_duration(soup)
            dates, times = self._extract_showtimes(soup)
            venue = self._extract_venue(soup)
            description = self._extract_description(soup)
            is_special_screening = self._is_special_screening(soup)

            return {
                "title": title,
                "director": director,
                "year": year,
                "country": country,
                "language": language,
                "duration": duration,
                "dates": dates,
                "times": times,
                "venue": venue,
                "description": description,
                "is_special_screening": is_special_screening,
                "url": url,
            }

        except Exception as e:
            print(f"❌ Error parsing movie page: {e}")
            return None

    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract movie title"""
        # Try multiple selectors for title
        title_selectors = ["h1", ".c-screening-data h1", "h1.c-screening__title"]

        for selector in title_selectors:
            element = soup.select_one(selector)
            if element:
                title = element.get_text().strip()
                if title and title != "Austin Film Society":
                    return title

        return None

    def _extract_director(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract director name"""
        # Look for "Directed by" text
        directed_patterns = [
            r"Directed by (.+?)(?:\n|$|<)",
            r"Director[:\s]+(.+?)(?:\n|$|<)",
        ]

        text = soup.get_text()
        for pattern in directed_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        return None

    def _extract_year_country(self, soup: BeautifulSoup) -> tuple:
        """Extract year and country from movie info line"""
        # Look for movie metadata in the screening data section
        screening_data = soup.find(class_="c-screening-data")
        if screening_data:
            # Look for the small text that usually contains "Country, Year"
            small_elements = screening_data.find_all(
                ["p", "span"], class_=["t-smaller", "t-small"]
            )

            for element in small_elements:
                text = element.get_text().strip()
                # Pattern: Country, Year, duration, etc.
                pattern = r"([A-Za-z\s]+),\s*(\d{4})"
                match = re.search(pattern, text)
                if match:
                    country = match.group(1).strip()
                    year = match.group(2).strip()

                    # Filter out director names and other non-countries
                    if (
                        len(country) <= 20
                        and not any(
                            x in country.lower()
                            for x in ["directed", "director", "min", "dcp"]
                        )
                        and country not in ["PM", "AM"]
                    ):
                        try:
                            return int(year), country
                        except ValueError:
                            continue

        return None, None

    def _extract_language(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract language information"""
        text = soup.get_text()

        # Look for language patterns
        language_patterns = [
            r"In (\w+) with",
            r"(\w+) with English subtitles",
            r"Language[:\s]+(\w+)",
        ]

        for pattern in language_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        return None

    def _extract_duration(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract movie duration"""
        text = soup.get_text()

        # Look for duration patterns
        duration_patterns = [
            r"(\d+h\s*\d+min)",
            r"(\d+\s*min)",
            r"(\d+:\d+)",
            r"Runtime[:\s]+(\d+\s*min)",
        ]

        for pattern in duration_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        return None

    def _extract_showtimes(self, soup: BeautifulSoup) -> tuple:
        """Extract dates and times from showtimes section"""
        dates = []
        times = []

        # Look for showtime displays
        showtime_displays = soup.find_all("div", class_="c-showtime-display")

        for display in showtime_displays:
            # Extract date from ID (e.g., "showtime-20250627")
            display_id = display.get("id", "")
            date_match = re.search(r"showtime-(\d{8})", display_id)
            if date_match:
                date_str = date_match.group(1)
                # Convert YYYYMMDD to YYYY-MM-DD
                formatted_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
                dates.append(formatted_date)

            # Extract time from button
            time_button = display.find("a", class_="c-button")
            if time_button:
                time_text = time_button.get_text().strip()
                times.append(time_text)

        # If no structured showtimes found, try to extract from text
        if not dates or not times:
            text = soup.get_text()

            # Look for date patterns
            date_patterns = [
                r"(\w{3},\s*\w{3}\s*\d{1,2})",  # "Fri, Jun 27"
                r"(\w{3}\s*\d{1,2})",  # "Jun 27"
            ]

            for pattern in date_patterns:
                matches = re.findall(pattern, text)
                dates.extend(matches)

            # Look for time patterns
            time_patterns = [
                r"(\d{1,2}:\d{2}\s*[AP]M)",
                r"(\d{1,2}\s*[AP]M)",
            ]

            for pattern in time_patterns:
                matches = re.findall(pattern, text)
                times.extend(matches)

        return dates, times

    def _extract_venue(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract venue information"""
        # Look for venue label
        venue_element = soup.find(class_="c-screening__venue-label")
        if venue_element:
            return venue_element.get_text().strip()

        # Default to AFS Cinema if not found
        return "AFS Cinema"

    def _extract_description(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract movie description"""
        # Look for screening content
        content_element = soup.find(class_="c-screening-content")
        if content_element:
            # Get all paragraphs and clean them
            paragraphs = content_element.find_all("p")
            description_parts = []

            for p in paragraphs:
                text = p.get_text().strip()
                if text and not text.startswith('"') and len(text) > 20:
                    description_parts.append(text)

            if description_parts:
                # Normalize newlines and spaces
                description = " ".join(description_parts)
                # Replace multiple spaces with single space
                description = re.sub(r'\s+', ' ', description)
                # Normalize quotes
                description = description.replace('"', '"').replace('"', '"')
                description = description.replace(''', "'").replace(''', "'")
                return description.strip()

        return None

    def _is_special_screening(self, soup: BeautifulSoup) -> bool:
        """Determine if this is a special screening"""
        text = soup.get_text().lower()

        # More specific keywords that indicate special events
        special_keywords = [
            "q&a",
            "special screening",
            "premiere",
            "free member monday",
            "opening night",
            "closing night",
            "filmmaker will be present",
            "director will be present",
            "with filmmaker",
            "with director",
            "conversation with",
            "followed by discussion",
        ]

        return any(keyword in text for keyword in special_keywords)

    def scrape_from_files(
        self, calendar_file: str, movie_files: List[str] = None
    ) -> List[Dict]:
        """Scrape from local HTML files (for testing)"""
        print("🎬 Starting comprehensive AFS scraping from files...")

        # Step 1: Extract URLs from calendar
        screenings = self.extract_screening_urls(calendar_file)
        print(f"📋 Found {len(screenings)} potential screenings")

        results = []

        # If movie files provided, use them
        if movie_files:
            for i, movie_file in enumerate(movie_files):
                if i < len(screenings):
                    print(f"🔍 Parsing movie file: {movie_file}")

                    with open(movie_file, "r", encoding="utf-8") as f:
                        html_content = f.read()

                    movie_data = self.parse_movie_page(
                        html_content, screenings[i]["url"]
                    )
                    if movie_data:
                        results.append(movie_data)
                        print(f"✅ Extracted: {movie_data['title']}")
                    else:
                        print(f"❌ Failed to extract from {movie_file}")

        return results

    def scrape_live(self, calendar_file: str, max_movies: int = 10) -> List[Dict]:
        """Scrape live from URLs (downloads movie pages)"""
        print("🎬 Starting live comprehensive AFS scraping...")

        # Step 1: Extract URLs from calendar
        screenings = self.extract_screening_urls(calendar_file)
        print(f"📋 Found {len(screenings)} potential screenings")

        results = []

        # Step 2: Follow URLs and parse movie pages
        for i, screening in enumerate(screenings[:max_movies]):
            print(
                f"🔍 Fetching movie page {i+1}/{min(len(screenings), max_movies)}: {screening['url']}"
            )

            try:
                response = self.session.get(screening["url"])
                response.raise_for_status()

                movie_data = self.parse_movie_page(response.text, screening["url"])
                if movie_data:
                    results.append(movie_data)
                    print(f"✅ Extracted: {movie_data['title']}")
                else:
                    print(f"❌ Failed to extract from {screening['url']}")

                # Be respectful with delays
                time.sleep(1)

            except Exception as e:
                print(f"❌ Error fetching {screening['url']}: {e}")
                continue

        return results


def main():
    scraper = ComprehensiveAFSScraper()

    # Test with local files first
    calendar_file = "austinfilm_calendar.html"
    movie_files = ["gwen_movie_page.html"]  # Add more as needed

    results = scraper.scrape_from_files(calendar_file, movie_files)

    # Save results
    output_file = "comprehensive_afs_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Saved {len(results)} movies to {output_file}")

    # Display results
    for movie in results:
        print(f"\n🎬 {movie['title']}")
        if movie["director"]:
            print(f"   Director: {movie['director']}")
        if movie["year"]:
            print(f"   Year: {movie['year']}")
        if movie["country"]:
            print(f"   Country: {movie['country']}")
        if movie["dates"]:
            print(f"   Dates: {', '.join(movie['dates'])}")
        if movie["times"]:
            print(f"   Times: {', '.join(movie['times'])}")


if __name__ == "__main__":
    main()
