"""
Austin Film Society scraper - scrapes events from website
"""

import re
from datetime import datetime
from typing import Dict, List
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..base_scraper import BaseScraper
from ..schemas import FilmEventSchema


class AFSScraper(BaseScraper):
    """Austin Film Society scraper - extracts film screenings from website."""

    def __init__(self):
        super().__init__(
            base_url="https://www.austinfilm.org", venue_name="Austin Film Society"
        )
        # Set better headers to bypass anti-bot protection  
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0'
        }
        self.session.headers.update(headers)

    def get_target_urls(self) -> List[str]:
        """Return list of URLs to scrape"""
        return [
            f"{self.base_url}/screenings/",
            f"{self.base_url}/calendar/",
        ]

    def get_data_schema(self) -> Dict:
        """Return the expected data schema for AFS film events"""
        return FilmEventSchema.get_schema()

    def scrape_events(self) -> List[Dict]:
        """
        Scrape AFS screenings from the website.
        Returns empty list if scraping fails.
        """
        try:
            all_events = []
            
            # Try multiple URLs
            urls_to_try = [
                f"{self.base_url}/screenings/",
                f"{self.base_url}/calendar/",
                f"{self.base_url}/",  # Main page as fallback
            ]
            
            for url in urls_to_try:
                try:
                    print(f"  Trying {url}")
                    response = self.session.get(url, timeout=15, allow_redirects=True)
                    
                    if response.status_code == 200:
                        print(f"    Got response with {len(response.text)} chars")
                        
                        # Extract movie page URLs from calendar/screenings page
                        from bs4 import BeautifulSoup
                        soup = BeautifulSoup(response.text, 'html.parser')
                        event_links = soup.find_all('a', href=True)
                        movie_urls = []
                        
                        print(f"    Total links found: {len(event_links)}")
                        
                        # Debug: check what hrefs we have
                        sample_hrefs = [link.get('href') for link in event_links[:10]]
                        print(f"    Sample hrefs: {sample_hrefs}")
                        
                        screening_count = 0
                        for link in event_links:
                            href = link.get('href', '')
                            if '/screening/' in href:
                                screening_count += 1
                                # Debug first few links
                                if screening_count <= 3:
                                    print(f"      Found screening link: {href}")
                                
                                if href.startswith('/'):
                                    href = f"{self.base_url}{href}"
                                elif not href.startswith('http'):
                                    href = f"{self.base_url}/{href}"
                                
                                if href not in movie_urls:
                                    movie_urls.append(href)
                                    
                                if len(movie_urls) <= 3:
                                    print(f"        Processed to: {href}")
                        
                        print(f"    Found {screening_count} screening hrefs, {len(movie_urls)} unique URLs")
                        
                        # Scrape first 10 movie pages for events
                        movie_count = 0
                        for movie_url in movie_urls[:10]:  # Limit to first 10 to avoid rate limits
                            try:
                                print(f"    Scraping movie page: {movie_url}")
                                movie_response = self.session.get(movie_url, timeout=10)
                                
                                if movie_response.status_code == 200:
                                    # Try LLM extraction on individual movie page
                                    if hasattr(self, 'llm_service') and self.llm_service.anthropic:
                                        film_schema = self.get_data_schema()
                                        schema = {
                                            "events": {
                                                "type": "array",
                                                "description": "Extract film screening events from AFS movie page. Look for movie title in h1/h2 headers, director in 'Directed by [Name]' text, showtimes in buttons like '9:30 PM'. Extract format info like 'France, 1985, 1h 7min, DCP' for country, year, duration, format.",
                                                "items": film_schema
                                            }
                                        }
                                        
                                        extraction_result = self.llm_service.extract_data(
                                            content=movie_response.text[:15000],
                                            schema=schema,
                                            url=movie_url,
                                            content_type="html"
                                        )
                                        
                                        if extraction_result.get('success'):
                                            data = extraction_result.get('data', {})
                                            llm_events = data.get('events', [])
                                            if llm_events:
                                                print(f"      Extracted {len(llm_events)} events from movie page")
                                                # Add venue and type info
                                                for event in llm_events:
                                                    event['venue'] = event.get('venue', 'Austin Film Society')
                                                    event['type'] = 'film'
                                                    event['location'] = 'AFS Cinema'
                                                    event['url'] = movie_url
                                                all_events.extend(llm_events)
                                                movie_count += 1
                                        
                                        # Add small delay between requests
                                        import time
                                        time.sleep(0.5)
                                        
                            except Exception as e:
                                print(f"      Error scraping {movie_url}: {e}")
                                continue
                        
                        if all_events:
                            print(f"    Successfully scraped {len(all_events)} events from {movie_count} movie pages")
                            break  # Stop trying other URLs if we found events
                except Exception as e:
                    print(f"    Error with {url}: {e}")
                    continue
            
            if all_events:
                print(f"Scraped {len(all_events)} events from AFS")
                return all_events
                
        except Exception as e:
            print(f"AFS scraping failed: {e}")
        
        print("AFS scraping failed - returning empty list")
        return []