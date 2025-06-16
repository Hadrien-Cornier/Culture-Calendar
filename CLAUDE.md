# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Culture Calendar is a Python application that automatically scrapes Austin Film Society events, enriches them with AI-powered ratings and personal preferences, and generates ICS calendar files for import into Google Calendar. The project is currently in Phase 1 (MVP) focusing on AFS integration only.

## Common Commands

```bash
# Run the main application
python main.py

# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Then edit .env to add PERPLEXITY_API_KEY
```

## Virtual Environment

- Use the venv python environment to run anything in here

## Future Scheduling

The project will use GitHub Actions for automated scheduling instead of local cron jobs or the scheduler.py file.

## Architecture

The application follows a pipeline architecture with three main components:

1. **Scraper** (`src/scraper.py`): Web scraping logic for AFS calendar
   - `AFSScraper.scrape_calendar()` - Fetches main calendar page
   - `AFSScraper.get_event_details()` - Gets individual event details
   - Detects special screenings (Q&A, 35mm prints, etc.)

2. **Processor** (`src/processor.py`): Event enrichment and rating
   - Uses Perplexity AI API for movie ratings and summaries
   - Applies personal preferences from `preferences.txt` (+2 points per match)
   - Adds special screening bonus (+3 points)
   - Combines AI rating with preference boosts for final score

3. **Calendar Generator** (`src/calendar_generator.py`): ICS file creation
   - Generates standard ICS format with event details
   - Includes ratings in event titles (⭐8/10 format)
   - Adds comprehensive descriptions with ratings explanations
   - Uses Austin timezone (America/Chicago)

## Key Configuration Files

- **`preferences.txt`**: Personal preferences (directors, genres, keywords) used for rating boosts
- **`.env`**: Environment variables, primarily `PERPLEXITY_API_KEY`
- **`requirements.txt`**: Python dependencies including requests, beautifulsoup4, icalendar

## Data Flow

1. Scrape AFS calendar page for event links and basic info
2. Follow each event link to get detailed descriptions
3. Send movie titles to Perplexity AI for ratings and summaries
4. Calculate preference scores based on user preferences file
5. Generate final ratings combining AI scores + preference boosts + special screening bonuses
6. Create ICS file with enriched event data

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