# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Culture Calendar is a production-ready Python application that automatically scrapes Austin cultural events from 7 venues, enriches them with AI-powered analysis, and provides both ICS calendar files and a live GitHub Pages website. The system uses a modern LLM-powered architecture with comprehensive testing and schema-driven development.

## Common Commands

```bash
# Activate virtual environment (required for all operations)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Edit .env to add required API keys:
# ANTHROPIC_API_KEY=your_key_here
# PERPLEXITY_API_KEY=your_key_here  
# FIRECRAWL_API_KEY=your_key_here

# Update website data (incremental - new events only)
python update_website_data.py --days 14

# Update website data (full refresh)
python update_website_data.py --full

# Force re-rate all events (ignore cache)
python update_website_data.py --full --force-reprocess

# Update with smart validation (recommended for production)
python update_website_data.py --full --validate

# Run comprehensive test suite
python run_tests.py              # All tests with coverage
python run_tests.py unit         # Unit tests only
python run_tests.py integration  # Integration tests
python run_tests.py fast         # Fast tests (no API calls)
python run_tests.py quality      # Data quality validation
python run_tests.py live         # Live integration tests (requires API keys)

# Test validation system
python test_validation.py        # Test scraper validation system
python test_validation.py --quick # Quick validation test (no live scraping)

# Pre-commit code quality checks (run before committing!)
python pre_commit_checks.py      # Auto-fix + quality checks + tests
python pre_commit_checks.py --fix-only    # Only run auto-fixes (black, isort, etc.)
python pre_commit_checks.py --check-only  # Only run quality checks
python pre_commit_checks.py --no-tests    # Skip tests, only code quality

# Test individual venue scrapers
python test_all_scrapers.py

# Generate new scraper from schema
python -c "from src.scraper_generator import create_new_venue_scraper; create_new_venue_scraper('VenueName', 'film', base_url='https://venue.com')"
```

## Development Workflow

### Adding New Venues
1. **Define Schema**: Add venue-specific schema to `src/schemas.py` with extraction hints
2. **Generate Scraper**: Use `ScraperGenerator.create_new_venue_scraper()` for 30-line boilerplate
3. **Customize Logic**: Implement venue-specific `get_target_urls()` and `get_fallback_data()`
4. **Add Tests**: Create tests in `tests/` following existing patterns
5. **Update Registry**: Add venue to `VENUE_SCHEMAS` mapping

### Key Architectural Patterns
- **Progressive Fallback**: Always have 4 tiers (requests → pyppeteer → firecrawl → static)
- **Real Data Only**: Use `None` for missing fields, never fake defaults
- **Schema-First**: Define extraction patterns before implementation
- **LLM Integration**: All data extraction goes through Claude API with structured prompts
- **Comprehensive Testing**: Unit/Integration/E2E/Quality tests for all components

### Virtual Environment
Always use the venv python environment: `source venv/bin/activate`

## Automated Scheduling
GitHub Actions handle all scheduling - no local cron jobs or scheduler.py needed.

## Smart Validation System

The Culture Calendar now includes a comprehensive validation system that ensures data quality and prevents deployment of malformed events.

### Validation Features
- **Schema Validation**: Ensures all events have required fields (title, date, venue, type)
- **LLM Content Validation**: AI-powered validation of event content quality
- **Per-Scraper Health Checks**: Validates at least 1 event from each scraper
- **Fail-Fast Mechanisms**: Stops pipeline immediately if >50% of scrapers fail
- **Detailed Logging**: Structured logs for debugging extraction failures

### Usage
```bash
# Enable validation during data refresh
python update_website_data.py --full --validate

# Test validation system manually
python test_validation.py

# Quick validation test (no live scraping)
python test_validation.py --quick
```

### GitHub Actions Integration
- **PR Validation**: Comprehensive testing on every pull request
- **Data Refresh Validation**: Smart validation during weekly/monthly updates
- **Automatic Failure Detection**: Workflows fail fast with detailed error reports

### Validation Thresholds
- **Minimum Scraper Success Rate**: 50% of scrapers must produce valid events
- **Events per Scraper**: At least 1 valid event required per scraper
- **Sample Size**: 3 events validated per scraper (adjustable)

The validation system helps catch issues early including:
- Website structure changes breaking scrapers
- Network connectivity problems
- LLM extraction failures  
- Schema validation errors
- Malformed or spam data

## Pre-Commit Code Quality Workflow

**Always run code quality checks before committing** to ensure your changes pass GitHub Actions:

