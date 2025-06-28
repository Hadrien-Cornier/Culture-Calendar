"""
Integration tests for validation system with real scrapers
"""

from unittest.mock import Mock, patch

import pytest

from src.scraper import MultiVenueScraper
from src.validation_service import EventValidationService


@pytest.mark.integration
class TestValidationIntegration:
    """Integration tests for validation with scraper system"""

    def setup_method(self):
        """Setup for each test"""
        self.scraper = MultiVenueScraper()
        self.validator = EventValidationService()

    def test_scraper_initialization(self):
        """Test that all scrapers can be initialized"""
        assert self.scraper.afs_scraper is not None
        assert self.scraper.hyperreal_scraper is not None
        assert self.scraper.alienated_majesty_scraper is not None
        assert self.scraper.first_light_scraper is not None
        assert self.scraper.symphony_scraper is not None
        assert self.scraper.early_music_scraper is not None
        assert self.scraper.la_follia_scraper is not None

    @patch("src.base_scraper.BaseScraper.scrape_events")
    def test_validation_with_mocked_scrapers(self, mock_scrape):
        """Test validation system with mocked scraper data"""
        # Mock good scraper results
        mock_scrape.return_value = [
            {
                "title": "Citizen Kane",
                "date": "2025-01-15",
                "time": "7:00 PM",
                "venue": "AFS",
                "type": "screening",
                "description": "Classic Orson Welles film",
            },
            {
                "title": "Casablanca",
                "date": "2025-01-16",
                "time": "7:30 PM",
                "venue": "AFS",
                "type": "screening",
                "description": "Bogart and Bergman classic",
            },
        ]

        # Test AFS scraper
        afs_events = self.scraper.afs_scraper.scrape_events()

        # Validate the events
        health_check = self.validator.validate_scraper_health("AFS", afs_events)

        assert health_check.events_found == 2
        assert health_check.success_rate > 0.5
        assert len(health_check.errors) == 0

    @patch("src.base_scraper.BaseScraper.scrape_events")
    def test_validation_with_bad_data(self, mock_scrape):
        """Test validation system with problematic data"""
        # Mock bad scraper results
        mock_scrape.return_value = [
            {
                "title": "",  # Missing title
                "date": "invalid-date",  # Bad date
                "venue": "AFS",
                # Missing required fields
            },
            {
                "title": "Some Movie",
                "date": "2025-01-15",
                # Missing venue and type
            },
        ]

        # Test scraper
        events = self.scraper.afs_scraper.scrape_events()

        # Validate the events
        health_check = self.validator.validate_scraper_health("AFS", events)

        assert health_check.events_found == 2
        assert health_check.success_rate < 0.5  # Should fail validation
        assert len(health_check.errors) > 0

    def test_multi_scraper_validation_mock(self):
        """Test validation of multiple scrapers"""
        # Create mock data for multiple scrapers
        mock_data = {
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
            "Hyperreal Film Club": [
                {
                    "title": "Movie 3",
                    "date": "2025-01-17",
                    "venue": "Hyperreal Film Club",
                    "type": "screening",
                },
            ],
            "Alienated Majesty Books": [
                {
                    "title": "Book Club 1",
                    "date": "2025-01-18",
                    "venue": "Alienated Majesty Books",
                    "type": "book_club",
                },
            ],
        }

        # Test validation
        should_continue, health_checks = self.validator.validate_all_scrapers(mock_data)

        assert should_continue is True
        assert len(health_checks) == 3

        # Check each health check
        scraper_names = [hc.scraper_name for hc in health_checks]
        assert "AFS" in scraper_names
        assert "Hyperreal Film Club" in scraper_names
        assert "Alienated Majesty Books" in scraper_names

    def test_validation_failure_threshold(self):
        """Test that validation fails when too many scrapers fail"""
        # Create data where most scrapers fail
        mock_data = {
            "AFS": [
                {"title": "", "date": "bad-date"},  # Invalid
            ],
            "Hyperreal Film Club": [
                {"title": "", "venue": ""},  # Invalid
            ],
            "Good Scraper": [
                {
                    "title": "Good Event",
                    "date": "2025-01-15",
                    "venue": "Test",
                    "type": "screening",
                },
            ],
        }

        # Test validation
        should_continue, health_checks = self.validator.validate_all_scrapers(mock_data)

        # Should fail because 2/3 scrapers failed (< 50% success rate)
        assert should_continue is False
        assert len(health_checks) == 3

    @patch("src.validation_service.LLMService")
    def test_validation_without_llm(self, mock_llm_service):
        """Test validation system without LLM service"""
        # Mock LLM service to not have API key
        mock_llm_instance = Mock()
        mock_llm_instance.anthropic_api_key = None
        mock_llm_service.return_value = mock_llm_instance

        validator = EventValidationService(mock_llm_instance)

        # Test with good data
        events = [
            {
                "title": "Test Movie",
                "date": "2025-01-15",
                "venue": "AFS",
                "type": "screening",
            }
        ]

        health_check = validator.validate_scraper_health("AFS", events)

        # Should still pass basic validation without LLM
        assert health_check.success_rate > 0.5
        assert health_check.events_validated > 0
