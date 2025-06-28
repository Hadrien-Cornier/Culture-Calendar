#!/usr/bin/env python3
"""
Tests for First Light Austin scraper using the test database
"""

import json
from pathlib import Path

import pytest

from src.scrapers.first_light_scraper import FirstLightAustinScraper


class TestFirstLightScraper:
    """Test suite for First Light Austin scraper"""

    @classmethod
    def setup_class(cls):
        """Set up test data"""
        cls.scraper = FirstLightAustinScraper()

        # Load test database
        test_db_path = Path(
            "tests/First_Light_test_data/first_light_scraper_test_database.json"
        )
        with open(test_db_path, "r", encoding="utf-8") as f:
            cls.test_database = json.load(f)

        cls.test_cases = cls.test_database["test_cases"]

    def test_database_loaded(self):
        """Test that the test database is properly loaded"""
        assert len(self.test_cases) == 10
        assert "schema" in self.test_database
        assert "description" in self.test_database

    def test_scraper_initialization(self):
        """Test that the scraper initializes correctly"""
        assert self.scraper.base_url == "https://www.firstlightaustin.com"
        assert self.scraper.venue_name == "FirstLight"

    def test_schema_covers_all_fields(self):
        """Test that scraper schema covers all fields in test database"""
        scraper_schema = self.scraper.get_data_schema()

        # Get all unique fields from test cases
        all_fields = set()
        for test_case in self.test_cases:
            expected_output = test_case["expected_output"]
            all_fields.update(expected_output.keys())

        # Remove fields that are okay to be missing from scraper schema
        optional_fields = {"url", "rsvp_url", "series"}
        required_fields = all_fields - optional_fields

        schema_fields = set(scraper_schema.keys())

        missing_fields = required_fields - schema_fields
        if missing_fields:
            pytest.fail(f"Scraper schema missing fields: {missing_fields}")

    def test_individual_extractions(self):
        """Test individual event extractions from HTML files"""
        failed_tests = []

        for test_case in self.test_cases:
            try:
                self._test_single_extraction(test_case)
            except Exception as e:
                failed_tests.append((test_case["test_id"], str(e)))

        if failed_tests:
            failure_msg = "\n".join(
                [f"Test {test_id}: {error}" for test_id, error in failed_tests]
            )
            pytest.fail(f"Failed extractions:\n{failure_msg}")

    def _test_single_extraction(self, test_case):
        """Test a single event extraction"""
        html_file = test_case["input"]["html_file"]
        expected_output = test_case["expected_output"]
        url = test_case["input"]["url"]

        # Read HTML file
        html_path = Path(f"tests/First_Light_test_data/{html_file}")
        if not html_path.exists():
            raise FileNotFoundError(f"HTML file {html_file} not found")

        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        # Extract events using scraper
        try:
            if "book-club" in url:
                extracted_events = self.scraper.extract_book_club_events(
                    html_content, url
                )
            else:
                extracted_events = self.scraper.extract_author_events(html_content, url)
        except AttributeError as e:
            raise AttributeError(
                f"Scraper missing method for extracting from {url}: {e}"
            )

        # Find matching event
        matching_event = None
        for event in extracted_events:
            if event.get("title") == expected_output.get("title"):
                matching_event = event
                break

        if not matching_event:
            raise AssertionError(
                f"No matching event found for: {expected_output.get('title')}"
            )

        # Compare fields
        self._compare_event_fields(
            matching_event, expected_output, test_case["test_id"]
        )

    def _compare_event_fields(self, actual, expected, test_id):
        """Compare extracted event fields with expected output"""
        for field, expected_value in expected.items():
            if field in ["url", "rsvp_url"]:  # Skip URL fields for now
                continue

            actual_value = actual.get(field)

            if expected_value is None:
                assert (
                    actual_value is None or actual_value == ""
                ), f"Test {test_id}: Field '{field}' should be None/empty, got: {actual_value}"
            else:
                assert (
                    actual_value is not None
                ), f"Test {test_id}: Field '{field}' is missing from extracted data"

                # For string fields, check if they match or at least contain
                # key information
                if isinstance(expected_value, str) and isinstance(actual_value, str):
                    if field == "date":
                        assert (
                            actual_value == expected_value
                        ), f"Test {test_id}: Date mismatch. Expected: {expected_value}, Got: {actual_value}"
                    elif field == "time":
                        assert (
                            actual_value.replace(" ", "").upper()
                            == expected_value.replace(" ", "").upper()
                        ), f"Test {test_id}: Time mismatch. Expected: {expected_value}, Got: {actual_value}"
                    else:
                        # For other fields, check if core content matches
                        assert (
                            actual_value.strip() == expected_value.strip()
                        ), f"Test {test_id}: Field '{field}' mismatch.\nExpected: {expected_value}\nGot: {actual_value}"
                else:
                    assert (
                        actual_value == expected_value
                    ), f"Test {test_id}: Field '{field}' mismatch. Expected: {expected_value}, Got: {actual_value}"

    def test_end_to_end_scraping(self):
        """Test end-to-end scraping functionality"""
        # This test will be implemented once the basic extraction methods work
        pytest.skip("End-to-end test not implemented yet")


# No dynamic test generation needed


if __name__ == "__main__":
    # Run tests directly
    pytest.main([__file__, "-v"])
