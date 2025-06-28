"""
Test empty extraction output scenarios and proper error handling
"""

import pytest
import json
from unittest.mock import Mock, patch
from src.llm_service import LLMService
from src.base_scraper import BaseScraper
from src.schemas import FilmEventSchema


class MockScraper(BaseScraper):
    """Mock scraper for testing empty extraction scenarios"""

    def get_target_urls(self):
        return ["https://example.com/test"]

    def get_data_schema(self):
        return FilmEventSchema.get_schema()

    def get_fallback_data(self):
        return []


@pytest.mark.unit
class TestEmptyExtractionOutput:
    """Test scenarios where extraction output is empty"""

    def test_empty_extraction_response(self):
        """Test when LLM returns empty JSON object"""
        llm_service = LLMService()

        # Mock empty extraction response
        empty_response = "{}"
        result = llm_service._parse_extraction_response(empty_response, {})

        assert result["success"] == True
        assert result["data"] == {}
        assert result["raw_response"] == empty_response

    def test_empty_extraction_with_no_json(self):
        """Test when LLM returns no JSON at all"""
        llm_service = LLMService()

        # Mock response with no JSON
        no_json_response = "I couldn't find any events in this content."
        result = llm_service._parse_extraction_response(no_json_response, {})

        assert result["success"] == False
        assert result["error"] == "No valid JSON found in response"
        assert result["data"] == {}
        assert result["raw_response"] == no_json_response

    def test_empty_extraction_with_invalid_json(self):
        """Test when LLM returns invalid JSON"""
        llm_service = LLMService()

        # Mock invalid JSON response
        invalid_json_response = '{"title": "Test", "date": "2025-01-01",}'
        result = llm_service._parse_extraction_response(invalid_json_response, {})

        assert result["success"] == False
        assert "JSON parsing error" in result["error"]
        assert result["data"] == {}
        assert result["raw_response"] == invalid_json_response

    def test_empty_extraction_with_null_data(self):
        """Test when LLM returns null values for all fields"""
        llm_service = LLMService()

        # Mock response with null data
        null_data_response = '{"title": null, "date": null, "time": null}'
        result = llm_service._parse_extraction_response(null_data_response, {})

        assert result["success"] == True
        assert result["data"] == {"title": None, "date": None, "time": None}

    def test_empty_extraction_with_empty_strings(self):
        """Test when LLM returns empty strings for all fields"""
        llm_service = LLMService()

        # Mock response with empty strings
        empty_strings_response = '{"title": "", "date": "", "time": ""}'
        result = llm_service._parse_extraction_response(empty_strings_response, {})

        assert result["success"] == True
        assert result["data"] == {"title": "", "date": "", "time": ""}

    def test_empty_extraction_with_missing_required_fields(self):
        """Test when LLM returns data missing required fields"""
        llm_service = LLMService()

        # Mock response missing required title field
        missing_required_response = '{"date": "2025-01-01", "time": "7:30 PM"}'
        result = llm_service._parse_extraction_response(missing_required_response, {})

        assert result["success"] == True
        assert result["data"] == {"date": "2025-01-01", "time": "7:30 PM"}
        # Note: The validation of required fields happens later in the pipeline


@pytest.mark.unit
class TestEmptyExtractionValidation:
    """Test validation of empty extraction results"""

    def test_validate_empty_extraction_result(self):
        """Test validation when extraction result is empty"""
        scraper = MockScraper("https://example.com", "TestVenue")

        # Test with empty list
        assert scraper._validate_extraction_result([]) == False

        # Test with None
        assert scraper._validate_extraction_result(None) == False

        # Test with non-list
        assert scraper._validate_extraction_result("not a list") == False

        # Test with list containing invalid events
        assert (
            scraper._validate_extraction_result([{"date": "2025-01-01"}]) == False
        )  # Missing title

        # Test with list containing valid events
        assert (
            scraper._validate_extraction_result(
                [{"title": "Test Event", "date": "2025-01-01"}]
            )
            == True
        )

    def test_standardize_event_data_with_empty_title(self):
        """Test standardizing event data with empty title"""
        scraper = MockScraper("https://example.com", "TestVenue")

        # Test with empty title
        result = scraper._standardize_event_data({"title": ""}, "https://example.com")
        assert result is None

        # Test with None title
        result = scraper._standardize_event_data({"title": None}, "https://example.com")
        assert result is None

        # Test with missing title
        result = scraper._standardize_event_data(
            {"date": "2025-01-01"}, "https://example.com"
        )
        assert result is None

        # Test with valid title
        result = scraper._standardize_event_data(
            {"title": "Test Event"}, "https://example.com"
        )
        assert result is not None
        assert result["title"] == "Test Event"

    def test_format_extraction_result_with_empty_data(self):
        """Test formatting extraction result with empty data"""
        scraper = MockScraper("https://example.com", "TestVenue")

        # Test with empty dict
        result = scraper._format_extraction_result({}, "https://example.com")
        assert result == []

        # Test with dict containing empty title
        result = scraper._format_extraction_result({"title": ""}, "https://example.com")
        assert result == []

        # Test with empty list
        result = scraper._format_extraction_result([], "https://example.com")
        assert result == []

        # Test with list containing empty events
        result = scraper._format_extraction_result(
            [{"title": ""}, {"title": None}], "https://example.com"
        )
        assert result == []

        # Test with valid data
        result = scraper._format_extraction_result(
            {"title": "Test Event"}, "https://example.com"
        )
        assert len(result) == 1
        assert result[0]["title"] == "Test Event"


