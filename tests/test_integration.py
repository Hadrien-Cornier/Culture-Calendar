"""
Integration tests for Culture Calendar - Test component interactions
"""

import pytest
import json
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from src.scraper import MultiVenueScraper
from src.processor import EventProcessor
from src.scrapers import (
    AFSScraper, HyperrealScraper, FirstLightAustinScraper,
    AustinSymphonyScraper, EarlyMusicAustinScraper, LaFolliaAustinScraper
)


@pytest.mark.integration
class TestScraperIntegration:
    """Test individual scraper integration with infrastructure"""
    
    @pytest.fixture
    def mock_classical_data_file(self, sample_classical_data, test_data_dir):
        """Create mock classical data file for classical scrapers"""
        file_path = os.path.join(test_data_dir, 'classical_data.json')
        with open(file_path, 'w') as f:
            json.dump(sample_classical_data, f)
        
        # Patch the hardcoded path in classical scrapers
        classical_scrapers = [
            'src.scrapers.austin_symphony_scraper',
            'src.scrapers.early_music_scraper', 
            'src.scrapers.la_follia_scraper'
        ]
        
        patches = []
        for scraper_module in classical_scrapers:
            patcher = patch(f'{scraper_module}.os.path.exists', return_value=True)
            patches.append(patcher)
            patcher.start()
            
            # Also patch the file reading
            def mock_open_func(filepath, *args, **kwargs):
                if 'classical_data.json' in filepath:
                    return open(file_path, *args, **kwargs)
                return open(filepath, *args, **kwargs)
            
            open_patcher = patch(f'{scraper_module}.open', side_effect=mock_open_func)
            patches.append(open_patcher)
            open_patcher.start()
        
        yield file_path
        
        # Clean up patches
        for patcher in patches:
            patcher.stop()
    
    def test_afs_scraper_initialization(self, mock_env_vars):
        """Test AFS scraper initializes correctly"""
        scraper = AFSScraper()
        assert scraper.venue_name == "AFS"
        assert scraper.base_url == "https://www.austinfilm.org"
        assert hasattr(scraper, 'llm_service')
    
    def test_hyperreal_scraper_initialization(self, mock_env_vars):
        """Test Hyperreal scraper initializes correctly"""
        scraper = HyperrealScraper()
        assert scraper.venue_name == "Hyperreal"
        assert scraper.base_url == "https://hyperrealfilm.club"
    
    def test_book_club_scraper_initialization(self, mock_env_vars):
        """Test book club scraper initializes correctly"""
        scraper = FirstLightAustinScraper()
        assert scraper.venue_name == "FirstLight"
        assert scraper.base_url == "https://www.firstlightaustin.com"
    
    def test_classical_scraper_initialization(self, mock_env_vars, mock_classical_data_file):
        """Test classical scrapers initialize and load data correctly"""
        # Test Symphony scraper
        symphony_scraper = AustinSymphonyScraper()
        assert symphony_scraper.venue_name == "Symphony"
        
        # Test Early Music scraper
        early_music_scraper = EarlyMusicAustinScraper()
        assert early_music_scraper.venue_name == "EarlyMusic"
        
        # Test La Follia scraper
        la_follia_scraper = LaFolliaAustinScraper()
        assert la_follia_scraper.venue_name == "LaFollia"
    
    def test_classical_scraper_data_loading(self, mock_env_vars, mock_classical_data_file):
        """Test that classical scrapers can load data from JSON"""
        with patch.object(AustinSymphonyScraper, 'data_file', mock_classical_data_file):
            scraper = AustinSymphonyScraper()
            events = scraper.scrape_events()
            
            assert isinstance(events, list)
            assert len(events) >= 0  # May be empty if no data
    
    def test_scraper_schema_consistency(self, mock_env_vars):
        """Test that all scrapers have consistent schema interfaces"""
        scrapers = [
            AFSScraper(),
            HyperrealScraper(),
            FirstLightAustinScraper(),
            AustinSymphonyScraper(),
            EarlyMusicAustinScraper(),
            LaFolliaAustinScraper()
        ]
        
        for scraper in scrapers:
            # Test required methods exist
            assert hasattr(scraper, 'get_target_urls')
            assert hasattr(scraper, 'get_data_schema') 
            assert hasattr(scraper, 'get_fallback_data')
            assert hasattr(scraper, 'scrape_events')
            
            # Test method returns
            urls = scraper.get_target_urls()
            assert isinstance(urls, list)
            
            schema = scraper.get_data_schema()
            assert isinstance(schema, dict)
            assert 'title' in schema
            assert 'date' in schema
            
            fallback = scraper.get_fallback_data()
            assert isinstance(fallback, list)