### 🚀 Quick Pre-Commit (Recommended)
```bash
# Run this before every commit
python pre_commit_checks.py
```
This will:
- **Auto-fix imports** (remove unused, sort with isort)
- **Auto-fix formatting** (autopep8 + black)
- **Run quality checks** (security audit)
- **Run quick tests** (unit tests only)

### 🔧 Auto-Fix Only Mode
```bash
# Just apply automatic fixes without running checks
python pre_commit_checks.py --fix-only
```
Perfect for:
- Cleaning up messy code quickly
- Applying consistent formatting
- Removing unused imports

### 🔍 Check-Only Mode  
```bash
# Only run quality checks, no auto-fixes
python pre_commit_checks.py --check-only
```
Use when:
- You want to see what needs fixing
- Code is already formatted
- Just validating before commit

### 📦 Installation
```bash
# Install all code quality tools
python pre_commit_checks.py --install
```

### Tools Included
- **black**: Code formatting (PEP8 compliant)
- **isort**: Import sorting and organization
- **autoflake**: Remove unused imports/variables
- **autopep8**: Basic PEP8 fixes
- **bandit**: Security vulnerability scanning
- **safety**: Dependency vulnerability checking

### Typical Workflow
```bash
# 1. Make your code changes
# 2. Run pre-commit checks
python pre_commit_checks.py

# 3. Review any auto-fixes applied
git diff

# 4. Commit your changes
git add .
git commit -m "Your commit message"
```

**Note**: The pre-commit script runs the exact same checks as GitHub Actions, so if it passes locally, your PR will pass validation.

## Architecture

The system follows a modern LLM-powered architecture with three core layers:

### 1. **Progressive Scraping Layer** (`src/base_scraper.py` + `src/scrapers/`)
**Universal BaseScraper** with 4-tier progressive fallback system:
- **Tier 1**: requests + LLM extraction (fastest, most reliable)
- **Tier 2**: pyppeteer + LLM (handles JavaScript)
- **Tier 3**: firecrawl + LLM (enterprise scraping service)
- **Tier 4**: Static fallback data (ensures 100% uptime)

**Schema-Driven Individual Scrapers** (~30-40 lines each):
- **Film**: AFS, Hyperreal (real-time web scraping)
- **Music**: Symphony, Early Music, La Follia, Paramount (mix of static/dynamic)
- **Books**: Alienated Majesty, First Light (intelligent parsing)

**MultiVenueScraper** (`src/scraper.py`): Orchestrates all individual scrapers with error handling

### 2. **AI Processing Layer** (`src/processor.py` + `src/llm_service.py`)
**LLMService**: Anthropic Claude API integration with caching and rate limiting
**EventProcessor**: 
- **Content-Aware Analysis**: Different AI prompts for films/concerts/books
- **Preference Integration**: Personal taste scoring from `preferences.txt`
- **Summary Generation**: One-line summaries for website cards
- **Work Hours Filtering**: Removes 9am-6pm weekday events

### 3. **Output Generation Layer**
**Website Generator** (`update_website_data.py`): JSON data for GitHub Pages
**Calendar Generator** (`src/calendar_generator.py`): ICS files for Google Calendar
**Test Suite** (`tests/`): 85+ tests across unit/integration/e2e/quality validation

## Schema-Driven Development

The system uses **schemas** (`src/schemas.py`) to define data extraction patterns:
- **FilmEventSchema**: director, year, country, duration, format extraction hints
- **BookClubEventSchema**: book, author, host, discussion topic patterns  
- **ConcertEventSchema**: composers, featured_artist, classical music terminology
- **SchemaRegistry**: Central registry managing all venue-schema mappings

**Auto-Generated Scrapers** (`src/scraper_generator.py`):
- **Template System**: Generate 30-line scrapers from schemas vs 200+ line custom code
- **Configuration-Driven**: New venues via JSON config, not Python code
- **LLM Integration**: Automatic extraction hint incorporation

## Key Configuration Files

- **`src/schemas.py`**: Schema definitions with LLM extraction hints and regex patterns
- **`preferences.txt`**: Personal taste preferences for rating boosts
- **`literature_preferences.txt`**: Book/author preferences for literary events
- **`.env`**: API keys (ANTHROPIC_API_KEY, PERPLEXITY_API_KEY, FIRECRAWL_API_KEY)
- **`cache/summary_cache.json`**: AI response cache to avoid reprocessing
- **`docs/data.json`**: Generated website data for GitHub Pages
- **`tests/conftest.py`**: Pytest fixtures and test configuration

