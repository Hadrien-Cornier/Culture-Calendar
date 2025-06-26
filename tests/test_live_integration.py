"""
Live integration tests for Culture Calendar - Test with real API keys and actual data
"""

import os
import pytest
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any
from dotenv import load_dotenv

# Import main components for live testing
from src.scraper import MultiVenueScraper
from src.processor import EventProcessor
from src.summary_generator import SummaryGenerator
from src.calendar_generator import CalendarGenerator
from src.schemas import SchemaRegistry, get_venue_schema

# Load environment variables
load_dotenv()

# Check API key availability
firecrawl_api_key = os.getenv("FIRECRAWL_API_KEY")
anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")

# Skip tests if API keys are not available
firecrawl_skip_reason = (
    "Firecrawl API key is not configured. Set FIRECRAWL_API_KEY in your .env file."
)
llm_skip_reason = (
    "Anthropic API key is not configured. Set ANTHROPIC_API_KEY in your .env file."
)


class LiveIntegrationTestFramework:
    """Framework for live integration testing with real data"""

    def __init__(self):
        self.scraper = MultiVenueScraper()
        self.processor = EventProcessor()
        self.summary_generator = SummaryGenerator()
        self.calendar_generator = CalendarGenerator()

    def validate_live_event(self, event: Dict, venue_name: str) -> Dict[str, Any]:
        """
        Validate a live event against schema and business rules

        Returns:
            Dict with validation results
        """
        validation_result = {
            "is_valid": True,
            "errors": [],
            "warnings": [],
            "venue": venue_name,
            "event_title": event.get("title", "Unknown"),
            "event_date": event.get("date", "Unknown"),
            "event_time": event.get("time", "Unknown"),
        }

        # Get venue-specific schema
        try:
            schema = get_venue_schema(venue_name)
        except Exception as e:
            validation_result["is_valid"] = False
            validation_result["errors"].append(f"Schema error: {str(e)}")
            return validation_result

        # Schema validation
        schema_validation = SchemaRegistry.validate_event_data(
            event, venue_name.lower()
        )
        if not schema_validation["is_valid"]:
            validation_result["is_valid"] = False
            validation_result["errors"].extend(schema_validation["errors"])

        # Business rule validation
        validation_result["warnings"].extend(schema_validation["warnings"])

        # Date validation - should be in the future
        if "date" in event and event["date"]:
            try:
                event_date = datetime.strptime(event["date"], "%Y-%m-%d").date()
                today = datetime.now().date()

                if event_date < today:
                    validation_result["warnings"].append(
                        f"Event date {event['date']} is in the past"
                    )

                # Check if date is too far in the future (more than 1 year)
                if event_date > today + timedelta(days=365):
                    validation_result["warnings"].append(
                        f"Event date {event['date']} is more than 1 year in the future"
                    )

            except ValueError:
                validation_result["errors"].append(
                    f"Invalid date format: {event['date']}"
                )

        # Time validation
        if "time" in event and event["time"]:
            time_pattern = r"\d{1,2}:\d{2}\s*[AP]M"
            import re

            if not re.match(time_pattern, event["time"], re.IGNORECASE):
                validation_result["warnings"].append(
                    f"Time format may be non-standard: {event['time']}"
                )

        # URL validation
        if "url" in event and event["url"]:
            if not event["url"].startswith(("http://", "https://")):
                validation_result["warnings"].append(
                    f"URL may be malformed: {event['url']}"
                )

        return validation_result

    def test_venue_scraper_live(self, venue_name: str) -> Dict[str, Any]:
        """
        Test a specific venue scraper with live data

        Returns:
            Dict with test results
        """
        print(f"\n--- Testing {venue_name} Scraper Live ---")

        # Get the specific scraper
        scraper_attr = f"{venue_name.lower()}_scraper"
        if not hasattr(self.scraper, scraper_attr):
            return {
                "success": False,
                "error": f"Scraper not found: {scraper_attr}",
                "events_found": 0,
                "valid_events": 0,
            }

        venue_scraper = getattr(self.scraper, scraper_attr)

        try:
            # Scrape events from live venue
            print(f"Scraping events from {venue_name}...")
            events = venue_scraper.scrape_events()

            if not events:
                print(f"No events found for {venue_name}")
                return {
                    "success": True,
                    "events_found": 0,
                    "valid_events": 0,
                    "note": "No events currently available",
                }

            print(f"Found {len(events)} events for {venue_name}")

            # Validate each event
            valid_events = 0
            validation_results = []

            for i, event in enumerate(events):
                print(f"  Validating event {i+1}: {event.get('title', 'Unknown')}")
                validation = self.validate_live_event(event, venue_name)
                validation_results.append(validation)

                if validation["is_valid"]:
                    valid_events += 1
                    print(f"    ✅ Valid event")
                else:
                    print(f"    ❌ Invalid event: {validation['errors']}")

                # Print first few events for inspection
                if i < 3:
                    print(f"    Sample event data: {json.dumps(event, indent=4)}")

            success = valid_events > 0

            return {
                "success": success,
                "events_found": len(events),
                "valid_events": valid_events,
                "validation_results": validation_results,
                "venue": venue_name,
            }

        except Exception as e:
            print(f"Error testing {venue_name}: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "events_found": 0,
                "valid_events": 0,
                "venue": venue_name,
            }