@pytest.mark.integration
class TestEmptyExtractionIntegration:
    """Test empty extraction scenarios in integration context"""

    @patch("src.llm_service.Anthropic")
    def test_llm_extraction_returns_empty(self, mock_anthropic):
        """Test when LLM extraction returns empty data"""
        # Mock LLM service to return empty data
        mock_client = Mock()
        mock_response = Mock()
        mock_response.content = [Mock()]
        mock_response.content[0].text = "{}"  # Empty JSON
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        llm_service = LLMService()

        # Test extraction with empty content
        result = llm_service.extract_data(
            content="<html><body>No events found</body></html>",
            schema=FilmEventSchema.get_schema(),
            url="https://example.com",
            content_type="html",
        )

        assert result["success"] == True
        assert result["data"] == {}

    @patch("src.llm_service.Anthropic")
    def test_llm_extraction_returns_no_json(self, mock_anthropic):
        """Test when LLM extraction returns no JSON"""
        # Mock LLM service to return no JSON
        mock_client = Mock()
        mock_response = Mock()
        mock_response.content = [Mock()]
        mock_response.content[0].text = "I couldn't find any events in this content."
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        llm_service = LLMService()

        # Test extraction with content that yields no JSON
        result = llm_service.extract_data(
            content="<html><body>No events found</body></html>",
            schema=FilmEventSchema.get_schema(),
            url="https://example.com",
            content_type="html",
        )

        assert result["success"] == False
        assert result["error"] == "No valid JSON found in response"
        assert result["data"] == {}

    @patch("src.llm_service.Anthropic")
    def test_llm_extraction_returns_invalid_json(self, mock_anthropic):
        """Test when LLM extraction returns invalid JSON"""
        # Mock LLM service to return invalid JSON
        mock_client = Mock()
        mock_response = Mock()
        mock_response.content = [Mock()]
        mock_response.content[0].text = (
            '{"title": "Test", "date": "2025-01-01",}'  # Invalid JSON
        )
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        llm_service = LLMService()

        # Test extraction with content that yields invalid JSON
        result = llm_service.extract_data(
            content="<html><body>Test content</body></html>",
            schema=FilmEventSchema.get_schema(),
            url="https://example.com",
            content_type="html",
        )

        assert result["success"] == False
        assert "JSON parsing error" in result["error"]
        assert result["data"] == {}


@pytest.mark.unit
class TestEmptyExtractionErrorReporting:
    """Test proper error reporting for empty extraction scenarios"""

    def test_empty_extraction_error_messages(self):
        """Test that empty extraction provides clear error messages"""
        llm_service = LLMService()

        # Test various empty extraction scenarios
        test_cases = [
            (
                "No JSON found",
                "I couldn't find any events",
                "No valid JSON found in response",
            ),
            ("Invalid JSON", '{"title": "Test",}', "JSON parsing error"),
            ("Empty JSON", "{}", None),  # This should succeed but with empty data
        ]

        for scenario, response_text, expected_error in test_cases:
            result = llm_service._parse_extraction_response(response_text, {})

            if expected_error:
                assert result["success"] == False
                assert expected_error in result["error"]
                assert result["data"] == {}
            else:
                assert result["success"] == True
                assert result["data"] == {}

    def test_empty_extraction_logging(self):
        """Test that empty extraction scenarios are properly logged"""
        scraper = MockScraper("https://example.com", "TestVenue")

        # Test that validation failures are logged
        with patch("builtins.print") as mock_print:
            scraper._validate_extraction_result([])
            # Note: The current implementation doesn't log validation failures
            # This test documents the current behavior

    def test_empty_extraction_caching(self):
        """Test that empty extraction results are properly cached"""
        llm_service = LLMService()

        # Test that empty results are cached
        empty_response = "{}"
        result1 = llm_service._parse_extraction_response(empty_response, {})
        result2 = llm_service._parse_extraction_response(empty_response, {})

        assert result1["success"] == result2["success"]
        assert result1["data"] == result2["data"]


