"""
Unit tests for Culture Calendar components
"""

import pytest
import json
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from src.llm_service import LLMService
from src.base_scraper import BaseScraper, ScrapingTier
from src.schemas import SchemaRegistry, get_venue_schema, FilmEventSchema
from src.summary_generator import SummaryGenerator
from src.calendar_generator import CalendarGenerator
from src.scraper_generator import ScraperGenerator, create_new_venue_scraper


class TestLLMService:
    """Test LLM service functionality"""

    @pytest.fixture
    def llm_service(self, mock_env_vars):
        """Create LLM service with mocked environment"""
        with patch("src.llm_service.Anthropic") as mock_anthropic:
            service = LLMService()
            service.anthropic = Mock()
            return service

    def test_initialization(self, mock_env_vars):
        """Test LLM service initialization"""
        with patch("src.llm_service.Anthropic"):
            service = LLMService()
            assert service.anthropic_api_key == "test_anthropic_key"
            assert service.firecrawl_api_key == "test_firecrawl_key"

    def test_extract_data(self, llm_service, sample_film_event):
        """Test data extraction from content"""
        # Mock the API response
        mock_response = Mock()
        mock_response.content = [Mock()]
        mock_response.content[0].text = json.dumps([sample_film_event])
        llm_service.anthropic.messages.create.return_value = mock_response

        schema = FilmEventSchema.get_schema()
        result = llm_service.extract_data("test content", schema)

        assert isinstance(result, dict)
        assert "extracted_events" in result or "title" in result

    def test_validate_extraction(self, llm_service, sample_film_event):
        """Test extraction validation"""
        # Mock validation response
        mock_response = Mock()
        mock_response.content = [Mock()]
        mock_response.content[0].text = (
            "VALID: All required fields present and well-formatted"
        )
        llm_service.anthropic.messages.create.return_value = mock_response

        schema = FilmEventSchema.get_schema()
        result = llm_service.validate_extraction(sample_film_event, schema)

        assert isinstance(result, dict)
        assert "is_valid" in result

    def test_similarity_detection(self, llm_service):
        """Test event similarity detection"""
        event1 = {"title": "The Great Movie", "date": "2025-07-15"}
        event2 = {"title": "Great Movie", "date": "2025-07-15"}

        # Mock similarity response
        mock_response = Mock()
        mock_response.content = [Mock()]
        mock_response.content[0].text = "SIMILAR: 0.95"
        llm_service.anthropic.messages.create.return_value = mock_response

        result = llm_service.detect_similarity(event1, event2)

        assert isinstance(result, dict)
        assert "similarity_score" in result


class TestBaseScraper:
    """Test base scraper functionality"""

    @pytest.fixture
    def test_scraper(self, mock_env_vars):
        """Create a test scraper"""

        class TestScraper(BaseScraper):
            def get_target_urls(self):
                return ["https://test.com/events"]

            def get_data_schema(self):
                return FilmEventSchema.get_schema()

            def get_fallback_data(self):
                return []

        return TestScraper(base_url="https://test.com", venue_name="Test")

    def test_initialization(self, test_scraper):
        """Test scraper initialization"""
        assert test_scraper.base_url == "https://test.com"
        assert test_scraper.venue_name == "Test"
        assert hasattr(test_scraper, "llm_service")

    def test_schema_methods(self, test_scraper):
        """Test schema-related methods"""
        urls = test_scraper.get_target_urls()
        assert isinstance(urls, list)
        assert len(urls) > 0

        schema = test_scraper.get_data_schema()
        assert isinstance(schema, dict)
        assert "title" in schema

        fallback = test_scraper.get_fallback_data()
        assert isinstance(fallback, list)

    @patch("requests.get")
    def test_requests_tier(self, mock_get, test_scraper, sample_film_event):
        """Test requests-based scraping tier"""
        # Mock successful HTTP response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "<html>Test content</html>"
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # Mock LLM extraction
        test_scraper.llm_service.extract_data = Mock(
            return_value={"extracted_events": [sample_film_event]}
        )

        result = test_scraper._scrape_with_requests_llm("https://test.com/events")

        assert isinstance(result, list)
        mock_get.assert_called_once()

    def test_fallback_tier(self, test_scraper):
        """Test fallback tier returns empty list"""
        result = test_scraper._scrape_with_fallback("https://test.com/events")
        assert result == []

    def test_cache_functionality(self, test_scraper):
        """Test caching system"""
        # Test cache key generation
        cache_key = test_scraper._generate_cache_key("https://test.com/events")
        assert isinstance(cache_key, str)
        assert len(cache_key) > 0