## Data Flow

1. **MultiVenueScraper** coordinates individual venue scrapers
2. **BaseScraper** uses progressive fallback (requests → pyppeteer → firecrawl → static)
3. **LLMService** extracts structured data using schema-specific prompts
4. **EventProcessor** enriches events with AI analysis and preference scoring
5. **SummaryGenerator** creates one-line summaries for website cards
6. **CalendarGenerator** produces ICS files for Google Calendar integration
7. **Website Generator** creates JSON data for GitHub Pages deployment

## Rate Limiting & API Usage

- 1-second delay between Perplexity API calls to respect rate limits
- 0.5-second delay between event detail page fetches
- Uses session with proper User-Agent headers for web scraping

## Output Format

Generated ICS files are named `afs_calendar_YYYYMMDD_HHMM.ics` and include:
- Star ratings in event titles
- Comprehensive descriptions with AI summaries and rating explanations
- Special screening indicators (✨)
- Direct links to original event pages

## Phase 2: Website Project

### Overview
A simple GitHub Pages website to make the Austin Film Society calendar accessible to the public. The site will provide downloadable .ics calendar files with rating-based filtering and display curated movie recommendations.

### Website Requirements

**Structure & Hosting:**
- Host on GitHub Pages using `docs/` folder structure in same repository
- Single-page website with clean, minimal design
- Mobile-responsive layout

**Content Display:**
- Date-organized list view of upcoming events (next 30 days)
- Movie cards with clear rating display (⭐X/10 format)
- Expandable descriptions (click to show full French cinéaste analysis)
- Movies sorted by highest rating first
- Filter out work-hour events (9am-6pm weekdays)

**Interactive Features:**
- Rating filter slider (1-10 range) for calendar downloads
- Generate filtered .ics files based on user's minimum rating selection
- Download button for filtered calendar files

**Disclaimers:**
- Personal disclaimer that ratings reflect individual preferences
- Clear attribution to Austin Film Society as source
- Statement about excluding work-hour screenings

**Automated Updates:**
- **Weekly Updates**: Every Saturday at 9 PM UTC (collects upcoming month)
- **Monthly Updates**: 1st of each month at 6 AM UTC (full month refresh)
- Generate fresh JSON data file for website consumption
- Update .ics calendar files for all rating thresholds

### Technical Implementation

**Data Pipeline:**
1. Weekly GitHub Action triggers scraper
2. Generate JSON file with: movie titles, ratings, dates, descriptions, URLs
3. Create base calendar file and filtered versions
4. Deploy updated data to GitHub Pages

**Website Files:**
- `docs/index.html` - Main single-page application
- `docs/style.css` - Styling and responsive design
- `docs/script.js` - Interactive features and filtering
- `docs/data.json` - Movie data for display
- `.ics` files generated dynamically on the client

**Key Features:**
- Client-side filtering and calendar generation
- Responsive design for mobile and desktop
- Accessible interface with clear typography
- Fast loading with minimal dependencies

### Phase 2.1: Website Enhancements

**Completed Features:**

1. **Markdown Rendering Fix:** ✅
   - Remove hashtag symbols and other markdown syntax from descriptions
   - Properly render markdown formatting (bold, headers, etc.) as HTML
   - Clean display of French cinéaste analyses

2. **Calendar View:** ✅
   - Add calendar widget/view to display events by date
   - Toggle between list view and calendar view
   - Visual calendar grid showing movie screenings
   - Click events to open AFS screening pages
   - Color-coded by rating (green=8+, yellow=6-7, gray=<6)
   - Chrome compatibility with improved date handling

3. **Movie Aggregation:** ✅
   - Group multiple screenings of same movie into single card
   - Display multiple date/time tags for each movie
   - Show all screening times and dates for each unique film
   - Reduce redundancy in movie list display

**Technical Improvements:**
- Robust error handling for calendar rendering
- Debug logging for troubleshooting
- Improved date formatting for cross-browser compatibility
- Responsive design for mobile calendar view
- Clickable calendar events linking to AFS pages

### GitHub Pages Setup Instructions

1. **Enable GitHub Pages:**
   - Go to repository Settings > Pages
   - Set Source to "Deploy from a branch"
   - Select "main" branch and "/docs" folder
   - Save settings

2. **Configure Repository Permissions:**
   - Go to repository Settings > Actions > General
   - Under "Workflow permissions", select "Read and write permissions"
   - Check "Allow GitHub Actions to create and approve pull requests"
   - Save settings

