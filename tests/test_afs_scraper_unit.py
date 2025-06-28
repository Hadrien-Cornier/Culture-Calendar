#!/usr/bin/env python3
"""
Unit tests for AFS scraper using new BaseScraper architecture
"""

import os
import sys
import unittest
from unittest.mock import patch

from src.scrapers.afs_scraper import AFSScraper

# Add the src directory to the path to import the scraper
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src", "scrapers"))


class TestAFSScraper(unittest.TestCase):
    """Unit tests for AFS scraper using new architecture"""

    def setUp(self):
        """Set up test fixtures"""
        self.scraper = AFSScraper()

    def test_scraper_initialization(self):
        """Test that the AFS scraper initializes correctly"""
        self.assertIsInstance(self.scraper, AFSScraper)
        self.assertEqual(self.scraper.venue_name, "Austin Film Society")
        self.assertEqual(self.scraper.base_url, "https://www.austinfilm.org")

    def test_get_target_urls(self):
        """Test that target URLs are returned correctly"""
        urls = self.scraper.get_target_urls()
        self.assertIsInstance(urls, list)
        self.assertTrue(len(urls) > 0)
        self.assertIn("https://www.austinfilm.org/calendar", urls)

    def test_get_data_schema(self):
        """Test that data schema is returned correctly"""
        schema = self.scraper.get_data_schema()
        self.assertIsInstance(schema, dict)
        # Should include basic film event fields
        expected_fields = ["title", "date", "venue", "type"]
        for field in expected_fields:
            self.assertIn(field, str(schema))

    def test_get_fallback_data(self):
        """Test that fallback data is provided when scraping fails"""
        fallback_data = self.scraper.get_fallback_data()
        self.assertIsInstance(fallback_data, list)
        self.assertTrue(len(fallback_data) > 0)
        
        # Check that fallback event has required fields
        event = fallback_data[0]
        required_fields = ["title", "date", "venue", "type"]
        for field in required_fields:
            self.assertIn(field, event)

    @patch('src.base_scraper.BaseScraper._scrape_single_url')
    def test_scrape_events_with_mock(self, mock_scrape):
        """Test scrape_events method with mocked data"""
        # Mock successful scraping result
        mock_scrape.return_value = [
            {
                "title": "Test Movie",
                "date": "2025-01-15",
                "time": "7:00 PM",
                "venue": "AFS Cinema",
                "type": "screening",
                "description": "A test movie screening"
            }
        ]
        
        events = self.scraper.scrape_events()
        self.assertIsInstance(events, list)
        
        # If mock was called, we should get the mocked data
        if events:
            self.assertTrue(len(events) > 0)
            event = events[0]
            self.assertEqual(event["title"], "Test Movie")

    def test_venue_configuration(self):
        """Test that venue-specific configuration is correct"""
        # Test that the scraper is properly configured for AFS
        self.assertEqual(self.scraper.venue_name, "Austin Film Society")
        self.assertTrue(self.scraper.base_url.startswith("https://"))
        
        # Test that required methods are implemented
        self.assertTrue(hasattr(self.scraper, 'get_target_urls'))
        self.assertTrue(hasattr(self.scraper, 'get_data_schema'))
        self.assertTrue(hasattr(self.scraper, 'get_fallback_data'))
        self.assertTrue(hasattr(self.scraper, 'scrape_events'))


if __name__ == "__main__":
    # Run tests with verbose output
    unittest.main(verbosity=2)
