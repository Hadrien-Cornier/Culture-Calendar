"""
Unit tests for the validation service
"""

import json
from unittest.mock import Mock, patch

from src.validation_service import (
    EventValidationService,
    ValidationLevel,
    quick_validate_events,
)


class TestEventValidationService:
    """Test the EventValidationService class"""

    def setup_method(self):
        """Setup for each test"""
        self.validator = EventValidationService()

    def test_validate_event_schema_valid(self):
        """Test schema validation with valid event"""
        valid_event = {
            "title": "Test Movie",
            "date": "2025-01-15",
            "venue": "AFS",
            "type": "screening",
            "description": "A great movie",
        }

        result = self.validator.validate_event_schema(valid_event)

        assert result.passed is True
        assert result.level == ValidationLevel.INFO
        assert "Schema validation passed" in result.message

    def test_validate_event_schema_missing_fields(self):
        """Test schema validation with missing required fields"""
        invalid_event = {
            "title": "Test Movie",
            # Missing date, venue, type
        }

        result = self.validator.validate_event_schema(invalid_event)

        assert result.passed is False
        assert result.level == ValidationLevel.CRITICAL
        assert "Missing required fields" in result.message

    def test_validate_event_schema_invalid_date(self):
        """Test schema validation with invalid date format"""
        invalid_event = {
            "title": "Test Movie",
            "date": "not-a-date",
            "venue": "AFS",
            "type": "screening",
        }

        result = self.validator.validate_event_schema(invalid_event)

        assert result.passed is False
        assert result.level == ValidationLevel.CRITICAL
        assert "Invalid date format" in result.message

    def test_validate_event_schema_unknown_type(self):
        """Test schema validation with unknown event type"""
        event = {
            "title": "Test Event",
            "date": "2025-01-15",
            "venue": "Test Venue",
            "type": "unknown_type",
        }

        result = self.validator.validate_event_schema(event)

        assert result.passed is False
        assert result.level == ValidationLevel.WARNING
        assert "Unknown event type" in result.message

    @patch("src.validation_service.LLMService")
    def test_validate_event_content_with_llm_no_api_key(self, mock_llm_service):
        """Test LLM validation when no API key is available"""
        mock_llm_instance = Mock()
        mock_llm_instance.anthropic_api_key = None
        mock_llm_service.return_value = mock_llm_instance

        validator = EventValidationService(mock_llm_instance)

        event = {
            "title": "Test Movie",
            "date": "2025-01-15",
            "venue": "AFS",
            "type": "screening",
        }

        result = validator.validate_event_content_with_llm(event)

        assert result.passed is True
        assert result.level == ValidationLevel.INFO
        assert "LLM validation skipped" in result.message

    @patch("src.validation_service.LLMService")
    def test_validate_event_content_with_llm_success(self, mock_llm_service):
        """Test successful LLM validation"""
        mock_llm_instance = Mock()
        mock_llm_instance.anthropic_api_key = "test-key"
        mock_llm_instance.analyze_with_anthropic.return_value = json.dumps(
            {
                "is_valid": True,
                "confidence": 0.9,
                "issues": [],
                "reasoning": "This appears to be a legitimate movie screening",
            }
        )
        mock_llm_service.return_value = mock_llm_instance

        validator = EventValidationService(mock_llm_instance)

        event = {
            "title": "Citizen Kane",
            "date": "2025-01-15",
            "venue": "AFS",
            "type": "screening",
            "description": "Classic film by Orson Welles",
        }

        result = validator.validate_event_content_with_llm(event)

        assert result.passed is True
        assert result.level == ValidationLevel.INFO
        assert "LLM validation passed" in result.message
        assert result.details["confidence"] == 0.9

    @patch("src.validation_service.LLMService")
    def test_validate_event_content_with_llm_failure(self, mock_llm_service):
        """Test failed LLM validation"""
        mock_llm_instance = Mock()
        mock_llm_instance.anthropic_api_key = "test-key"
        mock_llm_instance.analyze_with_anthropic.return_value = json.dumps(
            {
                "is_valid": False,
                "confidence": 0.2,
                "issues": ["Title appears to be spam", "No meaningful description"],
                "reasoning": "This does not appear to be a legitimate event",
            }
        )
        mock_llm_service.return_value = mock_llm_instance

        validator = EventValidationService(mock_llm_instance)

        event = {
            "title": "SPAM EVENT!!!",
            "date": "2025-01-15",
            "venue": "Unknown",
            "type": "screening",
            "description": "Click here now!!!",
        }

        result = validator.validate_event_content_with_llm(event)

        assert result.passed is False
        assert result.level == ValidationLevel.CRITICAL
        assert "LLM validation failed" in result.message
        assert "spam" in result.details["reasoning"].lower()

    def test_validate_scraper_health_good(self):
        """Test scraper health check with good events"""
        events = [
            {
                "title": "Movie 1",
                "date": "2025-01-15",
                "venue": "AFS",
                "type": "screening",
            },
            {
                "title": "Movie 2",
                "date": "2025-01-16",
                "venue": "AFS",
                "type": "screening",
            },
            {
                "title": "Movie 3",
                "date": "2025-01-17",
                "venue": "AFS",
                "type": "screening",
            },
        ]

        health_check = self.validator.validate_scraper_health("AFS", events)

        assert health_check.scraper_name == "AFS"
        assert health_check.events_found == 3
        assert health_check.events_validated == 3
        assert health_check.success_rate == 1.0
        assert len(health_check.errors) == 0

    def test_validate_scraper_health_poor(self):
        """Test scraper health check with poor events"""
        events = [
            {"title": "", "date": "bad-date", "venue": "AFS"},  # Invalid  # Invalid
            {
                "title": "Good Movie",
                "date": "2025-01-15",
                "venue": "AFS",
                "type": "screening",
            },
        ]

        health_check = self.validator.validate_scraper_health("AFS", events)

        assert health_check.scraper_name == "AFS"
        assert health_check.events_found == 2
        assert health_check.events_validated == 1
        assert health_check.success_rate == 0.5
        assert len(health_check.errors) > 0

    def test_validate_all_scrapers_pass(self):
        """Test validation of all scrapers - passing case"""
        scraper_results = {
            "AFS": [
                {
                    "title": "Movie 1",
                    "date": "2025-01-15",
                    "venue": "AFS",
                    "type": "screening",
                },
                {
                    "title": "Movie 2",
                    "date": "2025-01-16",
                    "venue": "AFS",
                    "type": "screening",
                },
            ],
            "Hyperreal": [
                {
                    "title": "Movie 3",
                    "date": "2025-01-17",
                    "venue": "Hyperreal",
                    "type": "screening",
                },
            ],
        }

        should_continue, health_checks = self.validator.validate_all_scrapers(
            scraper_results
        )

        assert should_continue is True
        assert len(health_checks) == 2
        assert all(hc.success_rate >= 0.5 for hc in health_checks)

    def test_validate_all_scrapers_fail(self):
        """Test validation of all scrapers - failing case"""
        scraper_results = {
            "AFS": [
                {"title": "", "date": "bad-date"},  # Invalid
            ],
            "Hyperreal": [
                {"title": "", "venue": ""},  # Invalid
            ],
        }

        should_continue, health_checks = self.validator.validate_all_scrapers(
            scraper_results
        )

        assert should_continue is False
        assert len(health_checks) == 2
        assert all(hc.success_rate < 0.5 for hc in health_checks)


def test_quick_validate_events():
    """Test the quick validation convenience function"""
    good_events = [
        {"title": "Movie 1", "date": "2025-01-15", "venue": "AFS", "type": "screening"},
        {"title": "Movie 2", "date": "2025-01-16", "venue": "AFS", "type": "screening"},
    ]

    bad_events = [
        {"title": "", "date": "bad-date"},
    ]

    assert quick_validate_events(good_events, "AFS") is True
    assert quick_validate_events(bad_events, "AFS") is False
    assert quick_validate_events([], "AFS") is False  # No events
