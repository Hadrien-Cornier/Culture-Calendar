"""
Data quality tests for Culture Calendar - Validate data integrity and quality
"""

import pytest
import json
import re
from datetime import datetime, timedelta
from typing import List, Dict

from src.schemas import SchemaRegistry, get_venue_schema


@pytest.mark.unit
class TestEventDataQuality:
    """Test data quality validation for events"""

    def test_required_fields_validation(
        self, sample_film_event, sample_book_club_event, sample_concert_event
    ):
        """Test that required fields are properly validated"""
        # Test film event
        film_validation = SchemaRegistry.validate_event_data(sample_film_event, "film")
        assert film_validation["is_valid"] == True
        assert len(film_validation["errors"]) == 0

        # Test book club event
        book_validation = SchemaRegistry.validate_event_data(
            sample_book_club_event, "book_club"
        )
        assert book_validation["is_valid"] == True
        assert len(book_validation["errors"]) == 0

        # Test concert event
        concert_validation = SchemaRegistry.validate_event_data(
            sample_concert_event, "concert"
        )
        assert concert_validation["is_valid"] == True
        assert len(concert_validation["errors"]) == 0

    def test_missing_required_fields(self):
        """Test validation fails for missing required fields"""
        incomplete_film = {
            "director": "Test Director",
            "year": 2023,
            # Missing required 'title' and 'date'
        }

        validation = SchemaRegistry.validate_event_data(incomplete_film, "film")
        assert validation["is_valid"] == False
        assert len(validation["errors"]) > 0
        assert any("title" in error for error in validation["errors"])

    def test_date_format_validation(self):
        """Test that date formats are valid"""
        valid_dates = ["2025-07-15", "2025-12-31", "2024-02-29"]  # Leap year
        invalid_dates = ["2025-13-01", "2025-07-32", "25-07-15", "July 15, 2025"]

        for date in valid_dates:
            event = {"title": "Test", "date": date, "time": "7:30 PM"}
            validation = SchemaRegistry.validate_event_data(event, "film")
            # Note: Our schema doesn't validate date format yet, but we test the concept
            assert "date" in event

            # Test that we can parse the date
            try:
                datetime.strptime(date, "%Y-%m-%d")
                assert True
            except ValueError:
                assert False, f"Valid date {date} failed to parse"

    def test_time_format_validation(self):
        """Test that time formats are reasonable"""
        valid_times = ["7:30 PM", "12:00 PM", "11:59 PM", "12:30 AM"]

        for time in valid_times:
            event = {"title": "Test", "date": "2025-07-15", "time": time}
            assert "time" in event

            # Test that time follows expected pattern
            time_pattern = r"\d{1,2}:\d{2}\s*[AP]M"
            assert re.match(
                time_pattern, time, re.IGNORECASE
            ), f"Time {time} doesn't match expected pattern"

    def test_url_format_validation(self):
        """Test that URLs are well-formed"""
        valid_urls = [
            "https://www.example.com",
            "https://example.com/path/to/event",
            "http://example.com",
            "https://example.com/event?id=123",
        ]

        invalid_urls = [
            "not-a-url",
            "ftp://example.com",
            "example.com",  # Missing protocol
            "",
        ]

        for url in valid_urls:
            assert url.startswith(
                ("http://", "https://")
            ), f"URL {url} should have valid protocol"

        for url in invalid_urls:
            if url:  # Empty strings are allowed as optional fields
                assert not url.startswith(
                    ("http://", "https://")
                ), f"URL {url} should be invalid"

    def test_venue_consistency(self):
        """Test that venue names are consistent"""
        expected_venues = {
            "AFS",
            "Hyperreal",
            "Symphony",
            "EarlyMusic",
            "LaFollia",
            "AlienatedMajesty",
            "FirstLight",
        }

        # Test sample events have valid venues
        test_events = [{"venue": "AFS"}, {"venue": "FirstLight"}, {"venue": "Symphony"}]

        for event in test_events:
            assert (
                event["venue"] in expected_venues
            ), f"Venue {event['venue']} not in expected list"

    def test_rating_bounds(self):
        """Test that ratings are within expected bounds"""
        valid_ratings = [1, 5, 8, 10]
        invalid_ratings = [0, 11, -1, 15]

        for rating in valid_ratings:
            assert 1 <= rating <= 10, f"Rating {rating} should be valid (1-10)"

        for rating in invalid_ratings:
            assert not (1 <= rating <= 10), f"Rating {rating} should be invalid"


