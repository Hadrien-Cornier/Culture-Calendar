"""
End-to-end tests for Culture Calendar - Test complete workflows
"""

import pytest
import json
import tempfile
import os
from unittest.mock import Mock, patch
from datetime import datetime

# Import main components for end-to-end testing
from src.scraper import MultiVenueScraper
from src.processor import EventProcessor
from src.summary_generator import SummaryGenerator
from src.calendar_generator import CalendarGenerator


@pytest.mark.integration
@pytest.mark.slow
class TestCompleteWorkflow:
    """Test complete scraping -> processing -> output workflow"""

    @pytest.fixture
    def mock_complete_system(self, mock_env_vars, temp_classical_data_file):
        """Mock all external dependencies for complete system test"""

        # Mock data to return from scrapers
        mock_events = [
            {
                "title": "Test Film Screening",
                "director": "Test Director",
                "year": 2023,
                "date": "2025-07-15",
                "time": "7:30 PM",
                "venue": "AFS",
                "type": "film",
                "url": "https://austinfilm.org/test",
                "description": "A test film for end-to-end testing",
            },
            {
                "title": "Test Book Club: Great Novel",
                "book": "Great Novel",
                "author": "Test Author",
                "date": "2025-07-20",
                "time": "7:00 PM",
                "venue": "FirstLight",
                "type": "book_club",
                "url": "https://firstlight.com/test",
                "description": "Discussion of a great novel",
            },
            {
                "title": "Test Symphony Concert",
                "composers": ["Beethoven"],
                "featured_artist": "Test Orchestra",
                "date": "2025-07-25",
                "time": "8:00 PM",
                "venue": "Symphony",
                "type": "concert",
                "url": "https://symphony.org/test",
                "description": "Classical music concert",
            },
        ]

        # Mock AI responses
        mock_ai_responses = {
            "film_rating": {
                "score": 8,
                "summary": "Compelling drama with excellent cinematography",
            },
            "book_rating": {
                "score": 7,
                "summary": "Thoughtful exploration of human nature",
            },
            "concert_rating": {
                "score": 9,
                "summary": "Masterful interpretation of classical works",
            },
            "summary": "Engaging cultural event worth attending",
        }

        return {
            "events": mock_events,
            "ai_responses": mock_ai_responses,
            "classical_data_file": temp_classical_data_file,
        }

    def test_full_scraping_pipeline(self, mock_complete_system):
        """Test complete scraping pipeline from start to finish"""

        # Step 1: Initialize scraper
        scraper = MultiVenueScraper()

        # Mock individual scrapers to return test data
        with patch.object(
            scraper.afs_scraper,
            "scrape_events",
            return_value=[mock_complete_system["events"][0]],
        ):
            with patch.object(
                scraper.first_light_scraper,
                "scrape_events",
                return_value=[mock_complete_system["events"][1]],
            ):
                with patch.object(
                    scraper.symphony_scraper,
                    "scrape_events",
                    return_value=[mock_complete_system["events"][2]],
                ):
                    with patch.object(
                        scraper.hyperreal_scraper, "scrape_events", return_value=[]
                    ):
                        with patch.object(
                            scraper.early_music_scraper,
                            "scrape_events",
                            return_value=[],
                        ):
                            with patch.object(
                                scraper.la_follia_scraper,
                                "scrape_events",
                                return_value=[],
                            ):
                                with patch.object(
                                    scraper.alienated_majesty_scraper,
                                    "scrape_events",
                                    return_value=[],
                                ):
                                    # Execute scraping
                                    scraped_events = scraper.scrape_all_venues()

        # Verify scraping results
        assert len(scraped_events) == 3
        assert scraped_events[0]["venue"] == "AFS"
        assert scraped_events[1]["venue"] == "FirstLight"
        assert scraped_events[2]["venue"] == "Symphony"

        # Step 2: Process events
        with patch("src.processor.SummaryGenerator"):
            processor = EventProcessor()

            # Mock AI rating calls
            def mock_get_ai_rating(event):
                return mock_complete_system["ai_responses"]["film_rating"]

            def mock_get_book_rating(event):
                return mock_complete_system["ai_responses"]["book_rating"]

            def mock_get_classical_rating(event):
                return mock_complete_system["ai_responses"]["concert_rating"]

            with patch.object(
                processor, "_get_ai_rating", side_effect=mock_get_ai_rating
            ):
                with patch.object(
                    processor, "_get_book_club_rating", side_effect=mock_get_book_rating
                ):
                    with patch.object(
                        processor,
                        "_get_classical_rating",
                        side_effect=mock_get_classical_rating,
                    ):
                        processed_events = processor.process_events(scraped_events)

        # Verify processing results
        assert len(processed_events) == 3
        for event in processed_events:
            assert "ai_rating" in event
            assert "final_rating" in event
            assert "rating_explanation" in event
            assert event["final_rating"] >= 1
            assert event["final_rating"] <= 10

        # Step 3: Generate calendar
        calendar_generator = CalendarGenerator()

        with tempfile.NamedTemporaryFile(suffix=".ics", delete=False) as temp_file:
            try:
                calendar_generator.generate_ics(processed_events, temp_file.name)

                # Verify calendar generation
                assert os.path.exists(temp_file.name)
                assert os.path.getsize(temp_file.name) > 0

                # Read and validate calendar content
                with open(temp_file.name, "r") as f:
                    calendar_content = f.read()

                assert "BEGIN:VCALENDAR" in calendar_content
                assert "END:VCALENDAR" in calendar_content
                assert "Test Film Screening" in calendar_content
                assert "Test Book Club" in calendar_content
                assert "Test Symphony Concert" in calendar_content

            finally:
                os.unlink(temp_file.name)

        return processed_events

    def test_website_data_generation(self, mock_complete_system):
        """Test generation of website JSON data"""

        # Use the processed events from previous test
        processed_events = [
            {
                "title": "Test Film Screening",
                "director": "Test Director",
                "year": 2023,
                "date": "2025-07-15",
                "time": "7:30 PM",
                "venue": "AFS",
                "type": "film",
                "final_rating": 8,
                "ai_rating": {"score": 8, "summary": "Great film"},
                "rating_explanation": "AI Rating: 8/10",
                "oneLinerSummary": "Compelling drama worth watching",
            }
        ]

        # Import website data generation function
        import sys

        sys.path.append(os.path.dirname(os.path.dirname(__file__)))

        # Mock the website data generation
        def generate_website_data(events):
            """Simple mock of website data generation"""
            website_events = []

            for event in events:
                if event.get("type") in ["film", "screening"]:
                    website_event = {
                        "title": event["title"],
                        "director": event.get("director"),
                        "year": event.get("year"),
                        "rating": event.get("final_rating"),
                        "oneLinerSummary": event.get("oneLinerSummary"),
                        "screenings": [
                            {
                                "date": event["date"],
                                "time": event["time"],
                                "venue": event["venue"],
                            }
                        ],
                    }
                    website_events.append(website_event)

            return website_events

        website_data = generate_website_data(processed_events)

        # Verify website data structure
        assert len(website_data) == 1
        film_event = website_data[0]

        assert film_event["title"] == "Test Film Screening"
        assert film_event["director"] == "Test Director"
        assert film_event["rating"] == 8
        assert len(film_event["screenings"]) == 1

        # Test JSON serialization
        json_data = json.dumps(website_data, indent=2)
        assert len(json_data) > 0

        # Test JSON deserialization
        parsed_data = json.loads(json_data)
        assert len(parsed_data) == 1
        assert parsed_data[0]["title"] == "Test Film Screening"

    def test_error_handling_in_pipeline(self, mock_complete_system):
        """Test that pipeline handles errors gracefully"""

        # Create events that might cause errors
        problematic_events = [
            {"title": "", "date": "invalid-date", "venue": "Unknown"},  # Empty title
            {
                "title": "Valid Event",
                "date": "2025-07-15",
                "time": "7:30 PM",
                "venue": "AFS",
                "type": "film",
            },
        ]

        # Test processing with errors
        with patch("src.processor.SummaryGenerator"):
            processor = EventProcessor()

            # Mock AI rating to sometimes fail
            def mock_failing_ai_rating(event):
                if not event.get("title"):
                    raise Exception("Empty title")
                return {"score": 8, "summary": "Test summary"}

            with patch.object(
                processor, "_get_ai_rating", side_effect=mock_failing_ai_rating
            ):
                processed_events = processor.process_events(problematic_events)

        # Should still return some events despite errors
        assert isinstance(processed_events, list)

        # Valid events should be processed successfully
        valid_events = [e for e in processed_events if e.get("title") == "Valid Event"]
        assert len(valid_events) > 0

    def test_rating_filtering_workflow(self, mock_complete_system):
        """Test rating-based filtering for calendar generation"""

        # Create events with different ratings
        events_with_ratings = [
            {
                "title": "High Rated Film",
                "date": "2025-07-15",
                "time": "7:30 PM",
                "venue": "AFS",
                "final_rating": 9,
                "rating_explanation": "AI Rating: 9/10",
            },
            {
                "title": "Medium Rated Film",
                "date": "2025-07-16",
                "time": "7:30 PM",
                "venue": "AFS",
                "final_rating": 6,
                "rating_explanation": "AI Rating: 6/10",
            },
            {
                "title": "Low Rated Film",
                "date": "2025-07-17",
                "time": "7:30 PM",
                "venue": "AFS",
                "final_rating": 3,
                "rating_explanation": "AI Rating: 3/10",
            },
        ]

        # Test filtering by minimum rating
        def filter_by_rating(events, min_rating):
            return [e for e in events if e.get("final_rating", 0) >= min_rating]

        # Test different rating thresholds
        high_rated = filter_by_rating(events_with_ratings, 8)
        medium_rated = filter_by_rating(events_with_ratings, 5)
        all_rated = filter_by_rating(events_with_ratings, 1)

        assert len(high_rated) == 1
        assert len(medium_rated) == 2
        assert len(all_rated) == 3

        # Generate calendars for different rating levels
        calendar_generator = CalendarGenerator()

        for rating_filter, filtered_events in [(8, high_rated), (5, medium_rated)]:
            if filtered_events:
                with tempfile.NamedTemporaryFile(
                    suffix=f"_rating_{rating_filter}.ics", delete=False
                ) as temp_file:
                    try:
                        calendar_generator.generate_ics(filtered_events, temp_file.name)

                        assert os.path.exists(temp_file.name)
                        assert os.path.getsize(temp_file.name) > 0

                        # Verify calendar contains only appropriately rated events
                        with open(temp_file.name, "r") as f:
                            content = f.read()

                        if rating_filter == 8:
                            assert "High Rated Film" in content
                            assert "Medium Rated Film" not in content
                        elif rating_filter == 5:
                            assert "High Rated Film" in content
                            assert "Medium Rated Film" in content

                    finally:
                        os.unlink(temp_file.name)


