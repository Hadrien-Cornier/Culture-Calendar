"""
Pytest configuration and fixtures for Culture Calendar tests
"""

import os
import pytest
import tempfile
import json
from unittest.mock import Mock, patch
from typing import Dict, List

# Ensure we can import from src
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


@pytest.fixture(scope="session")
def test_data_dir():
    """Create a temporary directory for test data"""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


@pytest.fixture
def sample_film_event():
    """Sample film event data for testing"""
    return {
        'title': 'Test Movie',
        'director': 'Test Director',
        'year': 2023,
        'country': 'USA',
        'language': 'English',
        'duration': '120 min',
        'date': '2025-07-15',
        'time': '7:30 PM',
        'venue': 'AFS',
        'type': 'film',
        'url': 'https://austinfilm.org/test-movie',
        'is_special_screening': False
    }


@pytest.fixture
def sample_book_club_event():
    """Sample book club event data for testing"""
    return {
        'title': 'Test Book Club: Great Novel',
        'book': 'Great Novel',
        'author': 'Famous Author',
        'host': 'Book Host',
        'date': '2025-07-20',
        'time': '7:00 PM',
        'venue': 'FirstLight',
        'type': 'book_club',
        'url': 'https://firstlightaustin.com/book-club',
        'series': 'Literary Fiction Book Club'
    }


@pytest.fixture
def sample_concert_event():
    """Sample concert event data for testing"""
    return {
        'title': 'Symphony Concert',
        'composers': ['Beethoven', 'Mozart'],
        'works': ['Symphony No. 5', 'Piano Concerto No. 21'],
        'featured_artist': 'Test Orchestra',
        'conductor': 'Test Conductor',
        'date': '2025-07-25',
        'time': '8:00 PM',
        'venue': 'Symphony',
        'type': 'concert',
        'url': 'https://austinsymphony.org/test-concert',
        'series': 'Classical Series'
    }


@pytest.fixture
def sample_ai_response():
    """Sample AI response for testing"""
    return {
        'score': 8,
        'summary': 'A compelling drama that explores themes of identity and belonging with nuanced character development.'
    }


@pytest.fixture
def mock_anthropic_client():
    """Mock Anthropic client for testing"""
    mock_client = Mock()
    mock_response = Mock()
    mock_response.content = [Mock()]
    mock_response.content[0].text = "Compelling one-line summary of the event"
    mock_client.messages.create.return_value = mock_response
    return mock_client


@pytest.fixture
def mock_firecrawl_client():
    """Mock Firecrawl client for testing"""
    mock_client = Mock()
    mock_client.scrape_url.return_value = {
        'markdown': 'Test markdown content',
        'html': '<html>Test HTML content</html>',
        'content': 'Test content'
    }
    return mock_client


@pytest.fixture
def sample_classical_data():
    """Sample classical music data for testing"""
    return {
        'austinSymphony': [
            {
                'title': 'Test Symphony Concert',
                'dates': ['2025-07-15', '2025-07-16'],
                'times': ['8:00 PM', '8:00 PM'],
                'series': 'Classical Series',
                'program': 'Beethoven Symphony No. 5',
                'featured_artist': 'Austin Symphony Orchestra',
                'composers': ['Beethoven'],
                'works': ['Symphony No. 5'],
                'venue_name': 'Long Center'
            }
        ],
        'earlyMusic': [
            {
                'title': 'Early Music Concert',
                'dates': ['2025-07-20'],
                'times': ['7:30 PM'],
                'series': 'Early Music Series',
                'program': 'Bach Cantatas',
                'featured_artist': 'Early Music Ensemble',
                'composers': ['Bach'],
                'works': ['Cantata BWV 140'],
                'venue_name': 'St. Davids Church'
            }
        ],
        'laFollia': [
            {
                'title': 'Chamber Music Concert',
                'dates': ['2025-07-25'],
                'times': ['8:00 PM'],
                'series': 'Chamber Series',
                'program': 'Mozart String Quartet',
                'featured_artist': 'La Follia Ensemble',
                'composers': ['Mozart'],
                'works': ['String Quartet K. 387'],
                'venue_name': 'Private Venue'
            }
        ]
    }


@pytest.fixture
def temp_classical_data_file(sample_classical_data, test_data_dir):
    """Create a temporary classical data file"""
    file_path = os.path.join(test_data_dir, 'classical_data.json')
    with open(file_path, 'w') as f:
        json.dump(sample_classical_data, f)
    return file_path


@pytest.fixture
def mock_env_vars():
    """Mock environment variables for testing"""
    env_vars = {
        'ANTHROPIC_API_KEY': 'test_anthropic_key',
        'FIRECRAWL_API_KEY': 'test_firecrawl_key',
        'PERPLEXITY_API_KEY': 'test_perplexity_key'
    }
    
    with patch.dict(os.environ, env_vars):
        yield env_vars


@pytest.fixture
def temp_cache_dir(test_data_dir):
    """Create a temporary cache directory"""
    cache_dir = os.path.join(test_data_dir, 'cache')
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir


@pytest.fixture
def sample_cache_data():
    """Sample cache data for testing"""
    return {
        'TEST MOVIE_FILM': 'Compelling one-line summary of test movie',
        'GREAT NOVEL_BOOK_CLUB': 'Thoughtful exploration of literary themes'
    }


@pytest.fixture
def temp_cache_file(sample_cache_data, temp_cache_dir):
    """Create a temporary cache file"""
    cache_file = os.path.join(temp_cache_dir, 'summary_cache.json')
    with open(cache_file, 'w') as f:
        json.dump(sample_cache_data, f)
    return cache_file


# Test markers
def pytest_configure(config):
    """Configure pytest markers"""
    config.addinivalue_line(
        "markers", "api: mark test as requiring API access"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )
    config.addinivalue_line(
        "markers", "unit: mark test as unit test"
    )
    config.addinivalue_line(
        "markers", "live: mark test as live integration test with real API keys"
    )


# Skip API tests if no API keys available
def pytest_collection_modifyitems(config, items):
    """Modify test collection to skip API tests without keys"""
    skip_api = pytest.mark.skip(reason="API keys not available")
    
    for item in items:
        if "api" in item.keywords:
            # Check if API keys are available
            if not all([
                os.getenv('ANTHROPIC_API_KEY'),
                os.getenv('FIRECRAWL_API_KEY'),
                os.getenv('PERPLEXITY_API_KEY')
            ]):
                item.add_marker(skip_api)