3. **Configure Secrets:**
   - Go to repository Settings > Secrets and variables > Actions
   - Add `PERPLEXITY_API_KEY` secret with your API key

4. **Manual Workflow Triggers:**
   - Go to Actions tab
   - **Weekly Update**: "Weekly Culture Calendar Update" (upcoming month)
   - **Monthly Update**: "Monthly Culture Calendar Update" (full refresh) 
   - **Re-rate Events**: "Re-rate All Events" (force fresh AI analysis)
   - Click "Run workflow" to test any workflow

5. **View Website:**
   - Website will be available at: `https://[username].github.io/Culture-Calendar/`
   - Updates automatically:
     - **Weekly**: Every Saturday at 9 PM UTC
     - **Monthly**: 1st of each month at 6 AM UTC

### Troubleshooting GitHub Actions

**Permission Denied Error (403):**
- Ensure "Read and write permissions" is enabled in Settings > Actions > General
- The workflow now includes proper `permissions: contents: write` and uses `GITHUB_TOKEN`

**API Rate Limiting:**
- The script processes all filtered events (no artificial limit)
- Built-in 1-second delay between API calls to respect rate limits
- Movie ratings are cached to avoid reprocessing the same films

**Update Frequency:**
- **Weekly**: Maintains fresh data for immediate upcoming events
- **Monthly**: Ensures complete coverage when AFS releases new month's schedule
- Both workflows collect events for "current month + next month" to fill calendar view

**Data Collection Range:**
- Collects events from 1st of current month through end of next month
- Filters out work-hour screenings (9am-6pm weekdays)
- Provides comprehensive data for calendar view display

## Production-Ready Architecture (June 2025)

The system has been fully transformed into a production-ready codebase with:

- **82% Code Reduction**: src/scraper.py reduced from 1300+ lines to 234 lines
- **Schema-Driven Development**: New venues via 30-line configuration vs 200+ line custom code  
- **Comprehensive Testing**: 85+ tests across unit/integration/e2e/quality validation
- **LLM-Powered Extraction**: Universal BaseScraper with progressive fallback system
- **Auto-Generated Scrapers**: Template system for rapid venue addition

### Core File Structure:
```
Culture-Calendar/
├── src/
│   ├── base_scraper.py          # Universal LLM scraper foundation
│   ├── llm_service.py           # Anthropic Claude API integration  
│   ├── schemas.py               # Schema definitions with extraction hints
│   ├── scraper_generator.py     # Auto-generate scrapers from templates
│   ├── scraper.py               # MultiVenueScraper orchestrator (234 lines)
│   └── scrapers/                # Individual 30-40 line venue scrapers
├── tests/                       # Comprehensive test suite (85+ tests)
├── run_tests.py                 # Test runner with coverage reporting
└── docs/                        # GitHub Pages website
```

### Completed Website Improvements:
1. ✅ **Duplicate Events** - Fixed deduplication logic in `update_website_data.py` to merge screenings by movie title
2. ✅ **Rating Extraction Bug** - Fixed decimal rating parsing (3.6/10 now correctly rounds to 4, not 6)
3. ✅ **Truncated Descriptions** - Increased API token limit and removed truncation for complete evaluations
4. ✅ **Movie Re-evaluation** - Successfully re-ran with all fixes applied
5. ✅ **Movie Metadata** - Added duration and director info scraped from AFS event pages
6. ✅ **Smart Event Filtering** - Structure-based detection of movies vs festivals/events using AFS page format
7. ✅ **Chrome Calendar Fix** - Fixed calendar width display issues in Chrome browser
8. ✅ **Cult Classic Detection** - AI-powered cult classic detection with purple badges
9. ✅ **French Movie Features** - French flag badges + 2 rating boost (capped at 10)
10. ✅ **Genre Classification** - AI-powered genre detection and display
11. ✅ **Genre Filtering** - Interactive genre toggle filters in website UI

### Enhanced Movie Cards Now Include:
- Duration and director information
- Cult classic badges (🎭)
- French movie flags (🇫🇷) with rating boost
- Genre classification and filtering
- Improved Chrome compatibility
- Explicit `isMovie` field for accurate filtering

### Smart Movie Detection System:
The system now uses **structure-based detection** instead of keyword matching:
- Detects movies by looking for "Directed by [Name]" pattern
- Validates with "Country, Year, Duration, Format" pattern
- Much more reliable than keyword filtering
- Prevents false filtering of movies with words like "festival" in title
- Adds explicit `isMovie: true/false` field to data schema

## Current Multi-Venue Status (Phase 3)