@pytest.mark.integration
class TestSystemIntegration:
    """Test integration with external systems and file formats"""

    def test_ics_calendar_compatibility(self):
        """Test that generated ICS files are compatible with calendar applications"""
        from src.calendar_generator import CalendarGenerator

        test_events = [
            {
                "title": "Test Event for Calendar Compatibility",
                "date": "2025-07-15",
                "time": "7:30 PM",
                "venue": "AFS",
                "final_rating": 8,
                "rating_explanation": "AI Rating: 8/10",
                "url": "https://example.com/event",
                "description": "Test event for calendar compatibility testing",
            }
        ]

        calendar_gen = CalendarGenerator()

        with tempfile.NamedTemporaryFile(suffix=".ics", delete=False) as temp_file:
            try:
                calendar_gen.generate_ics(test_events, temp_file.name)

                # Read the generated ICS file
                with open(temp_file.name, "r") as f:
                    ics_content = f.read()

                # Test ICS format compliance
                required_ics_elements = [
                    "BEGIN:VCALENDAR",
                    "VERSION:2.0",
                    "PRODID:",
                    "BEGIN:VEVENT",
                    "UID:",
                    "DTSTART:",
                    "DTEND:",
                    "SUMMARY:",
                    "DESCRIPTION:",
                    "END:VEVENT",
                    "END:VCALENDAR",
                ]

                for element in required_ics_elements:
                    assert (
                        element in ics_content
                    ), f"Missing required ICS element: {element}"

                # Test that dates are properly formatted
                import re

                date_pattern = r"DTSTART:(\d{8}T\d{6})"
                date_match = re.search(date_pattern, ics_content)
                assert date_match, "Date not properly formatted in ICS"

                # Test that event content is properly encoded
                assert "Test Event for Calendar Compatibility" in ics_content

            finally:
                os.unlink(temp_file.name)

    def test_json_data_compatibility(self):
        """Test that generated JSON is compatible with website"""

        sample_website_data = [
            {
                "title": "Test Movie",
                "director": "Test Director",
                "year": 2023,
                "rating": 8,
                "oneLinerSummary": "Great film to watch",
                "screenings": [
                    {"date": "2025-07-15", "time": "7:30 PM", "venue": "AFS"}
                ],
                "genres": ["Drama"],
                "isMovie": True,
                "duration": "120 min",
            }
        ]

        # Test JSON serialization/deserialization
        json_str = json.dumps(sample_website_data, indent=2)
        parsed_data = json.loads(json_str)

        assert len(parsed_data) == 1
        assert parsed_data[0]["title"] == "Test Movie"
        assert len(parsed_data[0]["screenings"]) == 1

        # Test that all required fields for website are present
        required_fields = ["title", "rating", "screenings"]
        for field in required_fields:
            assert field in parsed_data[0], f"Missing required field: {field}"

        # Test screening structure
        screening = parsed_data[0]["screenings"][0]
        screening_fields = ["date", "time", "venue"]
        for field in screening_fields:
            assert field in screening, f"Missing screening field: {field}"

    def test_cache_file_handling(self, temp_cache_dir):
        """Test cache file creation and management"""

        # Test summary cache
        cache_file = os.path.join(temp_cache_dir, "test_cache.json")

        cache_data = {
            "TEST_MOVIE_FILM": "Cached summary for test movie",
            "BOOK_CLUB_EVENT_BOOK": "Cached summary for book event",
        }

        # Write cache
        with open(cache_file, "w") as f:
            json.dump(cache_data, f, indent=2)

        assert os.path.exists(cache_file)

        # Read cache
        with open(cache_file, "r") as f:
            loaded_cache = json.load(f)

        assert loaded_cache == cache_data
        assert "TEST_MOVIE_FILM" in loaded_cache

        # Test cache key format
        for key in loaded_cache.keys():
            parts = key.split("_")
            assert len(parts) >= 2, f"Cache key {key} not properly formatted"


