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
        """Helper method to compare extracted data against expected results"""
        with self.subTest(test_case=test_case_name):
            # Check required fields
            self.assertIn("title", actual, f"Missing title in {test_case_name}")
            self.assertEqual(
                actual["title"],
                expected["title"],
                f"Title mismatch in {test_case_name}",
            )

            # Check optional fields if they exist in expected data
            optional_fields = ["director", "year", "country", "duration", "venue"]
            for field in optional_fields:
                if expected.get(field) is not None:
                    self.assertEqual(
                        actual.get(field),
                        expected[field],
                        f"{field} mismatch in {test_case_name}",
                    )

            # Check dates and times arrays
            if "dates" in expected:
                self.assertIn("date", actual, f"Missing date in {test_case_name}")
                # For single events, date should match one of the expected dates
                if isinstance(actual["date"], str):
                    self.assertIn(
                        actual["date"],
                        expected["dates"],
                        f"Date {actual['date']} not in expected dates {expected['dates']} for {test_case_name}",
                    )

            if "times" in expected:
                self.assertIn("time", actual, f"Missing time in {test_case_name}")
                # For single events, time should match one of the expected times
                if isinstance(actual["time"], str):
                    self.assertIn(
                        actual["time"],
                        expected["times"],
                        f"Time {actual['time']} not in expected times {expected['times']} for {test_case_name}",
                    )

            # Check venue
            if "venue" in expected:
                self.assertEqual(
                    actual.get("venue"),
                    expected["venue"],
                    f"Venue mismatch in {test_case_name}",
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

    def test_get_data_schema(self):
        """Test that data schema is returned correctly"""
        schema = self.scraper.get_data_schema()
        self.assertIsInstance(schema, dict)
        # Should include basic movie event fields
        expected_fields = ["title", "date", "venue", "type"]
        for field in expected_fields:
            self.assertIn(field, str(schema))

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
        """Test that venue-specific configuration is correct"""
        # Test that the scraper is properly configured for AFS
        self.assertEqual(self.scraper.venue_name, "Austin Movie Society")
        self.assertTrue(self.scraper.base_url.startswith("https://"))

        # Test that required methods are implemented
        self.assertTrue(hasattr(self.scraper, "get_target_urls"))
        self.assertTrue(hasattr(self.scraper, "get_data_schema"))
        self.assertTrue(hasattr(self.scraper, "scrape_events"))

    def test_extract_showtimes_accurately(self):
        """Test that showtimes are extracted accurately from movie pages"""
        # Test JANE AUSTEN which has many showtimes
        html_content = self._load_test_html("jane_austen_movie_page.html")

        with patch("requests.Session.get") as mock_get:
            import unittest.mock

            mock_response = unittest.mock.MagicMock()
            mock_response.status_code = 200
            mock_response.text = html_content
            mock_get.return_value = mock_response

            events = self.scraper.scrape_events()

            if events:
                event = events[0]
                # Should have date and time
                self.assertIn("date", event)
                self.assertIn("time", event)

                # Date should be in YYYY-MM-DD format
                import re

                date_pattern = r"\d{4}-\d{2}-\d{2}"
                self.assertRegex(
                    event["date"],
                    date_pattern,
                    f"Date {event['date']} not in YYYY-MM-DD format",
                )

                # Time should contain AM or PM
                self.assertTrue(
                    "AM" in event["time"] or "PM" in event["time"],
                    f"Time {event['time']} should contain AM or PM",
                )

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