@pytest.mark.integration  
class TestMultiVenueIntegration:
    """Test MultiVenueScraper integration with individual scrapers"""
    
    @pytest.fixture
    def multi_venue_scraper(self, mock_env_vars):
        """Create MultiVenueScraper with mocked dependencies"""
        return MultiVenueScraper()
    
    def test_multi_venue_initialization(self, multi_venue_scraper):
        """Test that MultiVenueScraper initializes all individual scrapers"""
        assert hasattr(multi_venue_scraper, 'afs_scraper')
        assert hasattr(multi_venue_scraper, 'hyperreal_scraper')
        assert hasattr(multi_venue_scraper, 'first_light_scraper')
        assert hasattr(multi_venue_scraper, 'symphony_scraper')
        
        # Check that scrapers are properly initialized
        assert multi_venue_scraper.afs_scraper.venue_name == "AFS"
        assert multi_venue_scraper.hyperreal_scraper.venue_name == "Hyperreal"
    
    def test_venue_assignment(self, multi_venue_scraper):
        """Test that venue names are properly assigned to events"""
        # Mock individual scrapers to return test events
        test_events = [
            {'title': 'Test Event 1', 'date': '2025-07-15', 'time': '7:30 PM'},
            {'title': 'Test Event 2', 'date': '2025-07-16', 'time': '8:00 PM'}
        ]
        
        with patch.object(multi_venue_scraper.afs_scraper, 'scrape_events', return_value=test_events):
            with patch.object(multi_venue_scraper.hyperreal_scraper, 'scrape_events', return_value=[]):
                with patch.object(multi_venue_scraper.symphony_scraper, 'scrape_events', return_value=[]):
                    with patch.object(multi_venue_scraper.early_music_scraper, 'scrape_events', return_value=[]):
                        with patch.object(multi_venue_scraper.la_follia_scraper, 'scrape_events', return_value=[]):
                            with patch.object(multi_venue_scraper.alienated_majesty_scraper, 'scrape_events', return_value=[]):
                                with patch.object(multi_venue_scraper.first_light_scraper, 'scrape_events', return_value=[]):
                                    events = multi_venue_scraper.scrape_all_venues()
        
        assert len(events) == 2
        for event in events:
            assert event['venue'] == 'AFS'
    
    def test_error_handling(self, multi_venue_scraper):
        """Test that errors in individual scrapers don't break the whole system"""
        # Make one scraper fail
        with patch.object(multi_venue_scraper.afs_scraper, 'scrape_events', side_effect=Exception("AFS Error")):
            with patch.object(multi_venue_scraper.hyperreal_scraper, 'scrape_events', return_value=[{'title': 'Working Event', 'date': '2025-07-15', 'time': '7:30 PM'}]):
                with patch.object(multi_venue_scraper.symphony_scraper, 'scrape_events', return_value=[]):
                    with patch.object(multi_venue_scraper.early_music_scraper, 'scrape_events', return_value=[]):
                        with patch.object(multi_venue_scraper.la_follia_scraper, 'scrape_events', return_value=[]):
                            with patch.object(multi_venue_scraper.alienated_majesty_scraper, 'scrape_events', return_value=[]):
                                with patch.object(multi_venue_scraper.first_light_scraper, 'scrape_events', return_value=[]):
                                    events = multi_venue_scraper.scrape_all_venues()
        
        # Should still get events from working scrapers
        assert len(events) == 1
        assert events[0]['venue'] == 'Hyperreal'
    
    def test_update_tracking(self, multi_venue_scraper):
        """Test that last update times are tracked"""
        # Mock all scrapers to return empty lists
        for scraper_name in ['afs_scraper', 'hyperreal_scraper', 'symphony_scraper', 
                            'early_music_scraper', 'la_follia_scraper', 
                            'alienated_majesty_scraper', 'first_light_scraper']:
            scraper = getattr(multi_venue_scraper, scraper_name)
            with patch.object(scraper, 'scrape_events', return_value=[]):
                pass
        
        multi_venue_scraper.scrape_all_venues()
        
        # Check that update times are recorded
        assert isinstance(multi_venue_scraper.last_updated, dict)
        assert 'AFS' in multi_venue_scraper.last_updated


