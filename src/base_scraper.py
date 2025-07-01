"""
Simple base scraper class for adhoc venue scrapers
"""

import os
import requests
from abc import ABC, abstractmethod
from typing import Dict, List

from dotenv import load_dotenv
from src.llm_service import LLMService

load_dotenv()


class BaseScraper(ABC):
    """
    Simple base scraper class.
    Each venue scraper implements its own adhoc scraping logic.
    """

    def __init__(self, base_url: str, venue_name: str):
        self.base_url = base_url
        self.venue_name = venue_name

        # Initialize HTTP session
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Cache-Control": "max-age=0",
            }
        )

        # Initialize LLM service
        self.llm_service = LLMService()

        print(f"Initialized {self.__class__.__name__} for {venue_name}")
        if not self.llm_service.anthropic:
            print(
                "  Warning: LLM service not configured - Smart extraction unavailable"
            )

    @abstractmethod
    def scrape_events(self) -> List[Dict]:
        """
        Each scraper implements its own adhoc scraping logic.
        Returns list of events in standard format.
        """
        pass
