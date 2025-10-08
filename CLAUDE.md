# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Culture Calendar is an automated system that scrapes Austin cultural events (films, concerts, book clubs, opera, ballet) from multiple venues, enriches them with AI-powered analysis and ratings, and publishes them to a GitHub Pages website with calendar/ICS export functionality.

**Current Venues**: Austin Film Society, Hyperreal Film Club, Austin Symphony, Early Music Austin, La Follia, Austin Opera, Ballet Austin, Alienated Majesty Books, First Light Austin, Arts on Alexander

## Development Commands

### Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Setup environment
cp .env.example .env
# Add PERPLEXITY_API_KEY and ANTHROPIC_API_KEY to .env
```

### Running the System
```bash
# Full scrape and update (all venues, all events)
python update_website_data.py

# Test mode (current week only)
python update_website_data.py --test-week

# Force reprocess all events (ignore cache)
python update_website_data.py --force-reprocess

# Enable smart validation (fail-fast on scraper failures)
python update_website_data.py --validate
```

### Testing
```bash
# Run all tests
pytest tests/

# Run unit tests only (no live scraping)
pytest tests/ -m "not live and not integration"

# Run specific scraper tests
pytest tests/test_afs_scraper_unit.py -v
pytest tests/test_enrichment_layer.py -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html
```

### Code Quality
```bash
# Format code with Black
black src/ tests/ *.py

# Pre-commit checks (formatting + tests)
python pre_commit_checks.py

# Auto-fix only
python pre_commit_checks.py --fix-only
```

## Architecture

### Two-Phase Scraping Pipeline

**Phase One: Normalization**
- Each venue scraper extends `BaseScraper` (src/base_scraper.py:20)
- Scraper-specific logic extracts raw event data from websites
- Events normalized to config-driven schema (snake_case, YYYY-MM-DD dates, HH:mm times)
- LLM extraction used for complex/dynamic websites (book clubs, some film venues)

**Phase Two: Enrichment** (Optional per venue)
- Classification: LLM determines event_category (movie/concert/book_club/opera/dance/other)
- Field Extraction: LLM fills missing required fields with evidence validation
- Only proceeds if classification enabled in config/master_config.yaml
- See src/enrichment_layer.py:40 for orchestration logic

### Key Components

**Configuration System** (config/master_config.yaml)
- Centralized schema definitions via templates (movie, concert, book_club, opera, dance, other)
- Per-venue policies: scraping frequency, classification enabled/disabled, assumed categories
- Field requirements, validation rules, date/time formats
- Loaded via ConfigLoader (src/config_loader.py)

**Scraper Architecture**
- `BaseScraper` (src/base_scraper.py): Abstract base with LLM service, session management, format_event(), validate_event()
- Individual scrapers in src/scrapers/: Each implements scrape_events() method
- `MultiVenueScraper` (src/scraper.py:28): Orchestrates all venue scrapers, manages duplicate detection
- LLM-powered extraction for dynamic content (Hyperreal, Alienated Majesty, First Light)
- Static JSON loading for season-based venues (Symphony, Opera, Ballet)

**Event Processing Pipeline**
1. Scraping: MultiVenueScraper.scrape_all_venues() ’ normalized events
2. Validation (optional): EventValidationService checks scraper health, fail-fast on widespread failures
3. Enrichment: EventProcessor.process_events() ’ AI ratings, descriptions, one-liners
4. Website Generation: update_website_data.py ’ docs/data.json with grouped events

**AI Integration**
- `LLMService` (src/llm_service.py): Abstracts Perplexity (Sonar) and Anthropic (Claude) APIs
- `EventProcessor` (src/processor.py:19): Generates AI ratings/reviews using Perplexity
- `EnrichmentLayer` (src/enrichment_layer.py:17): Classification and field extraction with evidence validation
- `SummaryGenerator` (src/summary_generator.py): Creates one-line summaries using Claude

### Event Schema

All events follow master_config.yaml templates with these common fields:
- **dates/times**: Arrays with pairwise_equal_length zip rule (YYYY-MM-DD, HH:mm)
- **occurrences**: Generated array of {date, time, url, venue} objects for each showing
- **event_category**: movie | concert | book_club | opera | dance | other
- **rating**: 0-10 AI-generated score based on artistic merit
- **description**: AI-generated analysis (French cinéaste style for films, distinguished criticism for music)
- **one_liner_summary**: Claude-generated concise hook

Type-specific fields defined in config templates (e.g., movies have director/country/language, concerts have composers/works).

## Common Development Tasks

### Adding a New Venue

1. Create scraper class in src/scrapers/new_venue_scraper.py extending BaseScraper
2. Implement scrape_events() method returning normalized events
3. Add venue config to config/master_config.yaml under venues:
4. Register in src/scrapers/__init__.py
5. Add to MultiVenueScraper.__init__() and scrape_all_venues() in src/scraper.py
6. Create unit tests in tests/test_new_venue_scraper_unit.py
7. Test with: `python update_website_data.py --test-week`

### Debugging Scraper Failures

1. Check validation report if using --validate flag
2. Run individual scraper in test mode
3. Verify website structure hasn't changed (common failure cause)
4. Check LLM extraction prompts if using smart extraction
5. Review enrichment telemetry: classifications, abstentions, fields_accepted/rejected

### Modifying Event Schema

1. Update template in config/master_config.yaml (add fields, change requirements)
2. Update scraper to populate new fields
3. Update enrichment prompts if field requires LLM extraction
4. Modify update_website_data.py:build_event_from_template() if special handling needed
5. Update tests with new schema

## Known Issues

1. **Pyppeteer threading**: Cannot run all scrapers in parallel due to "signal only works in main thread" error with pyppeteer
2. **Read review button**: Can crash site (mentioned in README problems section)
3. **Rating distribution**: Ratings not very customized/spread out (needs preference tuning)

## Data Flow

1. **Scraping**: MultiVenueScraper ’ raw events (Phase One normalization)
2. **Validation**: EventValidationService ’ health checks, fail-fast on systematic failures
3. **Enrichment**: EventProcessor ’ AI ratings + descriptions
4. **Summary Generation**: SummaryGenerator ’ one-line hooks
5. **Website Data**: update_website_data.py ’ docs/data.json (grouped by title for movies, unique for others)
6. **ICS Export**: Calendar files generated on-demand via website download button
7. **GitHub Pages**: docs/ folder served at hadrien-cornier.github.io/Culture-Calendar

## Testing Strategy

- **Unit tests**: Mock scrapers, test parsing logic without network calls
- **Integration tests**: Test full pipeline with cached responses
- **Live tests**: Marked with @pytest.mark.live, test actual website scraping
- Test data stored in tests/{Venue}_test_data/ directories
- Validation service has comprehensive integration tests (tests/test_validation_integration.py)

## Configuration Notes

- All scrapers use master_config.yaml as single source of truth
- Date inference handled dynamically at runtime for book clubs (current year vs next year logic)
- Venue policies control classification/enrichment (AFS has classification disabled, assumed movie category)
- Field defaults defined at config level to ensure consistency
- snake_case enforced across all field names per config style rules