# Initialize test framework
live_test_framework = LiveIntegrationTestFramework()


@pytest.mark.live
@pytest.mark.slow
@pytest.mark.skipif(not firecrawl_api_key, reason=firecrawl_skip_reason)
class TestLiveScraperIntegration:
    """Test live scraper integration with real venues"""

    def test_all_venue_scrapers_live(self):
        """Test all venue scrapers with live data"""
        print("\n=== Testing All Venue Scrapers Live ===")

        # List of all venues to test
        venues = [
            "AFS",
            "Hyperreal",
            "FirstLight",
            "Symphony",
            "EarlyMusic",
            "LaFollia",
            "AlienatedMajesty",
        ]

        results = {}
        total_events = 0
        total_valid_events = 0
        successful_venues = 0

        for venue in venues:
            result = live_test_framework.test_venue_scraper_live(venue)
            results[venue] = result

            if result["success"]:
                successful_venues += 1
                total_events += result["events_found"]
                total_valid_events += result["valid_events"]

        # Print summary
        print(f"\n=== Live Test Summary ===")
        print(f"Successful venues: {successful_venues}/{len(venues)}")
        print(f"Total events found: {total_events}")
        print(f"Total valid events: {total_valid_events}")

        for venue, result in results.items():
            status = "✅" if result["success"] else "❌"
            print(
                f"{status} {venue}: {result['events_found']} events, {result['valid_events']} valid"
            )
            if not result["success"] and "error" in result:
                print(f"    Error: {result['error']}")

        # Assertions
        assert (
            successful_venues >= 3
        ), f"At least 3 venues should work, but only {successful_venues} succeeded"
        assert (
            total_valid_events >= 5
        ), f"Should find at least 5 valid events, but found {total_valid_events}"

        return results


