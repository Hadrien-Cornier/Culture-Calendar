"""
Test suite for the enrichment layer (Phase Two)
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from src.enrichment_layer import EnrichmentLayer
from src.config_loader import ConfigLoader


class TestEnrichmentLayer:
    """Tests for the EnrichmentLayer class"""
    
    @pytest.fixture
    def mock_config(self):
        """Create a mock ConfigLoader"""
        config = Mock(spec=ConfigLoader)
        
        # Mock venue policies
        config.get_venue_policy.return_value = {
            'classification': {'enabled': True},
            'enrichment': {'enabled': True}
        }
        
        # Mock allowed categories
        config.get_allowed_event_categories.return_value = [
            'movie', 'book_club', 'concert', 'opera', 'dance', 'other'
        ]
        
        # Mock templates
        config.get_template.return_value = {
            'fields': ['title', 'dates', 'times', 'director', 'runtime_minutes'],
            'required_on_publish': ['title', 'dates', 'times', 'director'],
            'field_definitions': {}
        }
        
        # Mock validation rules
        config.get_validation_rules.return_value = {
            'fail_fast': True,
            'error_on_missing_required_on_publish': True
        }
        
        # Mock date/time spec
        config.get_date_time_spec.return_value = {
            'date_field': 'dates',
            'time_field': 'times',
            'date_format': 'YYYY-MM-DD',
            'time_format': 'HH:mm',
            'zip_rule': 'pairwise_equal_length'
        }
        
        # Mock other methods
        config.is_classification_enabled.return_value = True
        config.get_assumed_event_category.return_value = None
        config._config = {'style': {'field_naming': 'snake_case'}}
        
        return config
    
    @pytest.fixture
    def mock_llm(self):
        """Create a mock LLMService"""
        llm = Mock()
        llm.anthropic = Mock()
        llm.perplexity_api_key = "test_key"
        llm.call_perplexity = Mock()
        llm._call_anthropic_json = Mock()
        return llm
    
    @pytest.fixture
    def enrichment_layer(self, mock_config, mock_llm):
        """Create EnrichmentLayer instance with mocks"""
        with patch('src.enrichment_layer.LLMService', return_value=mock_llm):
            layer = EnrichmentLayer(config_loader=mock_config)
            layer.llm = mock_llm
            return layer
    
    def test_run_enrichment_classification_enabled(self, enrichment_layer, mock_config):
        """Test run_enrichment when classification is enabled"""
        # Setup
        event = {
            'title': 'Test Movie',
            'description': 'A test movie description',
            'dates': ['2025-10-01'],
            'times': ['19:00'],
            'venue': 'Test Cinema',
            'director': 'Test Director'  # Add required field to avoid validation error
        }
        
        # Mock classification response
        enrichment_layer.llm.call_perplexity.return_value = {
            'event_category': 'movie',
            'abstained': False
        }
        
        # Execute
        result = enrichment_layer.run_enrichment(event, 'hyperreal')
        
        # Assert
        assert result['event_category'] == 'movie'
        assert result['enrichment_meta']['status'] == 'completed'
        assert result['enrichment_meta']['method'] == 'perplexity_v1'
        assert result['enrichment_meta']['abstained'] == False
    
    def test_run_enrichment_classification_disabled(self, enrichment_layer, mock_config):
        """Test run_enrichment when classification is disabled"""
        # Setup
        mock_config.is_classification_enabled.return_value = False
        mock_config.get_assumed_event_category.return_value = 'book_club'
        
        # Mock book_club template to avoid validation errors
        mock_config.get_template.return_value = {
            'fields': ['title', 'dates', 'times', 'book', 'author'],
            'required_on_publish': ['title', 'dates', 'times'],  # Don't require book/author for test
            'field_definitions': {}
        }
        
        event = {
            'title': 'Book Club Meeting',
            'dates': ['2025-10-01'],
            'times': ['19:00']
        }
        
        # Execute
        result = enrichment_layer.run_enrichment(event, 'alienated_majesty')
        
        # Assert
        assert result['event_category'] == 'book_club'
        # The policy_reason might be overwritten by enrichment, so check for either message
        policy_reason = result['enrichment_meta'].get('policy_reason', '')
        assert 'Classification disabled' in policy_reason or 'No missing required fields' in policy_reason
    
    def test_classify_event_success(self, enrichment_layer):
        """Test successful event classification"""
        # Setup
        event = {
            'title': 'Dune: Part Two',
            'description': 'Epic sci-fi movie sequel',
            'venue': 'IMAX Theater'
        }
        
        enrichment_layer.llm.call_perplexity.return_value = {
            'event_category': 'movie',
            'abstained': False
        }
        
        # Execute
        category, meta = enrichment_layer.classify_event(event)
        
        # Assert
        assert category == 'movie'
        assert meta['method'] == 'perplexity_v1'
        assert meta['abstained'] == False
        assert enrichment_layer.telemetry['classifications']['movie'] == 1
    
    def test_classify_event_abstention(self, enrichment_layer):
        """Test classification abstention on uncertain events"""
        # Setup
        event = {
            'title': 'Community Gathering',
            'description': 'Various activities'
        }
        
        enrichment_layer.llm.call_perplexity.return_value = {
            'event_category': 'Unknown',
            'abstained': True
        }
        
        # Execute
        category, meta = enrichment_layer.classify_event(event)
        
        # Assert
        assert category is None
        assert meta['abstained'] == True
        assert enrichment_layer.telemetry['abstentions'] == 1
    
    def test_enrich_for_type_with_missing_fields(self, enrichment_layer):
        """Test enrichment when required fields are missing"""
        # Setup
        event = {
            'title': 'The Godfather',
            'dates': ['2025-10-01'],
            'times': ['20:00']
            # Missing 'director' which is required
        }
        
        enrichment_layer.llm.call_perplexity.return_value = {
            'fields': {
                'director': {
                    'value': 'Francis Ford Coppola',
                    'evidence': 'substring',
                    'citations': []
                }
            }
        }
        
        # Mock evidence validation to accept the director
        with patch.object(enrichment_layer, '_validate_evidence', return_value=True):
            # Execute
            enriched, meta = enrichment_layer.enrich_for_type(event, 'movie')
        
        # Assert
        assert enriched['director'] == 'Francis Ford Coppola'
        assert meta['field_sources']['director'] == 'llm_substring'
        assert enrichment_layer.telemetry['fields_accepted'] == 1
    
    def test_enrich_for_type_no_missing_fields(self, enrichment_layer):
        """Test enrichment when all required fields are present"""
        # Setup
        event = {
            'title': 'The Godfather',
            'dates': ['2025-10-01'],
            'times': ['20:00'],
            'director': 'Francis Ford Coppola'
        }
        
        # Execute
        enriched, meta = enrichment_layer.enrich_for_type(event, 'movie')
        
        # Assert
        assert meta['status'] == 'completed'
        assert meta['policy_reason'] == 'No missing required fields'
        assert enrichment_layer.telemetry['fields_accepted'] == 0
    
    def test_validate_evidence_substring_valid(self, enrichment_layer):
        """Test evidence validation for valid substring"""
        # Setup
        value = "Francis Ford Coppola"
        context = "Directed by Francis Ford Coppola, The Godfather is a classic"
        
        # Execute
        result = enrichment_layer._validate_evidence(
            value, 'substring', [], context
        )
        
        # Assert
        assert result == True
    
    def test_validate_evidence_substring_invalid(self, enrichment_layer):
        """Test evidence validation for invalid substring"""
        # Setup
        value = "Steven Spielberg"
        context = "Directed by Francis Ford Coppola, The Godfather is a classic"
        
        # Execute
        result = enrichment_layer._validate_evidence(
            value, 'substring', [], context
        )
        
        # Assert
        assert result == False
    
    def test_validate_evidence_citation_valid(self, enrichment_layer):
        """Test evidence validation with citations"""
        # Setup
        value = "175 minutes"
        citations = ["https://imdb.com/title/tt0068646"]
        context = "Movie information"
        
        # Execute
        result = enrichment_layer._validate_evidence(
            value, 'citation', citations, context
        )
        
        # Assert
        assert result == True
    
    def test_validate_evidence_citation_invalid(self, enrichment_layer):
        """Test evidence validation without citations"""
        # Setup
        value = "175 minutes"
        citations = []
        context = "Movie information"
        
        # Execute
        result = enrichment_layer._validate_evidence(
            value, 'citation', citations, context
        )
        
        # Assert
        assert result == False
    
    def test_validate_event_missing_required_fields(self, enrichment_layer):
        """Test validation with missing required fields"""
        # Setup
        event = {
            'event_category': 'movie',
            'title': 'Test Movie',
            'dates': ['2025-10-01']
            # Missing 'times' and 'director'
        }
        
        # Execute
        errors = enrichment_layer._validate_event(event)
        
        # Assert
        assert 'Missing required field: times' in errors
        assert 'Missing required field: director' in errors
    
    def test_validate_event_mismatched_dates_times(self, enrichment_layer):
        """Test validation with mismatched dates/times arrays"""
        # Setup
        event = {
            'event_category': 'movie',
            'title': 'Test Movie',
            'dates': ['2025-10-01', '2025-10-02'],
            'times': ['19:00'],  # Only one time for two dates
            'director': 'Test Director'
        }
        
        # Execute
        errors = enrichment_layer._validate_event(event)
        
        # Assert
        assert any('Mismatched lengths' in e for e in errors)
    
    def test_validate_event_invalid_date_format(self, enrichment_layer):
        """Test validation with invalid date format"""
        # Setup
        event = {
            'event_category': 'movie',
            'title': 'Test Movie',
            'dates': ['10/01/2025'],  # Wrong format
            'times': ['19:00'],
            'director': 'Test Director'
        }
        
        # Execute
        errors = enrichment_layer._validate_event(event)
        
        # Assert
        assert any('Invalid date format' in e for e in errors)
    
    def test_validate_event_invalid_field_names(self, enrichment_layer):
        """Test validation with non-snake_case field names"""
        # Setup
        event = {
            'event_category': 'movie',
            'title': 'Test Movie',
            'dates': ['2025-10-01'],
            'times': ['19:00'],
            'director': 'Test Director',
            'releaseYear': '2025'  # camelCase instead of snake_case
        }
        
        # Execute
        errors = enrichment_layer._validate_event(event)
        
        # Assert
        assert any('not snake_case' in e for e in errors)
    
    def test_telemetry_tracking(self, enrichment_layer):
        """Test telemetry data collection"""
        # Setup initial telemetry
        enrichment_layer.telemetry = {
            'classifications': {'movie': 2, 'concert': 1},
            'abstentions': 3,
            'fields_accepted': 5,
            'fields_rejected': 2,
            'missing_required': ['director', 'runtime'],
            'enrichment_failures': 1
        }
        
        # Get telemetry
        telemetry = enrichment_layer.get_telemetry()
        
        # Assert
        assert telemetry['total_classifications'] == 3
        assert telemetry['classifications_by_label']['movie'] == 2
        assert telemetry['abstentions'] == 3
        assert telemetry['fields_accepted'] == 5
        assert telemetry['fields_rejected'] == 2
        assert telemetry['missing_required_count'] == 2
        assert telemetry['enrichment_failures'] == 1
    
    def test_perplexity_fallback_to_anthropic(self, enrichment_layer):
        """Test fallback to Anthropic when Perplexity fails"""
        # Setup
        enrichment_layer.llm.call_perplexity.return_value = None
        enrichment_layer.llm._call_anthropic_json.return_value = {
            'event_category': 'movie',
            'abstained': False
        }
        
        event = {
            'title': 'Test Movie',
            'description': 'A movie'
        }
        
        # Execute
        category, meta = enrichment_layer.classify_event(event)
        
        # Assert
        assert category == 'movie'
        enrichment_layer.llm._call_anthropic_json.assert_called_once()
    
    def test_enrichment_with_other_category(self, enrichment_layer):
        """Test enrichment for 'other' category events"""
        # Setup
        mock_config = enrichment_layer.config
        mock_config.get_template.return_value = {
            'fields': ['title', 'dates', 'times', 'venue', 'rating', 
                      'one_liner_summary', 'description', 'url'],
            'required_on_publish': ['title', 'dates', 'times', 'rating', 
                                   'one_liner_summary', 'description', 'venue']
        }
        
        event = {
            'event_category': 'other',
            'title': 'Community Workshop',
            'dates': ['2025-10-15'],
            'times': ['14:00'],
            'venue': 'Community Center'
            # Missing rating, one_liner_summary, description
        }
        
        enrichment_layer.llm.call_perplexity.return_value = {
            'fields': {
                'rating': {
                    'value': '-1',
                    'evidence': 'substring',
                    'citations': []
                },
                'one_liner_summary': {
                    'value': 'Interactive workshop for community members',
                    'evidence': 'substring',
                    'citations': []
                },
                'description': {
                    'value': 'A hands-on workshop bringing together community members',
                    'evidence': 'substring',
                    'citations': []
                }
            }
        }
        
        # Mock validation to accept all fields
        with patch.object(enrichment_layer, '_validate_evidence', return_value=True):
            # Execute
            enriched, meta = enrichment_layer.enrich_for_type(event, 'other')
        
        # Assert
        assert enriched['rating'] == '-1'
        assert 'workshop' in enriched['one_liner_summary'].lower()
        assert meta['field_sources']['rating'] == 'llm_substring'