class TestSchemaRegistry:
    """Test schema registry functionality"""

    def test_get_schema(self):
        """Test schema retrieval"""
        film_schema = SchemaRegistry.get_schema("film")
        assert isinstance(film_schema, dict)
        assert "title" in film_schema
        assert "director" in film_schema

        book_schema = SchemaRegistry.get_schema("book_club")
        assert isinstance(book_schema, dict)
        assert "book" in book_schema
        assert "author" in book_schema

    def test_available_types(self):
        """Test getting available schema types"""
        types = SchemaRegistry.get_available_types()
        assert isinstance(types, list)
        assert "film" in types
        assert "book_club" in types
        assert "concert" in types

    def test_validate_event_data(self, sample_film_event):
        """Test event data validation"""
        result = SchemaRegistry.validate_event_data(sample_film_event, "film")

        assert isinstance(result, dict)
        assert "is_valid" in result
        assert "errors" in result
        assert "warnings" in result

    def test_venue_schema_mapping(self):
        """Test venue-specific schema mapping"""
        afs_schema = get_venue_schema("AFS")
        assert isinstance(afs_schema, dict)
        assert "director" in afs_schema  # Film-specific field

        firstlight_schema = get_venue_schema("FirstLight")
        assert isinstance(firstlight_schema, dict)
        assert "book" in firstlight_schema  # Book club-specific field


class TestSummaryGenerator:
    """Test summary generator functionality"""

    @pytest.fixture
    def summary_generator(self, mock_env_vars, temp_cache_file):
        """Create summary generator with mocked dependencies"""
        with patch("src.summary_generator.Anthropic") as mock_anthropic:
            with patch(
                "src.summary_generator.SummaryGenerator._load_cache"
            ) as mock_load:
                generator = SummaryGenerator()
                generator.client = Mock()
                generator.summary_cache = {}
                return generator

    def test_initialization(self, mock_env_vars):
        """Test summary generator initialization"""
        with patch("src.summary_generator.Anthropic"):
            generator = SummaryGenerator()
            assert generator.anthropic_api_key == "test_anthropic_key"

    def test_validate_event_data(self, summary_generator, sample_film_event):
        """Test event data validation"""
        assert summary_generator._validate_event_data(sample_film_event) == True

        # Test invalid event
        invalid_event = {"title": ""}
        assert summary_generator._validate_event_data(invalid_event) == False

    def test_generate_summary_cached(self, summary_generator, sample_film_event):
        """Test summary generation with cache hit"""
        cache_key = "TEST MOVIE_screening"
        summary_generator.summary_cache[cache_key] = "Cached summary"

        result = summary_generator.generate_summary(sample_film_event)
        assert result == "Cached summary"

    def test_generate_summary_new(self, summary_generator, sample_film_event):
        """Test summary generation with API call"""
        # Mock API response
        mock_response = Mock()
        mock_response.content = [Mock()]
        mock_response.content[0].text = "Generated summary of the film"
        summary_generator.client.messages.create.return_value = mock_response

        result = summary_generator.generate_summary(
            sample_film_event, force_regenerate=True
        )
        assert isinstance(result, str)
        assert len(result) > 0

    def test_prompt_building(self, summary_generator, sample_film_event):
        """Test prompt building for different event types"""
        # Test film prompt
        film_prompt = summary_generator._build_movie_prompt(
            "Test Movie", "Description", sample_film_event
        )
        assert "Test Movie" in film_prompt
        assert "8-12 words" in film_prompt

        # Test concert prompt
        concert_event = {"venue": "Symphony", "composers": ["Beethoven"]}
        concert_prompt = summary_generator._build_concert_prompt(
            "Concert", "Description", concert_event
        )
        assert "classical music" in concert_prompt.lower()


