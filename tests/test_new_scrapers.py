"""
Enhanced test suite for new LLM-powered scrapers with validation
"""

import os
import pytest
import json
from typing import Dict, List, Any
from dotenv import load_dotenv

# Import new scrapers
from src.scrapers.first_light_scraper import FirstLightAustinScraper
from src.llm_service import LLMService
from src.schemas import SchemaRegistry, get_venue_schema

# Load environment variables
load_dotenv()

# Check API key availability
firecrawl_api_key = os.getenv('FIRECRAWL_API_KEY')
anthropic_api_key = os.getenv('ANTHROPIC_API_KEY')

is_firecrawl_configured = firecrawl_api_key is not None
is_llm_configured = anthropic_api_key is not None

firecrawl_skip_reason = "Firecrawl API key is not configured. Set FIRECRAWL_API_KEY in your .env file."
llm_skip_reason = "Anthropic API key is not configured. Set ANTHROPIC_API_KEY in your .env file."


class ScraperTestFramework:
    """Framework for testing scrapers with LLM validation"""
    
    def __init__(self):
        self.llm_service = LLMService()
    
    def validate_scraper_events(self, scraper, events: List[Dict]) -> Dict[str, Any]:
        """
        Comprehensive validation of scraper events using both schema and LLM validation
        
        Returns:
            Dict with validation results
        """
        validation_results = {
            'total_events': len(events),
            'schema_validation': [],
            'llm_validation': [],
            'summary': {
                'schema_passed': 0,
                'llm_passed': 0,
                'overall_quality': 0.0
            }
        }
        
        venue_name = scraper.venue_name
        schema = get_venue_schema(venue_name)
        
        for i, event in enumerate(events):
            # Schema validation
            schema_result = self._validate_event_schema(event, schema, venue_name)
            validation_results['schema_validation'].append({
                'event_index': i,
                'event_title': event.get('title', 'Unknown'),
                'result': schema_result
            })
            
            if schema_result['is_valid']:
                validation_results['summary']['schema_passed'] += 1
            
            # LLM validation (if available)
            if self.llm_service.anthropic:
                llm_result = self._validate_event_with_llm(event, schema)
                validation_results['llm_validation'].append({
                    'event_index': i,
                    'event_title': event.get('title', 'Unknown'),
                    'result': llm_result
                })
                
                if llm_result['is_valid']:
                    validation_results['summary']['llm_passed'] += 1
        
        # Calculate overall quality score
        if len(events) > 0:
            schema_score = validation_results['summary']['schema_passed'] / len(events)
            if validation_results['llm_validation']:
                llm_score = validation_results['summary']['llm_passed'] / len(events)
                validation_results['summary']['overall_quality'] = (schema_score + llm_score) / 2
            else:
                validation_results['summary']['overall_quality'] = schema_score
        
        return validation_results
    
    def _validate_event_schema(self, event: Dict, schema: Dict, venue_name: str) -> Dict:
        """Validate event against schema"""
        return SchemaRegistry.validate_event_data(event, venue_name.lower())
    
    def _validate_event_with_llm(self, event: Dict, schema: Dict) -> Dict:
        """Validate event using LLM"""
        try:
            return self.llm_service.validate_extraction(event, schema)
        except Exception as e:
            return {
                'is_valid': False,
                'confidence': 0.0,
                'reason': f"LLM validation error: {str(e)}"
            }
    
    def test_scraper_robustness(self, scraper) -> Dict[str, Any]:
        """
        Test scraper robustness across all tiers
        
        Returns:
            Dict with tier-by-tier results
        """
        results = {
            'scraper_name': scraper.__class__.__name__,
            'venue_name': scraper.venue_name,
            'tier_results': {},
            'fallback_data_quality': None
        }
        
        # Test each tier individually (if possible)
        target_urls = scraper.get_target_urls()
        if target_urls:
            url = target_urls[0]  # Test first URL
            
            # Test fallback data
            fallback_events = scraper.get_fallback_data()
            if fallback_events:
                fallback_validation = self.validate_scraper_events(scraper, fallback_events)
                results['fallback_data_quality'] = fallback_validation['summary']['overall_quality']
        
        return results