### Completed Venue Integration ✅

**🎬 Film Venues (2/2)**
1. **Austin Film Society** - Full web scraping with event details
2. **Hyperreal Film Club** - Complete integration with AI analysis

**🎼 Music Venues (4/4)**  
1. **Paramount Theater** - Full web scraping and event processing
2. **Austin Symphony Orchestra** - Season-based static data with concert analysis
3. **Texas Early Music Project** - Season-based with classical music AI reviews
4. **La Follia Austin** - Chamber music events with sophisticated analysis

**📚 Book Club Venues (2/2)**
1. **Alienated Majesty Books** - Real web scraper with intelligent fallbacks
2. **First Light Austin** - Multiple book clubs with dynamic date parsing

### Live Website Features ✅

**📱 Interactive Web Application**
- **URL**: https://hadrien-cornier.github.io/Culture-Calendar/
- **Total Events**: 117 cultural events across 7 venues
- **List View**: Sortable by rating with expandable descriptions
- **Calendar View**: Visual month-by-month event calendar
- **Venue Filtering**: Toggle venues on/off with visual indicators
- **Rating Filtering**: 1-10 slider for minimum rating threshold
- **Google Calendar**: One-click export to personal calendars
- **Download ICS**: Rating-filtered calendar files

**🔧 Technical Infrastructure**
- **Auto-Updates**: Weekly (Saturdays 9PM UTC) + Monthly (1st 6AM UTC)
- **GitHub Actions**: Automated scraping and deployment
- **Error Handling**: Graceful fallbacks for all scrapers
- **Mobile Responsive**: Works on all device sizes
- **Fast Loading**: Client-side filtering with minimal dependencies

### Book Club Scraper Architecture

**Dynamic Web Scraping with Fallbacks:**

1. **Real Web Scraping**: Attempts to extract current book information from venue websites
2. **Intelligent Parsing**: Extracts book titles, authors, dates, and hosts from HTML
3. **Date Generation**: Automatically creates future dates when scraping fails
4. **Fallback Data**: Provides sensible defaults with proper venue attribution
5. **Monthly Auto-Updates**: No manual intervention required

**Alienated Majesty Books Scraper:**
- Primary: Scrapes `/book-clubs` page for current selections
- Fallback: Generates monthly discussion dates with TBA book info
- Handles: JavaScript-heavy sites gracefully

**First Light Austin Scraper:**
- Primary: Parses 4 different book clubs from `/book-club` page
- Extracts: "World Wide What", "About Motherhood", "Small & Indie", "Future Greats"
- Date Parsing: Converts "Friday, June 27th" to proper date format
- Fallback: Host-specific defaults for each book club series

## Local Development & Debugging

### Environment Setup Issues
- **Missing API Keys**: Ensure all three API keys are set in `.env` file
- **Virtual Environment**: Always activate `venv` before running scripts
- **Python Version**: Requires Python 3.11+ for proper dependency compatibility

### Testing & Debugging Commands
```bash
# Run comprehensive test suite
python run_tests.py              # All tests with coverage
python run_tests.py unit         # Unit tests only  
python run_tests.py integration  # Integration tests
python run_tests.py fast         # Fast tests (no API calls)
python run_tests.py quality      # Data quality validation
python run_tests.py e2e          # End-to-end pipeline tests

# Test individual venue scrapers
python test_all_scrapers.py
python -c "from src.scrapers import AFSScraper; s=AFSScraper(); print(f'AFS: {len(s.scrape_events())} events')"
python -c "from src.scrapers import FirstLightAustinScraper; s=FirstLightAustinScraper(); print(f'FirstLight: {len(s.scrape_events())} events')"

# Validate system components
python -c "from src.schemas import SchemaRegistry; print('Available schemas:', SchemaRegistry.get_available_types())"
python -c "from src.scraper_generator import ScraperGenerator; g=ScraperGenerator(); print('Generator ready')"
python -c "import json; data=json.load(open('docs/data.json')); print(f'Total events: {len(data)}')"

# Cache management
ls -la cache/
rm cache/summary_cache.json  # Clear AI cache to force re-processing

# GitHub Actions validation
cat .github/workflows/update-calendar.yml
cat .github/workflows/complete-data-wipe-reload.yml
```

### Performance & Rate Limiting
- **API Delays**: Built-in 1-second delays between AI API calls
- **Web Scraping**: 0.5-second delays between page fetches
- **Cache Usage**: AI responses cached to avoid redundant processing
- **Incremental Updates**: Use `--incremental` flag for faster updates

