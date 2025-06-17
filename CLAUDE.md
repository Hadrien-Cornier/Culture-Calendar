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
- `docs/calendars/` - Directory for .ics download files

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
   - Click "Run workflow" to test either one

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

## Recent Website Improvements (Completed)

### Critical Fixes:
1. ✅ **Duplicate Events** - Fixed deduplication logic in `update_website_data.py` to merge screenings by movie title
2. ✅ **Rating Extraction Bug** - Fixed decimal rating parsing (3.6/10 now correctly rounds to 4, not 6)
3. ✅ **Truncated Descriptions** - Increased API token limit and removed truncation for complete evaluations
4. ✅ **Movie Re-evaluation** - Successfully re-ran with all fixes applied

### New Features Added:
1. ✅ **Movie Metadata** - Added duration and director info scraped from AFS event pages
2. ✅ **Smart Event Filtering** - Structure-based detection of movies vs festivals/events using AFS page format
3. ✅ **Chrome Calendar Fix** - Fixed calendar width display issues in Chrome browser
4. ✅ **Cult Classic Detection** - AI-powered cult classic detection with purple badges
5. ✅ **French Movie Features** - French flag badges + 2 rating boost (capped at 10)
6. ✅ **Genre Classification** - AI-powered genre detection and display
7. ✅ **Genre Filtering** - Interactive genre toggle filters in website UI

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