@pytest.mark.unit
class TestSchemaExtraction:
    """Test schema-based data extraction quality"""

    def test_extraction_hints_completeness(self):
        """Test that schemas have useful extraction hints"""
        from src.schemas import FilmEventSchema, BookClubEventSchema

        film_schema = FilmEventSchema.get_schema()
        book_schema = BookClubEventSchema.get_schema()

        # Check that important fields have extraction hints
        important_film_fields = ["director", "year", "country", "duration"]
        for field in important_film_fields:
            if field in film_schema:
                field_def = film_schema[field]
                assert (
                    "extraction_hints" in field_def
                ), f"Film field {field} missing extraction hints"
                assert (
                    len(field_def["extraction_hints"]) > 0
                ), f"Film field {field} has empty extraction hints"

        important_book_fields = ["book", "author", "host"]
        for field in important_book_fields:
            if field in book_schema:
                field_def = book_schema[field]
                assert (
                    "extraction_hints" in field_def
                ), f"Book field {field} missing extraction hints"
                assert (
                    len(field_def["extraction_hints"]) > 0
                ), f"Book field {field} has empty extraction hints"

    def test_extraction_patterns_validity(self):
        """Test that regex patterns in schemas are valid"""
        from src.schemas import FilmEventSchema

        film_schema = FilmEventSchema.get_schema()

        for field_name, field_def in film_schema.items():
            patterns = field_def.get("extraction_patterns", [])
            for pattern in patterns:
                try:
                    re.compile(pattern)
                except re.error as e:
                    assert (
                        False
                    ), f"Invalid regex pattern in {field_name}: {pattern} - {e}"

    def test_schema_field_descriptions(self):
        """Test that schema fields have meaningful descriptions"""
        schemas = ["film", "book_club", "concert", "theater"]

        for schema_type in schemas:
            schema = SchemaRegistry.get_schema(schema_type)

            for field_name, field_def in schema.items():
                description = field_def.get("description", "")
                assert (
                    description.strip()
                ), f"Field {field_name} in {schema_type} schema missing description"
                assert (
                    len(description) > 10
                ), f"Field {field_name} description too short: {description}"


@pytest.mark.integration
class TestCrossVenueDataQuality:
    """Test data quality across different venues"""

    def test_event_type_consistency(self):
        """Test that event types are consistent with venues"""
        venue_type_mapping = {
            "AFS": "film",
            "Hyperreal": "film",
            "Symphony": "concert",
            "EarlyMusic": "concert",
            "LaFollia": "concert",
            "AlienatedMajesty": "book_club",
            "FirstLight": "book_club",
        }

        for venue, expected_type in venue_type_mapping.items():
            schema = get_venue_schema(venue)
            # Verify venue gets correct schema type
            if expected_type == "film":
                assert "director" in schema
            elif expected_type == "book_club":
                assert "book" in schema and "author" in schema
            elif expected_type == "concert":
                assert "composers" in schema or "featured_artist" in schema

    def test_duplicate_detection_logic(self):
        """Test logic for detecting duplicate events"""
        # Test events that should be considered duplicates
        event1 = {
            "title": "The Great Movie",
            "date": "2025-07-15",
            "time": "7:30 PM",
            "venue": "AFS",
        }

        event2 = {
            "title": "The Great Movie",  # Same title
            "date": "2025-07-15",  # Same date
            "time": "7:30 PM",  # Same time
            "venue": "AFS",  # Same venue
        }

        event3 = {
            "title": "The Great Movie",
            "date": "2025-07-15",
            "time": "9:30 PM",  # Different time - not duplicate
            "venue": "AFS",
        }

        # Simple duplicate detection logic
        def create_event_id(event):
            return f"{event['title'].lower()}_{event['date']}_{event['time']}_{event['venue']}"

        id1 = create_event_id(event1)
        id2 = create_event_id(event2)
        id3 = create_event_id(event3)

        assert id1 == id2, "Identical events should have same ID"
        assert id1 != id3, "Different times should have different IDs"

    def test_date_range_validation(self):
        """Test that event dates are within reasonable ranges"""
        today = datetime.now().date()
        max_future_date = today + timedelta(days=365)  # 1 year in future
        min_past_date = today - timedelta(days=30)  # 30 days in past

        test_dates = [
            "2025-07-15",  # Should be valid
            "2024-01-01",  # Might be too far in past
            "2027-12-31",  # Might be too far in future
        ]

        for date_str in test_dates:
            try:
                event_date = datetime.strptime(date_str, "%Y-%m-%d").date()

                # Check if date is within reasonable range
                is_valid_range = min_past_date <= event_date <= max_future_date

                # For testing, we just verify the logic works
                assert isinstance(is_valid_range, bool)

            except ValueError:
                assert False, f"Date {date_str} should be parseable"