@pytest.mark.live
@pytest.mark.slow
@pytest.mark.skipif(not firecrawl_api_key, reason=firecrawl_skip_reason)
class TestLiveProcessingPipeline:
    """Test live processing pipeline with real data"""

    def test_live_scraping_to_processing(self):
        """Test complete live scraping to processing pipeline"""
        print("\n=== Testing Live Scraping to Processing Pipeline ===")

        # Step 1: Scrape live data
        print("Step 1: Scraping live data from all venues...")
        scraper = MultiVenueScraper()
        scraped_events = scraper.scrape_all_venues()

        print(f"Scraped {len(scraped_events)} total events")

        # Group by venue for analysis
        events_by_venue = {}
        for event in scraped_events:
            venue = event.get("venue", "Unknown")
            if venue not in events_by_venue:
                events_by_venue[venue] = []
            events_by_venue[venue].append(event)

        print("Events by venue:")
        for venue, events in events_by_venue.items():
            print(f"  {venue}: {len(events)} events")

        # Assertions for scraping
        assert (
            len(scraped_events) >= 5
        ), f"Should scrape at least 5 events, but got {len(scraped_events)}"
        assert (
            len(events_by_venue) >= 3
        ), f"Should get events from at least 3 venues, but got {len(events_by_venue)}"

        # Step 2: Process events (if we have events)
        if scraped_events:
            print("\nStep 2: Processing events with AI...")

            # Take a sample of events for processing (to avoid API costs)
            sample_events = scraped_events[:3]  # Process first 3 events
            print(f"Processing sample of {len(sample_events)} events...")

            processor = EventProcessor()
            processed_events = processor.process_events(sample_events)

            print(f"Successfully processed {len(processed_events)} events")

            # Validate processed events
            for event in processed_events:
                assert "ai_rating" in event, "Processed event should have AI rating"
                assert (
                    "final_rating" in event
                ), "Processed event should have final rating"
                assert (
                    "rating_explanation" in event
                ), "Processed event should have rating explanation"
                assert (
                    1 <= event["final_rating"] <= 10
                ), f"Rating should be 1-10, got {event['final_rating']}"

            print("✅ All processed events have required fields")

            # Step 3: Generate summaries (if we have processed events)
            if processed_events:
                print("\nStep 3: Generating summaries...")

                summary_generator = SummaryGenerator()
                for event in processed_events[
                    :2
                ]:  # Generate summaries for first 2 events
                    summary = summary_generator.generate_summary(event)
                    assert summary is not None, "Summary should not be None"
                    assert len(summary) > 0, "Summary should not be empty"
                    print(f"  Generated summary: {summary[:100]}...")

                print("✅ Summary generation successful")

            return {
                "scraped_events": len(scraped_events),
                "processed_events": len(processed_events),
                "venues_with_events": len(events_by_venue),
            }

        return {"scraped_events": 0, "processed_events": 0, "venues_with_events": 0}


@pytest.mark.live
@pytest.mark.slow
@pytest.mark.skipif(not firecrawl_api_key, reason=firecrawl_skip_reason)
class TestLiveCalendarGeneration:
    """Test live calendar generation with real data"""

    def test_live_calendar_generation(self):
        """Test calendar generation with live scraped data"""
        print("\n=== Testing Live Calendar Generation ===")

        # Scrape some live data
        scraper = MultiVenueScraper()
        scraped_events = scraper.scrape_all_venues()

        if not scraped_events:
            pytest.skip("No events available for calendar generation test")

        # Take a sample for calendar generation
        sample_events = scraped_events[:5]  # Use first 5 events

        # Add required fields for calendar generation
        for event in sample_events:
            event["final_rating"] = 8  # Add a default rating
            event["rating_explanation"] = "Live test rating"

        print(f"Generating calendar for {len(sample_events)} events...")

        # Generate calendar
        calendar_generator = CalendarGenerator()

        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".ics", delete=False) as temp_file:
            try:
                calendar_generator.generate_ics(sample_events, temp_file.name)

                # Verify calendar file
                assert os.path.exists(temp_file.name), "Calendar file should be created"
                assert (
                    os.path.getsize(temp_file.name) > 0
                ), "Calendar file should not be empty"

                # Read and validate calendar content
                with open(temp_file.name, "r") as f:
                    calendar_content = f.read()

                # Check for required ICS elements
                required_elements = [
                    "BEGIN:VCALENDAR",
                    "VERSION:2.0",
                    "BEGIN:VEVENT",
                    "END:VEVENT",
                    "END:VCALENDAR",
                ]

                for element in required_elements:
                    assert (
                        element in calendar_content
                    ), f"Calendar should contain {element}"

                # Check that event titles are in calendar
                for event in sample_events:
                    if event.get("title"):
                        assert (
                            event["title"] in calendar_content
                        ), f"Event title should be in calendar: {event['title']}"

                print(
                    f"✅ Calendar generated successfully with {len(sample_events)} events"
                )
                print(f"Calendar file size: {os.path.getsize(temp_file.name)} bytes")

            finally:
                os.unlink(temp_file.name)

        return {"events_in_calendar": len(sample_events)}


