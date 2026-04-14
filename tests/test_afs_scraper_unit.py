#!/usr/bin/env python3
"""
Unit tests for AFS scraper using real test data from AFS_test_data/
"""

import json
import os
import sys
import unittest
from unittest.mock import patch

# Add the src directory to the path to import the scraper
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.scrapers.afs_scraper import AFSScraper


class TestAFSScraper(unittest.TestCase):
    """Unit tests for AFS scraper using real HTML test data"""

    def setUp(self):
        """Set up test fixtures"""
        self.scraper = AFSScraper()
        self.test_data_dir = os.path.join(os.path.dirname(__file__), "AFS_test_data")

        # Load test database
        with open(
            os.path.join(self.test_data_dir, "afs_scraper_test_database.json"), "r"
        ) as f:
            self.test_database = json.load(f)

    def _load_test_html(self, filename):
        """Helper method to load HTML test files"""
        file_path = os.path.join(self.test_data_dir, filename)
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()

    def _assert_extracted_data_matches_expected(self, actual, expected, test_case_name):
        """Helper: compare scraper output against expected fixture.

        Scraper emits arrays (`dates`, `times`) and snake_case template fields
        (`release_year`, `runtime_minutes`). Fixtures use legacy names
        (`year`, `duration`); this helper bridges both.
        """
        with self.subTest(test_case=test_case_name):
            self.assertIn("title", actual, f"Missing title in {test_case_name}")
            self.assertEqual(actual["title"], expected["title"])
            self.assertEqual(actual.get("type"), "movie", f"type must be 'movie' in {test_case_name}")

            field_map = {
                "director": "director",
                "year": "release_year",
                "country": "country",
                "venue": "venue",
            }
            for expected_field, actual_field in field_map.items():
                if expected.get(expected_field) is not None:
                    self.assertEqual(
                        actual.get(actual_field),
                        expected[expected_field],
                        f"{expected_field}→{actual_field} mismatch in {test_case_name}",
                    )

            if expected.get("duration") is not None:
                expected_minutes = self.scraper._parse_duration_to_minutes(expected["duration"])
                self.assertEqual(
                    actual.get("runtime_minutes"),
                    expected_minutes,
                    f"runtime_minutes mismatch in {test_case_name}",
                )

            if "dates" in expected:
                self.assertIn("dates", actual, f"Missing dates array in {test_case_name}")
                for date in actual["dates"]:
                    self.assertIn(
                        date,
                        expected["dates"],
                        f"Unexpected date {date} in {test_case_name}",
                    )

            if "times" in expected:
                self.assertIn("times", actual, f"Missing times array in {test_case_name}")
                self.assertEqual(
                    len(actual["dates"]),
                    len(actual["times"]),
                    f"dates/times length mismatch in {test_case_name}",
                )

    def test_scraper_initialization(self):
        """Test that the AFS scraper initializes correctly"""
        self.assertIsInstance(self.scraper, AFSScraper)
        self.assertEqual(self.scraper.venue_name, "Austin Movie Society")
        self.assertEqual(self.scraper.base_url, "https://www.austinfilm.org")

    def test_get_target_urls(self):
        """Test that target URLs are returned correctly"""
        urls = self.scraper.get_target_urls()
        self.assertIsInstance(urls, list)
        self.assertTrue(len(urls) > 0)
        self.assertIn("https://www.austinfilm.org/calendar/", urls)

    def test_type_is_movie_on_extracted_events(self):
        """Every emitted AFS event must have type='movie' so the processor filter accepts it."""
        html_content = self._load_test_html("jane_austen_movie_page.html")
        with patch("requests.Session.get") as mock_get:
            import unittest.mock
            mock_response = unittest.mock.MagicMock()
            mock_response.status_code = 200
            mock_response.text = html_content
            mock_get.return_value = mock_response
            events = self.scraper.scrape_events()
        self.assertGreater(len(events), 0, "Scraper must produce events from fixture")
        for e in events:
            self.assertEqual(e.get("type"), "movie")

    def test_extract_movie_data_from_real_pages(self):
        """Test extraction of movie data from real AFS HTML pages"""
        # Test each movie in the test database
        for test_case in self.test_database["test_cases"]:
            with self.subTest(movie=test_case["expected_output"]["title"]):
                # Load the HTML file
                html_content = self._load_test_html(test_case["input"]["html_file"])

                # Create a mock response with the real HTML
                with patch("requests.Session.get") as mock_get:
                    import unittest.mock

                    mock_response = unittest.mock.MagicMock()
                    mock_response.status_code = 200
                    mock_response.text = html_content
                    mock_get.return_value = mock_response

                    # Extract events using the scraper
                    events = self.scraper.scrape_events()

                    # Should extract at least one event
                    self.assertGreater(
                        len(events),
                        0,
                        f"No events extracted from {test_case['input']['html_file']}",
                    )

                    # Test the first extracted event against expected data
                    extracted_event = events[0]
                    expected_data = test_case["expected_output"]

                    self._assert_extracted_data_matches_expected(
                        extracted_event, expected_data, test_case["input"]["html_file"]
                    )

    def test_venue_configuration(self):
        """Scraper is properly configured for AFS and implements required methods."""
        self.assertEqual(self.scraper.venue_name, "Austin Movie Society")
        self.assertTrue(self.scraper.base_url.startswith("https://"))
        self.assertTrue(hasattr(self.scraper, "get_target_urls"))
        self.assertTrue(hasattr(self.scraper, "scrape_events"))

    def test_extract_showtimes_accurately(self):
        """Showtimes are extracted as YYYY-MM-DD dates and 12-hour times."""
        html_content = self._load_test_html("jane_austen_movie_page.html")
        with patch("requests.Session.get") as mock_get:
            import unittest.mock
            mock_response = unittest.mock.MagicMock()
            mock_response.status_code = 200
            mock_response.text = html_content
            mock_get.return_value = mock_response
            events = self.scraper.scrape_events()

        self.assertGreater(len(events), 0)
        event = events[0]
        self.assertIn("dates", event)
        self.assertIn("times", event)
        self.assertTrue(len(event["dates"]) >= 1 and len(event["times"]) >= 1)
        import re
        self.assertRegex(event["dates"][0], r"^\d{4}-\d{2}-\d{2}$")
        self.assertTrue("AM" in event["times"][0] or "PM" in event["times"][0])

    def test_detect_special_screenings(self):
        """Test detection of special screenings like Free Member Monday"""
        # Test the Irish movie which has a Free Member Monday screening
        html_content = self._load_test_html("that_they_may_face_rising_sun.html")

        with patch("requests.Session.get") as mock_get:
            import unittest.mock

            mock_response = unittest.mock.MagicMock()
            mock_response.status_code = 200
            mock_response.text = html_content
            mock_get.return_value = mock_response

            events = self.scraper.scrape_events()

            if events:
                event = events[0]
                # Should extract the title
                title = event.get("title", "").upper()
                self.assertIn("THAT THEY MAY FACE", title)

                # Description should mention Free Member Monday
                description = event.get("description", "")
                if description:
                    self.assertIn("Free Member Monday", description)


if __name__ == "__main__":
    # Run tests with verbose output
    unittest.main(verbosity=2)