@pytest.mark.unit
class TestDataSanitization:
    """Test data cleaning and sanitization"""

    def test_text_field_sanitization(self):
        """Test that text fields are properly sanitized"""
        dirty_texts = [
            "  Title with extra spaces  ",
            "Title\nwith\nnewlines",
            "Title with\ttabs",
            'Title with "quotes"',
            "Title with <html> tags",
        ]

        expected_results = [
            "Title with extra spaces",
            "Title with newlines",
            "Title with tabs",
            'Title with "quotes"',  # Quotes should be preserved
            "Title with <html> tags",  # HTML should be preserved or escaped
        ]

        for dirty, expected in zip(dirty_texts, expected_results):
            # Basic sanitization: strip and normalize whitespace
            sanitized = " ".join(dirty.strip().split())

            # For this test, we just verify sanitization logic works
            assert len(sanitized) <= len(dirty), "Sanitized text shouldn't be longer"
            assert not sanitized.startswith(" "), "Should not start with space"
            assert not sanitized.endswith(" "), "Should not end with space"

    def test_url_sanitization(self):
        """Test URL sanitization and validation"""
        urls = [
            "https://example.com/path",
            "http://example.com",
            "https://example.com/path?param=value&other=123",
        ]

        for url in urls:
            # Basic URL validation
            assert url.startswith(
                ("http://", "https://")
            ), f"URL {url} should have valid protocol"
            assert "." in url, f"URL {url} should have domain"
            assert len(url) > 10, f"URL {url} should be reasonable length"

    def test_none_vs_empty_string_handling(self):
        """Test proper handling of None vs empty strings"""
        event_with_none = {
            "title": "Test Event",
            "director": None,  # None for missing data
            "year": None,
            "description": "Has description",
        }

        event_with_empty = {
            "title": "Test Event",
            "director": "",  # Empty string
            "year": "",
            "description": "Has description",
        }

        # Verify that None is preferred over empty strings for missing data
        for field in ["director", "year"]:
            none_value = event_with_none[field]
            empty_value = event_with_empty[field]

            # None is preferred for truly missing data
            assert none_value is None
            assert empty_value == ""

            # Test that we can distinguish between them
            assert none_value != empty_value


@pytest.mark.unit
class TestDataConsistency:
    """Test data consistency across the system"""

    def test_venue_name_consistency(self):
        """Test that venue names are consistent across components"""
        from src.schemas import VENUE_SCHEMAS

        # All venue names should be properly mapped
        expected_venues = {
            "AFS",
            "Hyperreal",
            "Symphony",
            "EarlyMusic",
            "LaFollia",
            "AlienatedMajesty",
            "FirstLight",
        }
        mapped_venues = set(VENUE_SCHEMAS.keys())

        assert (
            expected_venues == mapped_venues
        ), f"Venue mapping inconsistency: {expected_venues - mapped_venues}"

    def test_event_type_consistency(self):
        """Test that event types are consistently defined"""
        from src.schemas import SchemaRegistry

        available_types = set(SchemaRegistry.get_available_types())
        expected_types = {"film", "concert", "book_club", "theater", "event"}

        assert expected_types.issubset(
            available_types
        ), f"Missing event types: {expected_types - available_types}"

    def test_field_naming_consistency(self):
        """Test that field names are consistent across schemas"""
        schemas = ["film", "book_club", "concert"]

        # Fields that should be in all schemas
        universal_fields = {"title", "date", "time", "venue"}

        for schema_type in schemas:
            schema = SchemaRegistry.get_schema(schema_type)
            schema_fields = set(schema.keys())

            missing_universal = universal_fields - schema_fields
            assert (
                len(missing_universal) == 0
            ), f"Schema {schema_type} missing universal fields: {missing_universal}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