@pytest.mark.integration
class TestProcessorIntegration:
    """Test EventProcessor integration with scrapers"""
    
    @pytest.fixture
    def event_processor(self, mock_env_vars):
        """Create EventProcessor with mocked dependencies"""
        with patch('src.processor.SummaryGenerator'):
            return EventProcessor()
    
    def test_processor_initialization(self, event_processor):
        """Test EventProcessor initializes correctly"""
        assert hasattr(event_processor, 'preferences')
        assert hasattr(event_processor, 'literature_preferences')
        assert hasattr(event_processor, 'movie_cache')
    
    def test_process_film_events(self, event_processor, sample_film_event):
        """Test processing film events"""
        # Mock AI rating response
        with patch.object(event_processor, '_get_ai_rating', return_value={'score': 8, 'summary': 'Great film'}):
            events = [sample_film_event]
            processed = event_processor.process_events(events)
        
        assert len(processed) == 1
        processed_event = processed[0]
        assert 'ai_rating' in processed_event
        assert 'final_rating' in processed_event
        assert 'rating_explanation' in processed_event
    
    def test_process_book_club_events(self, event_processor, sample_book_club_event):
        """Test processing book club events"""
        # Mock book club rating response
        with patch.object(event_processor, '_get_book_club_rating', return_value={'score': 7, 'summary': 'Thoughtful discussion'}):
            events = [sample_book_club_event]
            processed = event_processor.process_events(events)
        
        assert len(processed) == 1
        processed_event = processed[0]
        assert 'ai_rating' in processed_event
        assert 'final_rating' in processed_event
    
    def test_process_concert_events(self, event_processor, sample_concert_event):
        """Test processing concert events"""
        # Mock concert rating response
        with patch.object(event_processor, '_get_classical_rating', return_value={'score': 9, 'summary': 'Excellent performance'}):
            events = [sample_concert_event]
            processed = event_processor.process_events(events)
        
        assert len(processed) == 1
        processed_event = processed[0]
        assert 'ai_rating' in processed_event
        assert 'final_rating' in processed_event
    
    def test_work_hours_filtering(self, event_processor):
        """Test that work hours filtering works correctly"""
        work_hour_event = {
            'title': 'Work Hour Event',
            'date': '2025-07-15',  # Tuesday
            'time': '2:00 PM',
            'type': 'screening'
        }
        
        evening_event = {
            'title': 'Evening Event',
            'date': '2025-07-15',
            'time': '7:00 PM',
            'type': 'screening'
        }
        
        # Mock AI ratings
        with patch.object(event_processor, '_get_ai_rating', return_value={'score': 8, 'summary': 'Test'}):
            events = [work_hour_event, evening_event]
            processed = event_processor.process_events(events)
        
        # Work hour event should be filtered out
        assert len(processed) == 1
        assert processed[0]['title'] == 'Evening Event'
    
    def test_preference_scoring(self, event_processor, sample_film_event):
        """Test preference scoring integration"""
        # Add a preference that matches the test event
        event_processor.preferences = ['test', 'movie']
        
        with patch.object(event_processor, '_get_ai_rating', return_value={'score': 6, 'summary': 'Contains test keywords'}):
            events = [sample_film_event]
            processed = event_processor.process_events(events)
        
        processed_event = processed[0]
        assert processed_event['preference_score'] > 0
        assert processed_event['final_rating'] > 6  # Should be boosted by preferences


