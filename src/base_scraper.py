"""
Base scraper class with progressive fallback system and LLM-powered extraction
"""

import os
import time
import asyncio
import hashlib
from typing import Dict, List, Optional, Union, Any
from datetime import datetime, timedelta
from abc import ABC, abstractmethod

import requests
from pyppeteer import launch
from firecrawl import FirecrawlApp
from dotenv import load_dotenv

from src.llm_service import LLMService

load_dotenv()


class ScrapingTier:
    """Enumeration of scraping tiers"""
    REQUESTS_LLM = "requests_llm"
    PYPPETEER = "pyppeteer"
    FIRECRAWL = "firecrawl"
    FALLBACK = "fallback"


class BaseScraper(ABC):
    """
    Base scraper class with progressive fallback system.
    All venue scrapers should inherit from this class.
    """
    
    def __init__(self, base_url: str, venue_name: str):
        self.base_url = base_url
        self.venue_name = venue_name
        
        # Initialize HTTP session
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        
        # Initialize LLM service
        self.llm_service = LLMService()
        
        # Initialize Firecrawl client
        firecrawl_api_key = os.getenv('FIRECRAWL_API_KEY')
        self.firecrawl = FirecrawlApp(api_key=firecrawl_api_key) if firecrawl_api_key else None
        
        # Content cache for avoiding redundant fetches
        self.content_cache = {}
        
        # Configuration
        self.max_retries = 3
        self.base_delay = 1.0  # Base delay between requests
        self.max_delay = 60.0  # Maximum delay for exponential backoff
        
        print(f"Initialized {self.__class__.__name__} for {venue_name}")
        if not self.firecrawl:
            print("  Warning: Firecrawl not configured - Tier 4 fallback unavailable")
        if not self.llm_service.anthropic:
            print("  Warning: LLM service not configured - Smart extraction unavailable")
    
    @abstractmethod
    def get_target_urls(self) -> List[str]:
        """Return list of URLs to scrape for this venue"""
        pass
    
    @abstractmethod
    def get_data_schema(self) -> Dict:
        """Return the expected data schema for this venue"""
        pass
    
    @abstractmethod
    def get_fallback_data(self) -> List[Dict]:
        """Return fallback data when all scraping methods fail"""
        pass
    
    def scrape_events(self, use_cache: bool = True) -> List[Dict]:
        """
        Main scraping method with progressive fallback system
        
        Args:
            use_cache: Whether to use cached content
            
        Returns:
            List of extracted events
        """
        all_events = []
        target_urls = self.get_target_urls()
        
        print(f"Scraping {len(target_urls)} URLs for {self.venue_name}")
        
        for url in target_urls:
            events = self._scrape_single_url(url, use_cache)
            all_events.extend(events)
            
            # Respectful delay between URLs
            if len(target_urls) > 1:
                time.sleep(self.base_delay)
        
        print(f"Extracted {len(all_events)} events from {self.venue_name}")
        return all_events
    
    def _scrape_single_url(self, url: str, use_cache: bool = True) -> List[Dict]:
        """Scrape a single URL using progressive fallback"""
        
        # Check cache first
        cache_key = self._create_cache_key(url)
        if use_cache and cache_key in self.content_cache:
            cached_data = self.content_cache[cache_key]
            if self._is_cache_valid(cached_data):
                print(f"Using cached data for {url}")
                return cached_data['events']
        
        # Progressive fallback through tiers (skip Tier 1 for simplicity)
        tiers = [
            (ScrapingTier.REQUESTS_LLM, self._scrape_with_requests_llm),
            (ScrapingTier.PYPPETEER, self._scrape_with_pyppeteer),
            (ScrapingTier.FIRECRAWL, self._scrape_with_firecrawl),
            (ScrapingTier.FALLBACK, self._scrape_with_fallback)
        ]
        
        for tier_name, scraper_func in tiers:
            try:
                print(f"Trying {tier_name} for {url}")
                
                # Apply exponential backoff for retries
                for attempt in range(self.max_retries):
                    try:
                        result = scraper_func(url)
                        
                        if result and self._validate_extraction_result(result):
                            print(f"✓ {tier_name} succeeded for {url}")
                            
                            # Cache the result
                            self.content_cache[cache_key] = {
                                'events': result,
                                'timestamp': datetime.now().isoformat(),
                                'tier': tier_name,
                                'url': url
                            }
                            
                            return result
                        
                    except Exception as e:
                        print(f"  Attempt {attempt + 1} failed: {e}")
                        
                        if attempt < self.max_retries - 1:
                            delay = min(self.base_delay * (2 ** attempt), self.max_delay)
                            print(f"  Retrying in {delay:.1f}s...")
                            time.sleep(delay)
                
                print(f"✗ {tier_name} failed after {self.max_retries} attempts")
                
            except Exception as e:
                print(f"✗ {tier_name} failed with error: {e}")
        
        # If all tiers failed, return empty list
        print(f"All scraping tiers failed for {url}")
        return []
    
    def _scrape_with_requests_llm(self, url: str) -> List[Dict]:
        """Tier 2: Requests + LLM extraction"""
        response = self.session.get(url, timeout=30)
        response.raise_for_status()
        
        # Use LLM to extract data from HTML
        schema = self.get_data_schema()
        extraction_result = self.llm_service.extract_data(
            content=response.text,
            schema=schema,
            url=url,
            content_type="html"
        )
        
        if extraction_result['success']:
            # Validate extraction
            validation_result = self.llm_service.validate_extraction(
                extracted_data=extraction_result['data'],
                schema=schema,
                original_content=response.text[:2000]  # Truncate for validation
            )
            
            if validation_result['is_valid']:
                events = self._format_extraction_result(extraction_result['data'], url)
                if events:
                    return events
                else:
                    print(f"  LLM extraction succeeded but produced no events - data: {extraction_result['data']}")
                    return []
            else:
                print(f"  LLM validation failed: {validation_result['reason']}")
                return []
        else:
            print(f"  LLM extraction failed: {extraction_result['error']}")
            if 'No useful data extracted' in extraction_result.get('error', ''):
                print(f"    Raw response: {extraction_result.get('raw_response', 'N/A')[:200]}...")
            return []
    
    def _scrape_with_pyppeteer(self, url: str) -> List[Dict]:
        """Tier 3: Pyppeteer + LLM extraction"""
        
        async def fetch_with_browser():
            browser = await launch(headless=True, args=['--no-sandbox'])
            page = await browser.newPage()
            await page.goto(url, {'waitUntil': 'networkidle2'})
            content = await page.content()
            await browser.close()
            return content
        
        # Get content with browser
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            html_content = loop.run_until_complete(fetch_with_browser())
        finally:
            try:
                loop.close()
            except Exception:
                pass
        
        # Use LLM to extract data
        schema = self.get_data_schema()
        extraction_result = self.llm_service.extract_data(
            content=html_content,
            schema=schema,
            url=url,
            content_type="html"
        )
        
        if extraction_result['success']:
            # Validate extraction
            validation_result = self.llm_service.validate_extraction(
                extracted_data=extraction_result['data'],
                schema=schema,
                original_content=html_content[:2000]
            )
            
            if validation_result['is_valid']:
                events = self._format_extraction_result(extraction_result['data'], url)
                if events:
                    return events
                else:
                    print(f"  LLM extraction succeeded but produced no events - data: {extraction_result['data']}")
                    return []
            else:
                print(f"  LLM validation failed: {validation_result['reason']}")
                return []
        else:
            print(f"  LLM extraction failed: {extraction_result['error']}")
            if 'No useful data extracted' in extraction_result.get('error', ''):
                print(f"    Raw response: {extraction_result.get('raw_response', 'N/A')[:200]}...")
            return []
    
    def _scrape_with_firecrawl(self, url: str) -> List[Dict]:
        """Tier 4: Firecrawl + LLM extraction"""
        if not self.firecrawl:
            raise Exception("Firecrawl not configured")
        
        # Scrape with Firecrawl
        scrape_result = self.firecrawl.scrape_url(url, params={'formats': ['markdown', 'html']})
        
        if not scrape_result:
            raise Exception("Firecrawl returned no data")
        
        # Try markdown first, then HTML
        content = scrape_result.get('markdown') or scrape_result.get('html') or scrape_result.get('content')
        content_type = 'markdown' if scrape_result.get('markdown') else 'html'
        
        if not content:
            raise Exception("Firecrawl returned no usable content")
        
        # Use LLM to extract data
        schema = self.get_data_schema()
        extraction_result = self.llm_service.extract_data(
            content=content,
            schema=schema,
            url=url,
            content_type=content_type
        )
        
        if extraction_result['success']:
            # Validate extraction
            validation_result = self.llm_service.validate_extraction(
                extracted_data=extraction_result['data'],
                schema=schema,
                original_content=content[:2000]
            )
            
            if validation_result['is_valid']:
                events = self._format_extraction_result(extraction_result['data'], url)
                if events:
                    return events
                else:
                    print(f"  LLM extraction succeeded but produced no events - data: {extraction_result['data']}")
                    return []
            else:
                print(f"  LLM validation failed: {validation_result['reason']}")
                return []
        else:
            print(f"  LLM extraction failed: {extraction_result['error']}")
            if 'No useful data extracted' in extraction_result.get('error', ''):
                print(f"    Raw response: {extraction_result.get('raw_response', 'N/A')[:200]}...")
            return []
    
    def _scrape_with_fallback(self, url: str) -> List[Dict]:
        """Tier 5: Fallback to static data"""
        print(f"Using fallback data for {url}")
        return self.get_fallback_data()
    
    def _format_extraction_result(self, extracted_data: Union[Dict, List], url: str) -> List[Dict]:
        """Format LLM extraction result into standard event format"""
        events = []
        
        # Handle both single events and lists of events
        if isinstance(extracted_data, dict):
            # Single event
            event = self._standardize_event_data(extracted_data, url)
            if event:
                events.append(event)
        elif isinstance(extracted_data, list):
            # Multiple events
            for event_data in extracted_data:
                if isinstance(event_data, dict):
                    event = self._standardize_event_data(event_data, url)
                    if event:
                        events.append(event)
        
        return events
    
    def _standardize_event_data(self, event_data: Dict, url: str) -> Optional[Dict]:
        """Standardize event data format"""
        try:
            # Ensure required fields exist
            if not event_data.get('title'):
                return None
            
            # Standardize the event format - use None for missing data
            standardized = {
                'title': str(event_data.get('title', '')).strip(),
                'url': url,
                'date': event_data.get('date') or None,
                'time': event_data.get('time') or None,
                'venue': self.venue_name,
                'location': event_data.get('location') or None,
                'type': event_data.get('type') or None,
                'description': event_data.get('description') or None,
            }
            
            # Add venue-specific fields
            for key, value in event_data.items():
                if key not in standardized:
                    standardized[key] = value
            
            return standardized
            
        except Exception as e:
            print(f"Error standardizing event data: {e}")
            return None
    
    def _validate_extraction_result(self, events: List[Dict]) -> bool:
        """Validate that extraction result is reasonable"""
        if not isinstance(events, list):
            return False
        
        if len(events) == 0:
            return False
        
        # Check that events have required fields
        for event in events:
            if not isinstance(event, dict):
                return False
            if not event.get('title'):
                return False
        
        return True
    
    def _create_cache_key(self, url: str) -> str:
        """Create cache key for URL"""
        return hashlib.md5(url.encode('utf-8')).hexdigest()
    
    def _is_cache_valid(self, cached_data: Dict, max_age_hours: int = 24) -> bool:
        """Check if cached data is still valid"""
        try:
            timestamp = datetime.fromisoformat(cached_data['timestamp'])
            age = datetime.now() - timestamp
            return age < timedelta(hours=max_age_hours)
        except:
            return False
    
    def clear_cache(self):
        """Clear the content cache"""
        self.content_cache.clear()
        print(f"Cache cleared for {self.__class__.__name__}")
    
    def get_cache_stats(self) -> Dict:
        """Get cache statistics"""
        return {
            'cache_size': len(self.content_cache),
            'venue': self.venue_name,
            'entries': list(self.content_cache.keys())
        }