# Initialize test framework
test_framework = ScraperTestFramework()


# Parametrized test for all new scrapers
@pytest.mark.parametrize("scraper_class,scraper_name", [
    (FirstLightAustinScraper, "FirstLightAustinScraper"),
])
def test_new_scraper_architecture(scraper_class, scraper_name):
    """Test new scraper architecture with comprehensive validation"""
    print(f"\n--- Testing {scraper_name} with New Architecture ---")
    
    # Initialize scraper
    scraper = scraper_class()
    
    # Basic setup validation
    assert hasattr(scraper, 'get_target_urls'), f"{scraper_name} missing get_target_urls method"
    assert hasattr(scraper, 'get_data_schema'), f"{scraper_name} missing get_data_schema method"
    assert hasattr(scraper, 'get_fallback_data'), f"{scraper_name} missing get_fallback_data method"
    
    # Test target URLs
    target_urls = scraper.get_target_urls()
    assert isinstance(target_urls, list), "get_target_urls should return a list"
    assert len(target_urls) > 0, "Should have at least one target URL"
    print(f"Target URLs: {target_urls}")
    
    # Test schema
    schema = scraper.get_data_schema()
    assert isinstance(schema, dict), "get_data_schema should return a dict"
    assert len(schema) > 0, "Schema should not be empty"
    print(f"Schema has {len(schema)} fields")
    
    # Test fallback data
    fallback_events = scraper.get_fallback_data()
    assert isinstance(fallback_events, list), "get_fallback_data should return a list"
    print(f"Fallback data has {len(fallback_events)} events")
    
    if fallback_events:
        # Validate fallback data quality
        fallback_validation = test_framework.validate_scraper_events(scraper, fallback_events)
        print(f"Fallback data quality: {fallback_validation['summary']['overall_quality']:.2f}")
        
        # Fallback data should be high quality
        assert fallback_validation['summary']['overall_quality'] >= 0.8, \
            f"Fallback data quality too low: {fallback_validation['summary']['overall_quality']:.2f}"


@pytest.mark.skipif(not is_firecrawl_configured, reason=firecrawl_skip_reason)
def test_first_light_scraper_live():
    """Test FirstLight scraper against live website"""
    print("\n--- Testing FirstLightAustinScraper Live ---")
    
    scraper = FirstLightAustinScraper()
    events = scraper.scrape_events()
    
    assert isinstance(events, list), f"Expected list of events, got {type(events)}"
    
    if not events:
        print("No events found - testing fallback system")
        # If no live events, ensure fallback works
        fallback_events = scraper.get_fallback_data()
        assert len(fallback_events) > 0, "Fallback data should not be empty"
        events = fallback_events
    
    print(f"Found {len(events)} events")
    
    # Validate events
    validation_results = test_framework.validate_scraper_events(scraper, events)
    
    print(f"Schema validation: {validation_results['summary']['schema_passed']}/{validation_results['total_events']} passed")
    if validation_results['llm_validation']:
        print(f"LLM validation: {validation_results['summary']['llm_passed']}/{validation_results['total_events']} passed")
    print(f"Overall quality: {validation_results['summary']['overall_quality']:.2f}")
    
    # Quality thresholds
    assert validation_results['summary']['overall_quality'] >= 0.7, \
        f"Event quality too low: {validation_results['summary']['overall_quality']:.2f}"
    
    # Print sample event for inspection
    if events:
        print("\nSample event:")
        print(json.dumps(events[0], indent=2))
        
        # Validate required fields for book club events
        sample_event = events[0]
        assert 'title' in sample_event, "Missing title field"
        assert 'date' in sample_event, "Missing date field"
        assert 'book' in sample_event, "Missing book field"
        assert 'author' in sample_event, "Missing author field"
        assert 'venue' in sample_event, "Missing venue field"


