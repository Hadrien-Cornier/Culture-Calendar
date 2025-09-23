# Phase Two Implementation - Config-driven Classification and Enrichment

## Overview
Phase Two adds a self-contained enrichment layer that runs after Phase One's normalization. It performs:
1. **Classification** - Categorizes events into ontology labels (movie, book_club, concert, etc.)
2. **Enrichment** - Extracts missing required fields using LLM with strict evidence rules

## Architecture

```
Phase One (Scrapers)     Phase Two (Enrichment)      Output
        |                         |                     |
    Raw Events --------> Normalized Events -----> Enriched Events
        |                         |                     |
   BaseScraper            EnrichmentLayer         Validated Data
                                 |
                          ConfigLoader (policies)
                                 |
                           LLMService (AI)
```

## Key Components

### 1. EnrichmentLayer (`src/enrichment_layer.py`)
Main orchestration module that:
- Applies venue-specific policies from config
- Runs classification if enabled
- Performs type-aware enrichment
- Validates results against required fields
- Tracks telemetry

### 2. LLM Service Updates (`src/llm_service.py`)
Enhanced with:
- Perplexity API integration for deterministic classification
- Fallback to Anthropic Claude if Perplexity unavailable
- JSON-only response parsing
- Caching for repeated queries

### 3. Base Scraper Integration (`src/base_scraper.py`)
New capabilities:
- `scrape_and_enrich()` method for Phase One + Two pipeline
- Automatic enrichment if ConfigLoader provided
- Telemetry reporting after enrichment

## Configuration

Venue policies in `config/master_config.yaml`:

```yaml
venues:
  hyperreal:
    classification:
      enabled: true        # Run classifier
    enrichment:
      enabled: true        # Extract missing fields
  
  afs:
    classification:
      enabled: false       # Skip classification
      assumed_event_category: movie  # Use this type
    enrichment:
      enabled: false       # No enrichment needed
```

## Evidence Rules (Fail Fast)

The enrichment layer only accepts extracted fields with proper evidence:

1. **Substring Evidence**: Value must be exact substring from input text
2. **Citation Evidence**: Valid web citations must be provided (if online search allowed)

Fields without proper evidence are rejected to maintain data integrity.

## Usage

### Direct Enrichment
```python
from src.enrichment_layer import EnrichmentLayer
from src.config_loader import ConfigLoader

config = ConfigLoader()
enrichment = EnrichmentLayer(config)

# Event from Phase One
event = {
    "title": "Dune: Part Two",
    "dates": ["2025-10-15"],
    "times": ["19:00"],
    "venue": "Cinema",
    "description": "Sci-fi epic"
}

# Apply Phase Two
enriched = enrichment.run_enrichment(event, "hyperreal")
```

### Scraper Integration
```python
from src.scrapers.hyperreal_scraper import HyperrealScraper
from src.config_loader import ConfigLoader

config = ConfigLoader()
scraper = HyperrealScraper(config=config)

# Runs Phase One + Two automatically
events = scraper.scrape_and_enrich()
```

## Enrichment Metadata

Each enriched event includes metadata:

```json
{
  "event_category": "movie",
  "enrichment_meta": {
    "status": "completed",
    "step": "enrichment", 
    "method": "perplexity_v1",
    "abstained": false,
    "field_sources": {
      "director": "llm_substring",
      "runtime_minutes": "llm_citation"
    },
    "citations": {
      "runtime_minutes": ["https://imdb.com/..."]
    }
  }
}
```

## Telemetry

Track enrichment performance:

```python
telemetry = enrichment.get_telemetry()
# {
#   "total_classifications": 25,
#   "classifications_by_label": {"movie": 20, "other": 5},
#   "abstentions": 3,
#   "fields_accepted": 45,
#   "fields_rejected": 12
# }
```

## Validation

Strict validation ensures data quality:
- All `required_on_publish` fields must be present
- Date/time arrays must have equal length (pairwise)
- Dates must be YYYY-MM-DD format
- Field names must be snake_case
- Fail fast on validation errors (configurable)

## API Keys

Set environment variables:
```bash
export PERPLEXITY_API_KEY="pplx-..."  # Preferred for classification
export ANTHROPIC_API_KEY="sk-..."     # Fallback option
```

## Testing

Comprehensive test suite:
```bash
python -m pytest tests/test_enrichment_layer.py -v
```

Tests cover:
- Classification with/without API
- Enrichment with evidence validation
- Venue policy application
- Validation rules
- Telemetry tracking
- API fallback logic

## Examples

See `examples/enrichment_example.py` for:
- Direct enrichment usage
- Scraper integration
- Validation scenarios
- Telemetry aggregation
- Error handling

## Rollout Strategy

1. **Phase 1**: Enable classification only for `hyperreal` and `paramount`
2. **Phase 2**: Enable enrichment for Movie and BookClub types
3. **Phase 3**: Extend to Concert, Opera, Dance types
4. **Monitor**: Track telemetry, tune prompts, improve evidence rules

## Key Design Decisions

1. **Deterministic LLM**: Low temperature (0.2), strict JSON schema
2. **Evidence-based**: No fabrication, only verifiable extraction
3. **Fail Fast**: Strict validation with actionable errors
4. **Type-aware**: Different requirements per event category
5. **Config-driven**: All policies in master_config.yaml
6. **Minimal**: Only enrich missing required fields

## Future Improvements

- [ ] Batch processing for multiple events
- [ ] Parallel LLM calls for performance
- [ ] More sophisticated evidence validation
- [ ] Custom prompts per venue/type
- [ ] A/B testing different models
- [ ] Confidence scoring for classifications