## Testing & Debugging

### Comprehensive Test Suite (85+ Tests)

The test suite is organized into four categories:

```
tests/
├── unit/           # Unit tests for individual components
├── integration/    # Integration tests for system interactions
├── live/          # Live tests with real API calls (optional)
└── quality/       # Data quality validation tests
```

**Unit Tests** (`tests/test_units.py`):
```bash
pytest tests/test_units.py -v -m unit
```
- LLMService API integration and error handling
- BaseScraper progressive fallback system
- Schema validation and registry functionality
- SummaryGenerator caching and prompt building
- CalendarGenerator ICS file creation
- ScraperGenerator template system

**Integration Tests** (`tests/test_integration.py`):
```bash
pytest tests/test_integration.py -v -m integration
```
- MultiVenueScraper coordination and error isolation
- Individual scraper initialization and schema consistency
- EventProcessor AI pipeline integration
- Full scraping → processing → output workflows

**Data Quality Tests** (`tests/test_data_quality.py`):
```bash
pytest tests/test_data_quality.py -v -m unit
```
- Schema validation and field consistency
- Date/time format validation and business rules
- Cross-venue data quality and duplicate detection
- Data sanitization and None handling

**End-to-End Tests** (`tests/test_e2e.py`):
```bash
pytest tests/test_e2e.py -v -m integration
```
- Complete pipeline testing from scraping to calendar generation
- ICS calendar compatibility and JSON data validation
- Performance requirements and memory usage
- Error recovery and graceful degradation

**Live Integration Tests** (`tests/test_live_integration.py`):
```bash
python run_live_tests.py
# or
pytest tests/test_live_integration.py -v -s -m live
```
- **Real API Keys**: Uses actual FIRECRAWL_API_KEY and ANTHROPIC_API_KEY
- **Live Data**: Fetches real events from all venue websites
- **Mini Refresh**: Simulates complete update_website_data.py process
- **Validation**: Ensures at least one valid event per scraper
- **Pipeline Testing**: Tests scraping → AI processing → calendar generation

**Empty Extraction Tests** (`tests/test_empty_extraction.py`):
```bash
pytest tests/test_empty_extraction.py -v -m unit
```
- Edge cases where LLM returns no useful data
- Error handling for invalid JSON responses
- Validation of empty/null field handling

**New Scrapers Tests** (`tests/test_new_scrapers.py`):
```bash
pytest tests/test_new_scrapers.py -v -s
```
- LLM-powered scraper architecture validation
- Live website testing with real data
- Schema-driven development verification

### Live Testing with Real Data

The **live integration tests** are the most valuable for ensuring production readiness:

**What They Test:**
- ✅ **Real Venue Scraping**: Each scraper fetches actual events from live websites
- ✅ **Data Validation**: Events are validated against schemas and business rules
- ✅ **AI Processing**: Real AI analysis with actual event descriptions
- ✅ **Calendar Generation**: ICS files created with real event data
- ✅ **Mini Refresh**: Complete pipeline simulation

**Running Live Tests:**
```bash
# Quick start with API key checking
python run_live_tests.py

# Direct pytest with live marker
pytest tests/test_live_integration.py -v -s -m live

# Test specific venue
pytest tests/test_live_integration.py::TestLiveScraperIntegration::test_all_venue_scrapers_live -v -s
```

**Expected Results:**
- At least 3 venues should return events successfully
- At least 5 total valid events across all venues
- AI processing should work on sample events
- Calendar generation should create valid ICS files

**API Key Requirements:**
- **FIRECRAWL_API_KEY**: Required for web scraping (Firecrawl service)
- **ANTHROPIC_API_KEY**: Required for AI processing (Claude API)

### Component Validation

**Validate Individual Components:**
```bash
# Test specific scraper
python -c "from src.scrapers.afs_scraper import AFSScraper; print(AFSScraper().scrape_events())"

# Test schema validation
python -c "from src.schemas import SchemaRegistry; print(SchemaRegistry.get_available_types())"

# Test LLM service
python -c "from src.llm_service import LLMService; print(LLMService().anthropic_api_key is not None)"
```

**Cache Management:**
```bash
# Clear summary cache
rm cache/summary_cache.json

# Clear all cache
rm -rf cache/*

# View cache contents
cat cache/summary_cache.json | jq '.'
```

**GitHub Actions Validation:**
```bash
# Test workflow locally
python update_website_data.py

# Check generated files
ls -la docs/
cat docs/data.json | jq '.movies | length'
```