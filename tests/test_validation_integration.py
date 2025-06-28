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