class TestCalendarGenerator:
    """Test calendar generator functionality"""

    @pytest.fixture
    def calendar_generator(self):
        """Create calendar generator"""
        return CalendarGenerator()

    def test_initialization(self, calendar_generator):
        """Test calendar generator initialization"""
        assert calendar_generator.timezone.zone == "America/Chicago"

    def test_datetime_parsing(self, calendar_generator, sample_film_event):
        """Test datetime parsing"""
        result = calendar_generator._parse_datetime(sample_film_event)
        assert result is not None
        assert result.hour == 19  # 7:30 PM in 24-hour format
        assert result.minute == 30

    def test_event_creation(self, calendar_generator, sample_film_event):
        """Test calendar event creation"""
        # Add required rating field
        sample_film_event["final_rating"] = 8

        event = calendar_generator._create_event(sample_film_event)
        assert event is not None
        assert "Test Movie" in str(event["summary"])

    def test_uid_generation(self, calendar_generator, sample_film_event):
        """Test unique ID generation"""
        uid = calendar_generator._generate_uid(sample_film_event)
        assert isinstance(uid, str)
        assert "@culturecalendar.local" in uid

    def test_description_building(self, calendar_generator, sample_film_event):
        """Test event description building"""
        sample_film_event["rating_explanation"] = "AI Rating: 8/10"
        description = calendar_generator._build_description(sample_film_event)

        assert isinstance(description, str)
        assert "AI Rating" in description

    def test_generate_ics(self, calendar_generator, sample_film_event):
        """Test ICS file generation"""
        sample_film_event["final_rating"] = 8
        events = [sample_film_event]

        with tempfile.NamedTemporaryFile(suffix=".ics", delete=False) as temp_file:
            try:
                calendar_generator.generate_ics(events, temp_file.name)
                assert os.path.exists(temp_file.name)
                assert os.path.getsize(temp_file.name) > 0
            finally:
                os.unlink(temp_file.name)


class TestScraperGenerator:
    """Test scraper generator functionality"""

    @pytest.fixture
    def scraper_generator(self):
        """Create scraper generator"""
        return ScraperGenerator()

    def test_initialization(self, scraper_generator):
        """Test scraper generator initialization"""
        assert scraper_generator.template_dir == "src/scraper_templates"

    def test_venue_config_template(self, scraper_generator):
        """Test venue configuration template generation"""
        film_config = scraper_generator.generate_venue_config_template("film")
        assert film_config["venue_type"] == "film"
        assert "base_url" in film_config
        assert "target_urls" in film_config

        book_config = scraper_generator.generate_venue_config_template("book_club")
        assert book_config["venue_type"] == "book_club"

    def test_schema_fields_building(self, scraper_generator):
        """Test schema fields string building"""
        schema = FilmEventSchema.get_schema()
        result = scraper_generator._build_schema_fields(schema)

        assert isinstance(result, str)
        assert "title" in result
        assert "required" in result

    def test_extraction_hints_building(self, scraper_generator):
        """Test extraction hints building"""
        schema = FilmEventSchema.get_schema()
        result = scraper_generator._build_extraction_hints(schema)

        assert isinstance(result, str)
        assert "title" in result

    def test_scraper_generation(self, scraper_generator):
        """Test complete scraper generation"""
        config = {
            "venue_type": "film",
            "base_url": "https://test-venue.com",
            "target_urls": ["https://test-venue.com/events"],
            "venue_description": "Test venue for unit testing",
        }

        code = scraper_generator.generate_scraper("TestVenue", config)

        assert isinstance(code, str)
        assert "class TestVenueScraper" in code
        assert "https://test-venue.com" in code
        assert "get_target_urls" in code
        assert "get_data_schema" in code

    def test_convenience_function(self):
        """Test convenience function for scraper creation"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Override the default path
            with patch(
                "src.scraper_generator.ScraperGenerator.save_scraper"
            ) as mock_save:
                mock_save.return_value = os.path.join(temp_dir, "test_scraper.py")

                result = create_new_venue_scraper(
                    "TestVenue", "film", base_url="https://example.com"
                )

                assert isinstance(result, str)
                mock_save.assert_called_once()


@pytest.mark.unit
class TestErrorHandling:
    """Test error handling across components"""

    def test_llm_service_api_error(self, mock_env_vars):
        """Test LLM service handles API errors gracefully"""
        with patch("src.llm_service.Anthropic") as mock_anthropic:
            mock_anthropic.side_effect = Exception("API Error")

            # Should not raise exception during initialization
            service = LLMService()
            assert service.anthropic is None

    def test_summary_generator_api_error(self, mock_env_vars):
        """Test summary generator handles API errors"""
        with patch("src.summary_generator.Anthropic") as mock_anthropic:
            generator = SummaryGenerator()
            generator.client = Mock()
            generator.client.messages.create.side_effect = Exception("API Error")

            event = {"title": "Test Movie", "description": "Test description"}
            result = generator.generate_summary(event)

            # Should return None on error, not raise exception
            assert result is None

    def test_schema_validation_errors(self):
        """Test schema validation with invalid data"""
        invalid_event = {
            "title": "",  # Required field is empty
            "year": "invalid",  # Wrong type
        }

        result = SchemaRegistry.validate_event_data(invalid_event, "film")

        assert result["is_valid"] == False
        assert len(result["errors"]) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