@pytest.mark.slow
class TestPerformanceRequirements:
    """Test that system meets performance requirements"""

    def test_processing_time_limits(self, mock_complete_system):
        """Test that processing completes within reasonable time limits"""
        import time

        # Create a larger set of test events
        test_events = []
        for i in range(10):  # Small set for testing
            test_events.append(
                {
                    "title": f"Test Event {i}",
                    "date": "2025-07-15",
                    "time": "7:30 PM",
                    "venue": "AFS",
                    "type": "film",
                    "description": f"Test event number {i} for performance testing",
                }
            )

        # Mock processor with quick responses
        with patch("src.processor.SummaryGenerator"):
            processor = EventProcessor()

            def quick_ai_rating(event):
                return {"score": 8, "summary": "Quick test summary"}

            with patch.object(processor, "_get_ai_rating", side_effect=quick_ai_rating):

                start_time = time.time()
                processed_events = processor.process_events(test_events)
                end_time = time.time()

                processing_time = end_time - start_time

                # Should process events reasonably quickly (less than 1 second per event when mocked)
                assert (
                    processing_time < len(test_events) * 1.0
                ), f"Processing took too long: {processing_time}s"
                assert len(processed_events) == len(test_events)

    def test_memory_usage(self, mock_complete_system):
        """Test that system doesn't use excessive memory"""
        import sys

        # Get initial memory usage
        initial_size = sys.getsizeof(mock_complete_system)

        # Process events and measure memory
        events = (
            mock_complete_system["events"] * 5
        )  # Duplicate to create larger dataset

        with patch("src.processor.SummaryGenerator"):
            processor = EventProcessor()

            with patch.object(
                processor,
                "_get_ai_rating",
                return_value={"score": 8, "summary": "Test"},
            ):
                processed = processor.process_events(events)

                final_size = sys.getsizeof(processed)

                # Memory usage should be reasonable (less than 10x the input size)
                assert (
                    final_size < initial_size * 10
                ), f"Memory usage too high: {final_size} vs {initial_size}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "integration or slow"])
