"""
Phase Two: Config-driven Classification and Enrichment Layer

This module implements deterministic classification and enrichment of events
after normalization (Phase One), following strict config-driven policies.
"""

import json
import re
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime

from .config_loader import ConfigLoader
from .llm_service import LLMService


class EnrichmentLayer:
    """Orchestrates classification and enrichment based on config policies"""
    
    def __init__(self, config_loader: Optional[ConfigLoader] = None):
        """
        Initialize enrichment layer with config and LLM service
        
        Args:
            config_loader: Optional config loader instance
        """
        self.config = config_loader or ConfigLoader()
        self.llm = LLMService()
        
        # Telemetry counters
        self.telemetry = {
            'classifications': {},
            'abstentions': 0,
            'fields_accepted': 0,
            'fields_rejected': 0,
            'missing_required': [],
            'enrichment_failures': 0
        }
    
    def run_enrichment(self, event: Dict[str, Any], venue_key: str) -> Dict[str, Any]:
        """
        Main orchestration method: applies venue policy for classification and enrichment
        
        Args:
            event: Normalized event from Phase One
            venue_key: Venue identifier (e.g., 'hyperreal', 'paramount')
            
        Returns:
            Augmented event with classification and enrichment results
        """
        # Initialize enrichment metadata
        event['enrichment_meta'] = {
            'status': 'started',
            'step': 'init',
            'method': 'none',
            'abstained': False,
            'policy_reason': None,
            'field_sources': {},
            'citations': {}
        }
        
        try:
            # Get venue policy
            venue_policy = self.config.get_venue_policy(venue_key)
            
            # Step 1: Classification (if enabled)
            if self.config.is_classification_enabled(venue_key):
                event_category, classification_meta = self.classify_event(event)
                event['event_category'] = event_category
                event['enrichment_meta'].update(classification_meta)
            else:
                # Use assumed category if classification disabled
                assumed_category = self.config.get_assumed_event_category(venue_key)
                if assumed_category:
                    event['event_category'] = assumed_category
                    event['enrichment_meta']['policy_reason'] = f"Classification disabled, using assumed category: {assumed_category}"
                    event['enrichment_meta']['step'] = 'classification'
                else:
                    event['event_category'] = None
            
            # Step 2: Enrichment (if enabled and category determined)
            enrichment_enabled = venue_policy.get('enrichment', {}).get('enabled', True)
            if enrichment_enabled and event.get('event_category'):
                enriched_event, enrichment_meta = self.enrich_for_type(
                    event, event['event_category']
                )
                event.update(enriched_event)
                event['enrichment_meta'].update(enrichment_meta)
            elif not enrichment_enabled:
                event['enrichment_meta']['policy_reason'] = "Enrichment disabled by venue policy"
                event['enrichment_meta']['status'] = 'skipped'
            
            # Step 3: Validation
            validation_errors = self._validate_event(event)
            if validation_errors:
                event['enrichment_meta']['status'] = 'failed'
                event['enrichment_meta']['validation_errors'] = validation_errors
                
                # Track missing required fields
                self.telemetry['missing_required'].extend(validation_errors)
                
                if self.config.get_validation_rules().get('fail_fast', True):
                    raise ValueError(f"Validation failed: {', '.join(validation_errors)}")
            else:
                event['enrichment_meta']['status'] = 'completed'
            
            return event
            
        except Exception as e:
            event['enrichment_meta']['status'] = 'failed'
            event['enrichment_meta']['error'] = str(e)
            self.telemetry['enrichment_failures'] += 1
            raise
    
    def classify_event(self, event: Dict[str, Any]) -> Tuple[Optional[str], Dict[str, Any]]:
        """
        Classify event into allowed categories using deterministic LLM call
        
        Args:
            event: Event data with title, description, url, venue
            
        Returns:
            Tuple of (event_category, metadata)
        """
        meta = {
            'step': 'classification',
            'method': 'perplexity_v1',
            'abstained': False
        }
        
        try:
            # Get allowed labels from config
            allowed_labels = self.config.get_allowed_event_categories()
            
            # Build context from event
            context = self._build_event_context(event)
            
            # Create deterministic classification prompt
            prompt = self._create_classification_prompt(context, allowed_labels)
            
            # Call LLM with low temperature for determinism
            response = self._call_llm_json(prompt, temperature=0.2)
            
            # Parse response
            if response and isinstance(response, dict):
                event_category = response.get('event_category')
                abstained = response.get('abstained', False)
                
                meta['abstained'] = abstained
                
                # Validate category (normalize to lowercase)
                event_category_lower = event_category.lower() if event_category else None
                
                if event_category_lower in allowed_labels:
                    # Track telemetry
                    self.telemetry['classifications'][event_category_lower] = \
                        self.telemetry['classifications'].get(event_category_lower, 0) + 1
                    return event_category_lower, meta
                elif event_category_lower in ['unknown']:
                    self.telemetry['abstentions'] += 1
                    meta['abstained'] = True
                    return None, meta
                else:
                    # Default to 'other' for unrecognized categories
                    if 'other' in allowed_labels:
                        self.telemetry['classifications']['other'] = \
                            self.telemetry['classifications'].get('other', 0) + 1
                        return 'other', meta
            
            # Fallback
            self.telemetry['abstentions'] += 1
            meta['abstained'] = True
            return None, meta
            
        except Exception as e:
            meta['error'] = str(e)
            meta['abstained'] = True
            self.telemetry['abstentions'] += 1
            return None, meta
    
    def enrich_for_type(
        self, event: Dict[str, Any], event_category: str
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Enrich event by extracting missing required fields for its type
        
        Args:
            event: Event data
            event_category: Classified event type
            
        Returns:
            Tuple of (updated_event, metadata)
        """
        meta = {
            'step': 'enrichment',
            'method': 'perplexity_v1',
            'field_sources': {},
            'citations': {}
        }
        
        try:
            # Get template for event type
            template = self.config.get_template(event_category)
            required_fields = template.get('required_on_publish', [])
            
            # Identify missing required fields
            missing_fields = [
                field for field in required_fields 
                if not event.get(field) or event.get(field) == ''
            ]
            
            if not missing_fields:
                meta['status'] = 'completed'
                meta['policy_reason'] = 'No missing required fields'
                return event, meta
            
            # Build enrichment prompt
            context = self._build_event_context(event)
            prompt = self._create_enrichment_prompt(
                context, event_category, missing_fields
            )
            
            # Call LLM for enrichment
            response = self._call_llm_json(prompt, temperature=0.2)
            
            if response and isinstance(response, dict):
                fields_data = response.get('fields', {})
                
                # Process each field response
                for field_name, field_info in fields_data.items():
                    if field_name not in missing_fields:
                        continue
                    
                    value = field_info.get('value')
                    evidence = field_info.get('evidence')
                    citations = field_info.get('citations', [])
                    
                    # Apply evidence rules
                    accepted = self._validate_evidence(
                        value, evidence, citations, context
                    )
                    
                    if accepted:
                        # Update event with enriched field
                        event[field_name] = value
                        meta['field_sources'][field_name] = f"llm_{evidence}"
                        if citations:
                            meta['citations'][field_name] = citations
                        self.telemetry['fields_accepted'] += 1
                    else:
                        self.telemetry['fields_rejected'] += 1
            
            meta['status'] = 'completed'
            return event, meta
            
        except Exception as e:
            meta['error'] = str(e)
            meta['status'] = 'failed'
            self.telemetry['enrichment_failures'] += 1
            return event, meta
    
    def _build_event_context(self, event: Dict[str, Any]) -> str:
        """Build text context from event for LLM processing"""
        parts = []
        
        if event.get('title'):
            parts.append(f"Title: {event['title']}")
        if event.get('description'):
            parts.append(f"Description: {event['description']}")
        if event.get('venue'):
            parts.append(f"Venue: {event['venue']}")
        if event.get('url'):
            parts.append(f"URL: {event['url']}")
        if event.get('dates'):
            parts.append(f"Dates: {', '.join(event['dates'])}")
        if event.get('times'):
            parts.append(f"Times: {', '.join(event['times'])}")
        
        # Include any additional metadata
        for key in ['series', 'program', 'tags']:
            if event.get(key):
                parts.append(f"{key.title()}: {event[key]}")
        
        return "\n".join(parts)
    
    def _create_classification_prompt(
        self, context: str, allowed_labels: List[str]
    ) -> str:
        """Create classification prompt for deterministic LLM call"""
        
        # Format labels for display
        labels_str = ', '.join([label.title() for label in allowed_labels])
        
        return f"""You classify events and extract only verifiable fields from provided text or web citations. If uncertain, abstain. Output JSON only.

Classify this cultural event into one of these categories: {labels_str}

Event context:
{context}

INSTRUCTIONS:
1. Analyze the event information carefully
2. Choose the most specific matching category
3. If uncertain or ambiguous, return "Unknown" and set abstained to true
4. Return JSON with no additional text

Output exactly this JSON format:
{{
  "event_category": "{allowed_labels[0].title()}" | "{allowed_labels[1].title()}" | ... | "Unknown",
  "abstained": true | false
}}"""
    
    def _create_enrichment_prompt(
        self, context: str, event_category: str, missing_fields: List[str]
    ) -> str:
        """Create enrichment prompt for extracting missing fields"""
        
        # Build field descriptions
        field_specs = []
        for field in missing_fields:
            field_specs.append(f"- {field}")
        
        fields_str = "\n".join(field_specs)
        
        return f"""You classify events and extract only verifiable fields from provided text or web citations. If uncertain, abstain. Output JSON only.

Extract the following missing fields for this {event_category} event:
{fields_str}

Event context:
{context}

CRITICAL RULES:
1. Only extract values that are EXPLICITLY stated in the provided context
2. For "substring" evidence: The value must be an exact contiguous substring from the context
3. For "citation" evidence: Only use if you can cite a specific web source
4. If a field cannot be found with proper evidence, do not include it
5. Never fabricate or guess values

Output JSON format:
{{
  "fields": {{
    "field_name": {{
      "value": "extracted value",
      "evidence": "substring" | "citation",
      "citations": ["url1", "url2"] // only if evidence is "citation"
    }}
  }}
}}"""
    
    def _validate_evidence(
        self, value: Any, evidence: str, citations: List[str], context: str
    ) -> bool:
        """
        Validate extracted field based on evidence rules
        
        Args:
            value: Extracted value
            evidence: Evidence type ('substring' or 'citation')
            citations: List of citation URLs
            context: Original event context
            
        Returns:
            True if evidence is valid, False otherwise
        """
        if not value:
            return False
        
        if evidence == 'substring':
            # Check if value is exact substring in context
            value_str = str(value).strip()
            # Normalize whitespace for comparison
            normalized_context = ' '.join(context.split())
            normalized_value = ' '.join(value_str.split())
            
            # Accept if exact substring exists
            return normalized_value in normalized_context
        
        elif evidence == 'citation':
            # Accept if citations provided
            return bool(citations) and len(citations) > 0
        
        # Reject unknown evidence types
        return False
    
    def _validate_event(self, event: Dict[str, Any]) -> List[str]:
        """
        Validate event against required fields and date/time invariants
        
        Args:
            event: Event to validate
            
        Returns:
            List of validation error messages
        """
        errors = []
        
        # Skip validation if no event_category
        if not event.get('event_category'):
            return errors
        
        # Get validation rules
        validation_rules = self.config.get_validation_rules()
        
        # Check required fields for the event type
        template = self.config.get_template(event['event_category'])
        required_fields = template.get('required_on_publish', [])
        
        for field in required_fields:
            if not event.get(field):
                errors.append(f"Missing required field: {field}")
        
        # Validate date/time spec invariants
        date_spec = self.config.get_date_time_spec()
        
        # Check dates and times arrays exist
        dates = event.get(date_spec['date_field'], [])
        times = event.get(date_spec['time_field'], [])
        
        if not dates:
            errors.append(f"Missing or empty {date_spec['date_field']} array")
        if not times:
            errors.append(f"Missing or empty {date_spec['time_field']} array")
        
        # Check zip_rule
        if dates and times and date_spec.get('zip_rule') == 'pairwise_equal_length':
            if len(dates) != len(times):
                errors.append(
                    f"Mismatched lengths: {len(dates)} dates != {len(times)} times"
                )
        
        # Validate date format
        if dates:
            date_format = date_spec['date_format']  # YYYY-MM-DD
            for date in dates:
                if not self._validate_date_format(date, date_format):
                    errors.append(f"Invalid date format: {date} (expected {date_format})")
        
        # Validate field naming (snake_case)
        style = self.config._config.get('style', {})
        if style.get('field_naming') == 'snake_case':
            for field_name in event.keys():
                if not re.match(r'^[a-z_][a-z0-9_]*$', field_name):
                    errors.append(f"Invalid field name (not snake_case): {field_name}")
        
        return errors
    
    def _validate_date_format(self, date_str: str, format_spec: str) -> bool:
        """Check if date string matches expected format"""
        if format_spec == 'YYYY-MM-DD':
            try:
                datetime.strptime(date_str, '%Y-%m-%d')
                return True
            except ValueError:
                return False
        return False
    
    def _call_llm_json(self, prompt: str, temperature: float = 0.2) -> Optional[Dict]:
        """
        Call LLM and parse JSON response
        
        Args:
            prompt: Prompt to send
            temperature: Temperature setting (default 0.2 for determinism)
            
        Returns:
            Parsed JSON response or None
        """
        # Try Perplexity first if available, otherwise fall back to Anthropic
        if hasattr(self.llm, 'call_perplexity'):
            result = self.llm.call_perplexity(prompt, temperature=temperature)
            if result:
                return result
        
        # Fall back to direct Anthropic call
        if self.llm.anthropic:
            return self.llm._call_anthropic_json(prompt, temperature)
        
        return None
    
    def get_telemetry(self) -> Dict[str, Any]:
        """Get telemetry data for monitoring"""
        return {
            'classifications_by_label': self.telemetry['classifications'],
            'total_classifications': sum(self.telemetry['classifications'].values()),
            'abstentions': self.telemetry['abstentions'],
            'fields_accepted': self.telemetry['fields_accepted'],
            'fields_rejected': self.telemetry['fields_rejected'],
            'missing_required_count': len(self.telemetry['missing_required']),
            'enrichment_failures': self.telemetry['enrichment_failures']
        }