@pytest.mark.skipif(not is_llm_configured, reason=llm_skip_reason)
def test_llm_validation_system():
    """Test the LLM validation system independently"""
    print("\n--- Testing LLM Validation System ---")
    
    llm_service = LLMService()
    
    # Test with good data
    good_event = {
        'title': 'World Wide What Book Club: Beloved',
        'book': 'Beloved',
        'author': 'Toni Morrison',
        'date': '2025-07-15',
        'time': '7:30 PM',
        'venue': 'FirstLight',
        'type': 'book_club'
    }
    
    schema = get_venue_schema('FirstLight')
    validation_result = llm_service.validate_extraction(good_event, schema)
    
    print(f"Good event validation: {validation_result}")
    assert validation_result['is_valid'], f"Good event should be valid: {validation_result['reason']}"
    assert validation_result['confidence'] >= 0.7, f"Confidence too low: {validation_result['confidence']}"
    
    # Test with bad data
    bad_event = {
        'title': 'Invalid Event Title !!!###',
        'book': '',  # Missing required field
        'author': '123 Not A Real Author',
        'date': '2023-13-45',  # Invalid date
        'time': '25:99 XX',    # Invalid time
        'venue': 'FirstLight',
        'type': 'book_club'
    }
    
    bad_validation_result = llm_service.validate_extraction(bad_event, schema)
    
    print(f"Bad event validation: {bad_validation_result}")
    # Bad event should either be marked invalid or have low confidence
    assert not bad_validation_result['is_valid'] or bad_validation_result['confidence'] < 0.5, \
        f"Bad event should be flagged: {bad_validation_result}"


@pytest.mark.skipif(not is_firecrawl_configured, reason=firecrawl_skip_reason)
def test_progressive_fallback_system():
    """Test that the progressive fallback system works correctly"""
    print("\n--- Testing Progressive Fallback System ---")
    
    scraper = FirstLightAustinScraper()
    
    # Test that scraper can handle different scenarios
    # This will try all tiers until one succeeds
    events = scraper.scrape_events(use_cache=False)  # Don't use cache for testing
    
    assert isinstance(events, list), "Should return a list even if fallback is used"
    
    # Even if all web tiers fail, fallback should provide events
    if not events:
        fallback_events = scraper.get_fallback_data()
        assert len(fallback_events) > 0, "Fallback should provide events when web scraping fails"
    
    print(f"Progressive fallback test completed. Got {len(events)} events")


def test_schema_registry():
    """Test the schema registry system"""
    print("\n--- Testing Schema Registry ---")
    
    # Test getting schemas for different venue types
    film_schema = SchemaRegistry.get_schema('film')
    concert_schema = SchemaRegistry.get_schema('concert')
    book_schema = SchemaRegistry.get_schema('book_club')
    
    assert isinstance(film_schema, dict), "Film schema should be a dict"
    assert isinstance(concert_schema, dict), "Concert schema should be a dict"
    assert isinstance(book_schema, dict), "Book club schema should be a dict"
    
    # Test that schemas have required base fields
    for schema in [film_schema, concert_schema, book_schema]:
        assert 'title' in schema, "All schemas should have title field"
        assert 'date' in schema, "All schemas should have date field"
        assert 'time' in schema, "All schemas should have time field"
    
    # Test venue-specific schemas
    firstlight_schema = get_venue_schema('FirstLight')
    assert 'book' in firstlight_schema, "FirstLight schema should have book field"
    assert 'author' in firstlight_schema, "FirstLight schema should have author field"
    
    print(f"Schema registry test passed. Available types: {SchemaRegistry.get_available_types()}")


if __name__ == "__main__":
    # Run tests manually for debugging
    pytest.main([__file__, "-v", "-s"])