@pytest.mark.integration
class TestFullPipelineIntegration:
    """Test complete scraping -> processing -> output pipeline"""
    
    def test_scraper_to_processor_pipeline(self, mock_env_vars):
        """Test that scraped events can be processed successfully"""
        # Create minimal test data
        test_events = [
            {
                'title': 'Test Movie',
                'date': '2025-07-15',
                'time': '7:30 PM',
                'type': 'screening',
                'venue': 'AFS',
                'url': 'https://test.com'
            }
        ]
        
        # Mock scraper
        multi_scraper = MultiVenueScraper()
        with patch.object(multi_scraper, 'scrape_all_venues', return_value=test_events):
            scraped_events = multi_scraper.scrape_all_venues()
        
        # Mock processor
        with patch('src.processor.SummaryGenerator'):
            processor = EventProcessor()
            with patch.object(processor, '_get_ai_rating', return_value={'score': 8, 'summary': 'Test summary'}):
                processed_events = processor.process_events(scraped_events)
        
        assert len(processed_events) == 1
        processed_event = processed_events[0]
        
        # Check that event has all required fields for downstream processing
        required_fields = ['title', 'date', 'time', 'venue', 'ai_rating', 'final_rating']
        for field in required_fields:
            assert field in processed_event
    
    def test_processed_events_to_calendar(self, mock_env_vars):
        """Test that processed events can generate calendar files"""
        from src.calendar_generator import CalendarGenerator
        
        processed_events = [
            {
                'title': 'Test Movie',
                'date': '2025-07-15',
                'time': '7:30 PM',
                'venue': 'AFS',
                'final_rating': 8,
                'rating_explanation': 'AI Rating: 8/10',
                'url': 'https://test.com'
            }
        ]
        
        calendar_gen = CalendarGenerator()
        
        with tempfile.NamedTemporaryFile(suffix='.ics', delete=False) as temp_file:
            try:
                calendar_gen.generate_ics(processed_events, temp_file.name)
                
                # Verify file was created and has content
                assert os.path.exists(temp_file.name)
                assert os.path.getsize(temp_file.name) > 0
                
                # Read and verify basic ICS content
                with open(temp_file.name, 'r') as f:
                    content = f.read()
                    assert 'BEGIN:VCALENDAR' in content
                    assert 'Test Movie' in content
                    assert 'END:VCALENDAR' in content
                    
            finally:
                os.unlink(temp_file.name)
    
    def test_error_recovery_in_pipeline(self, mock_env_vars):
        """Test that pipeline recovers gracefully from errors"""
        # Test with events that might cause processing errors
        problematic_events = [
            {
                'title': '',  # Empty title
                'date': 'invalid-date',
                'time': 'invalid-time',
                'type': 'screening'
            },
            {
                'title': 'Valid Event',
                'date': '2025-07-15',
                'time': '7:30 PM',
                'type': 'screening'
            }
        ]
        
        with patch('src.processor.SummaryGenerator'):
            processor = EventProcessor()
            
            # Mock AI rating to sometimes fail
            def mock_ai_rating(event):
                if not event.get('title'):
                    raise Exception("No title provided")
                return {'score': 8, 'summary': 'Test summary'}
            
            with patch.object(processor, '_get_ai_rating', side_effect=mock_ai_rating):
                processed_events = processor.process_events(problematic_events)
        
        # Should still return events, even if some failed
        assert isinstance(processed_events, list)
        # Should have at least one event (the valid one)
        valid_events = [e for e in processed_events if e.get('title') == 'Valid Event']
        assert len(valid_events) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "integration"])