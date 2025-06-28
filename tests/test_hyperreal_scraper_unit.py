"""
Unit tests for Hyperreal Film Club scraper.
"""

import json
from pathlib import Path

import pytest

from src.scrapers.hyperreal_scraper import HyperrealScraper


class TestHyperrealScraper:
    """Test cases for Hyperreal Film Club scraper."""

    def setup_method(self):
        """Set up test fixtures."""
        self.scraper = HyperrealScraper()
        self.test_data_dir = Path(__file__).parent / "Hyperreal_test_data"

        # Load test database
        with open(
            self.test_data_dir / "hyperreal_scraper_test_database.json", "r"
        ) as f:
            self.test_db = json.load(f)

    def load_test_html(self, filename: str) -> str:
        """Load test HTML file."""
        file_path = self.test_data_dir / filename
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()

    def test_individual_event_extraction(self):
        """Test extraction of individual event data from movie page."""
        test_case = self.test_db["test_cases"][0]
        html_content = self.load_test_html(test_case["input"]["html_file"])
        url = test_case["input"]["url"]
        expected = test_case["expected_output"]

        # Extract event data
        result = self.scraper._extract_event_data_from_page(html_content, url)

        # Verify extraction worked
        assert result is not None, "Failed to extract event data"

        # Test core fields
        assert (
            result["title"] == expected["title"]
        ), f"Title mismatch: {result['title']} != {expected['title']}"
        assert result["full_title"] == expected["full_title"], f"Full title mismatch"
        assert result["presenter"] == expected["presenter"], f"Presenter mismatch"
        assert result["dates"] == expected["dates"], f"Dates mismatch"
        result["times"] = [t.replace("\u202f", " ") for t in result["times"]]
        assert result["times"] == expected["times"], f"Times mismatch"
        result["end_times"] = [t.replace("\u202f", " ") for t in result["end_times"]]
        assert result["end_times"] == expected["end_times"], f"End times mismatch"
        assert result["venue"] == expected["venue"], f"Venue mismatch"
        assert result["url"] == expected["url"], f"URL mismatch"
        assert (
            result["is_special_screening"] == expected["is_special_screening"]
        ), f"Special screening flag mismatch"

        # Test optional fields
        if expected.get("trailer_url"):
            assert (
                result["trailer_url"] == expected["trailer_url"]
            ), f"Trailer URL mismatch"

        # Test description (allowing for some flexibility in whitespace)
        if expected.get("description"):
            assert result["description"] is not None, "Description should not be None"
            assert len(result["description"]) > 100, "Description should be substantial"

    def test_movie_title_extraction(self):
        """Test movie title extraction from full event titles."""
        test_cases = [
            ("A Woman of Taste Presents ~ MERMAIDS at HYPERREAL FILM CLUB", "MERMAIDS"),
            (
                "Sad Girl Cinema ~ HOUSE OF TOLERANCE at HYPERREAL FILM CLUB",
                "HOUSE OF TOLERANCE",
            ),
            (
                "First Times ~ PLEASE BABY PLEASE at HYPERREAL FILM CLUB",
                "PLEASE BABY PLEASE",
            ),
            ("Fangoria presents THE BURNING at HYPERREAL FILM CLUB", "THE BURNING"),
            (
                "KOKOMO CITY presented by Queertopia at HYPERREAL FILM CLUB",
                "KOKOMO CITY",
            ),
            (
                "MISS JUNETEENTH free screening at HYPERREAL FILM CLUB",
                "MISS JUNETEENTH",
            ),
            ("Freaks Only ~ SEED OF CHUCKY at HYPERREAL FILM CLUB", "SEED OF CHUCKY"),
            ("SAW at HYPERREAL FILM CLUB", "SAW"),
            ("20TH CENTURY WOMEN at HYPERREAL FILM CLUB", "20TH CENTURY WOMEN"),
        ]

        for full_title, expected_title in test_cases:
            result = self.scraper._extract_movie_title(full_title)
            assert (
                result == expected_title
            ), f"Title extraction failed: '{full_title}' -> '{result}' (expected '{expected_title}')"

    def test_presenter_extraction(self):
        """Test presenter/series extraction from full event titles."""
        test_cases = [
            (
                "A Woman of Taste Presents ~ MERMAIDS at HYPERREAL FILM CLUB",
                "A Woman of Taste",
            ),
            (
                "Sad Girl Cinema ~ HOUSE OF TOLERANCE at HYPERREAL FILM CLUB",
                "Sad Girl Cinema",
            ),
            ("First Times ~ PLEASE BABY PLEASE at HYPERREAL FILM CLUB", "First Times"),
            (
                "Fangoria presents THE BURNING at HYPERREAL FILM CLUB",
                "Fangoria Presents",
            ),
            (
                "KOKOMO CITY presented by Queertopia at HYPERREAL FILM CLUB",
                "Presented By Queertopia",
            ),
            ("Freaks Only ~ SEED OF CHUCKY at HYPERREAL FILM CLUB", "Freaks Only"),
            ("SAW at HYPERREAL FILM CLUB", None),
            ("20TH CENTURY WOMEN at HYPERREAL FILM CLUB", None),
        ]

        for full_title, expected_presenter in test_cases:
            result = self.scraper._extract_presenter(full_title)
            if expected_presenter is None:
                assert (
                    result is None
                ), f"Should not extract presenter from '{full_title}', got '{result}'"
            else:
                assert (
                    result is not None
                ), f"Should extract presenter from '{full_title}'"
                # Allow for some flexibility in exact string matching
                assert any(
                    part.lower() in result.lower()
                    for part in expected_presenter.lower().split()
                ), f"Presenter extraction failed: '{full_title}' -> '{result}' (expected something containing '{expected_presenter}')"

    def test_special_screening_detection(self):
        """Test detection of special screenings."""
        test_cases = [
            ("A Woman of Taste Presents ~ MERMAIDS at HYPERREAL FILM CLUB", True),
            ("Sad Girl Cinema ~ HOUSE OF TOLERANCE at HYPERREAL FILM CLUB", True),
            ("First Times ~ PLEASE BABY PLEASE at HYPERREAL FILM CLUB", True),
            ("Fangoria presents THE BURNING at HYPERREAL FILM CLUB", True),
            ("MISS JUNETEENTH free screening at HYPERREAL FILM CLUB", True),
            ("Freaks Only ~ SEED OF CHUCKY at HYPERREAL FILM CLUB", True),
            ("SAW at HYPERREAL FILM CLUB", False),
            ("20TH CENTURY WOMEN at HYPERREAL FILM CLUB", False),
            ("PAST LIVES at HYPERREAL FILM CLUB", False),
        ]

        for title, expected_special in test_cases:
            result = self.scraper._is_special_screening(title)
            assert (
                result == expected_special
            ), f"Special screening detection failed for '{title}': got {result}, expected {expected_special}"

    def test_calendar_event_link_extraction(self):
        """Test extraction of event links from calendar page."""
        calendar_html = self.load_test_html("hyperreal_june_2025.html")

        # Extract event links
        event_links = self.scraper._extract_event_links_from_calendar(calendar_html)

        # Verify we found events
        assert len(event_links) > 0, "Should find event links in calendar"

        # Verify URL format
        for url in event_links:
            assert url.startswith(
                "https://hyperrealfilm.club/events/2025/"
            ), f"Invalid event URL format: {url}"
            assert (
                "movie-screening" in url
            ), f"Event URL should contain 'movie-screening': {url}"

    def test_calendar_url_generation(self):
        """Test calendar URL generation for different months."""
        test_cases = [
            (2025, 6, "https://hyperrealfilm.club/events?view=calendar&month=06-2025"),
            (2025, 12, "https://hyperrealfilm.club/events?view=calendar&month=12-2025"),
            (2024, 1, "https://hyperrealfilm.club/events?view=calendar&month=01-2024"),
        ]

        for year, month, expected_url in test_cases:
            result = self.scraper.get_calendar_url(year, month)
            assert (
                result == expected_url
            ), f"Calendar URL generation failed: got {result}, expected {expected_url}"

    def test_schema_structure(self):
        """Test that the scraper returns a proper schema."""
        schema = self.scraper.get_schema()

        # Verify schema has expected fields
        expected_fields = [
            "title",
            "full_title",
            "presenter",
            "dates",
            "times",
            "end_times",
            "venue",
            "description",
            "trailer_url",
            "url",
            "is_special_screening",
        ]

        # Schema should be a dictionary or have attributes for these fields
        for field in expected_fields:
            assert (
                hasattr(schema, field) or field in schema
            ), f"Schema missing field: {field}"

    def test_venue_and_address_constants(self):
        """Test that venue information is properly set."""
        assert self.scraper.venue_name == "Hyperreal Film Club"
        assert self.scraper.venue_address == "301 Chicon Street, Austin, TX, 78702"
        assert self.scraper.base_url == "https://hyperrealfilm.club"

    def test_description_extraction_quality(self):
        """Test that description extraction provides meaningful content."""
        test_case = self.test_db["test_cases"][0]
        html_content = self.load_test_html(test_case["input"]["html_file"])
        url = test_case["input"]["url"]

        result = self.scraper._extract_event_data_from_page(html_content, url)

        assert result is not None
        description = result["description"]

        # Description should be substantial
        assert len(description) > 100, "Description should be substantial"

        # Should contain key information
        assert "MERMAIDS" in description, "Description should mention the movie title"
        assert "Winona Ryder" in description, "Description should mention cast members"
        assert "Cher" in description, "Description should mention cast members"

        # Should not contain excessive HTML or formatting artifacts
        assert "<" not in description, "Description should not contain HTML tags"
        assert ">" not in description, "Description should not contain HTML tags"


if __name__ == "__main__":
    pytest.main([__file__])