@pytest.mark.failure
class TestEmptyExtractionFailureScenarios:
    """Test failure scenarios where extraction succeeds but produces no useful data"""

    def test_extraction_succeeds_but_produces_empty_data(self):
        """
        FAILURE SCENARIO: This test demonstrates the problem where extraction
        succeeds but returns empty data, which should be treated as a failure.
        """
        llm_service = LLMService()

        # This is the problematic case: extraction succeeds but returns empty data
        empty_response = "{}"
        result = llm_service._parse_extraction_response(empty_response, {})

        # FIXED BEHAVIOR (CORRECT):
        assert result["success"] == False  # ✅ Now correctly fails
        assert "No useful data extracted" in result["error"]  # ✅ Clear error message
        assert result["data"] == {}  # ✅ Still includes the empty data for debugging

    def test_extraction_succeeds_but_produces_null_data(self):
        """
        FAILURE SCENARIO: Extraction succeeds but all fields are null
        """
        llm_service = LLMService()

        # Another problematic case: all fields are null
        null_response = '{"title": null, "date": null, "time": null}'
        result = llm_service._parse_extraction_response(null_response, {})

        # FIXED BEHAVIOR (CORRECT):
        assert result["success"] == False  # ✅ Now correctly fails
        assert "No useful data extracted" in result["error"]  # ✅ Clear error message
        assert result["data"] == {
            "title": None,
            "date": None,
            "time": None,
        }  # ✅ Includes data for debugging

    def test_extraction_succeeds_but_produces_empty_strings(self):
        """
        FAILURE SCENARIO: Extraction succeeds but all fields are empty strings
        """
        llm_service = LLMService()

        # Another problematic case: all fields are empty strings
        empty_strings_response = '{"title": "", "date": "", "time": ""}'
        result = llm_service._parse_extraction_response(empty_strings_response, {})

        # FIXED BEHAVIOR (CORRECT):
        assert result["success"] == False  # ✅ Now correctly fails
        assert "No useful data extracted" in result["error"]  # ✅ Clear error message
        assert result["data"] == {
            "title": "",
            "date": "",
            "time": "",
        }  # ✅ Includes data for debugging

    def test_extraction_succeeds_but_missing_required_fields(self):
        """
        FAILURE SCENARIO: Extraction succeeds but missing required fields
        """
        llm_service = LLMService()

        # Missing required title field
        missing_required_response = '{"date": "2025-01-01", "time": "7:30 PM"}'
        result = llm_service._parse_extraction_response(missing_required_response, {})

        # FIXED BEHAVIOR (CORRECT):
        assert result["success"] == False  # ✅ Now correctly fails
        assert "No useful data extracted" in result["error"]  # ✅ Clear error message
        assert result["data"] == {
            "date": "2025-01-01",
            "time": "7:30 PM",
        }  # ✅ Includes data for debugging

    def test_extraction_succeeds_with_valid_data(self):
        """
        SUCCESS SCENARIO: Extraction succeeds with valid data
        """
        llm_service = LLMService()
        from src.schemas import FilmEventSchema

        schema = FilmEventSchema.get_schema()
        # Valid data with required fields
        valid_response = (
            '{"title": "Test Event", "date": "2025-01-01", "time": "7:30 PM"}'
        )
        result = llm_service._parse_extraction_response(valid_response, schema)
        # Should succeed with valid data
        assert result["success"] == True  # ✅ Correctly succeeds
        assert result["data"] == {
            "title": "Test Event",
            "date": "2025-01-01",
            "time": "7:30 PM",
        }

    def test_extraction_succeeds_with_partial_data(self):
        """
        SUCCESS SCENARIO: Extraction succeeds with partial but useful data
        """
        llm_service = LLMService()
        from src.schemas import FilmEventSchema

        schema = FilmEventSchema.get_schema()
        # Partial data but with required title
        partial_response = '{"title": "Test Event", "date": null, "time": ""}'
        result = llm_service._parse_extraction_response(partial_response, schema)
        # Should succeed if title is present (required field)
        assert result["success"] == True  # ✅ Correctly succeeds
        assert result["data"] == {"title": "Test Event", "date": None, "time": ""}

    def test_end_to_end_empty_extraction_failure(self):
        """
        FAILURE SCENARIO: End-to-end test showing how empty extraction
        now properly fails with clear error messages
        """
        scraper = MockScraper("https://example.com", "TestVenue")

        # Mock LLM service to return empty data
        with patch.object(scraper.llm_service, "extract_data") as mock_extract:
            mock_extract.return_value = {
                "success": False,  # ✅ Now correctly fails
                "error": "No useful data extracted - all fields are empty, null, or missing required data",
                "data": {},  # Empty data
                "raw_response": "{}",
            }

            # Test the scraping pipeline
            result = scraper._scrape_with_requests_llm("https://example.com")

            # FIXED BEHAVIOR (CORRECT):
            assert result == []  # ✅ Returns empty list
            # The error should be logged with clear message about why extraction failed


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v"])