@pytest.mark.live
@pytest.mark.slow
@pytest.mark.skipif(not firecrawl_api_key, reason=firecrawl_skip_reason)
def test_live_mini_refresh():
    """Test a mini version of the full refresh process with live data"""
    print("\n=== Testing Live Mini Refresh ===")

    # This simulates what happens in update_website_data.py
    results = {
        "scraping_start": datetime.now(),
        "venues_tested": 0,
        "total_events": 0,
        "valid_events": 0,
        "processing_success": False,
        "calendar_success": False,
    }

    try:
        # Step 1: Scrape from all venues
        print("Step 1: Scraping from all venues...")
        scraper = MultiVenueScraper()
        scraped_events = scraper.scrape_all_venues()

        results["total_events"] = len(scraped_events)
        results["venues_tested"] = len(
            set(event.get("venue", "Unknown") for event in scraped_events)
        )

        print(
            f"Scraped {len(scraped_events)} events from {results['venues_tested']} venues"
        )

        # Step 2: Validate events
        print("Step 2: Validating events...")
        valid_events = []
        for event in scraped_events:
            venue = event.get("venue", "Unknown")
            validation = live_test_framework.validate_live_event(event, venue)
            if validation["is_valid"]:
                valid_events.append(event)

        results["valid_events"] = len(valid_events)
        print(f"Validated {len(valid_events)} events")

        # Step 3: Process events (sample)
        if valid_events:
            print("Step 3: Processing events...")
            sample_events = valid_events[:3]  # Process sample

            processor = EventProcessor()
            processed_events = processor.process_events(sample_events)

            if processed_events:
                results["processing_success"] = True
                print(f"Successfully processed {len(processed_events)} events")

                # Step 4: Generate calendar
                print("Step 4: Generating calendar...")
                for event in processed_events:
                    event["final_rating"] = event.get("final_rating", 8)
                    event["rating_explanation"] = event.get(
                        "rating_explanation", "Live test"
                    )

                calendar_generator = CalendarGenerator()

                import tempfile

                with tempfile.NamedTemporaryFile(
                    suffix=".ics", delete=False
                ) as temp_file:
                    try:
                        calendar_generator.generate_ics(
                            processed_events, temp_file.name
                        )
                        results["calendar_success"] = True
                        print(f"Calendar generated successfully")
                    finally:
                        os.unlink(temp_file.name)

        results["scraping_end"] = datetime.now()
        results["duration"] = results["scraping_end"] - results["scraping_start"]

        # Print results
        print(f"\n=== Mini Refresh Results ===")
        print(f"Duration: {results['duration']}")
        print(f"Venues tested: {results['venues_tested']}")
        print(f"Total events: {results['total_events']}")
        print(f"Valid events: {results['valid_events']}")
        print(f"Processing success: {results['processing_success']}")
        print(f"Calendar success: {results['calendar_success']}")

        # Assertions
        assert (
            results["venues_tested"] >= 3
        ), f"Should test at least 3 venues, but tested {results['venues_tested']}"
        assert (
            results["total_events"] >= 5
        ), f"Should find at least 5 events, but found {results['total_events']}"
        assert (
            results["valid_events"] >= 3
        ), f"Should have at least 3 valid events, but had {results['valid_events']}"

        return results

    except Exception as e:
        print(f"Error during mini refresh: {str(e)}")
        results["error"] = str(e)
        raise


if __name__ == "__main__":
    # Run live tests manually
    pytest.main([__file__, "-v", "-s", "-m", "live"])
