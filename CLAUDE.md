# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Culture Calendar is a comprehensive Python application that automatically scrapes Austin cultural events from multiple venues, enriches them with AI-powered ratings and personal preferences, and provides both ICS calendar files and a live website. The project has expanded beyond Phase 1 to include 7 major Austin cultural venues.

## Common Commands

```bash
# Update website data (incremental - new events only)
source venv/bin/activate && python update_website_data_configurable.py --incremental

# Update website data (full refresh)
source venv/bin/activate && python update_website_data_configurable.py --full

# Update specific venues only
source venv/bin/activate && python update_website_data_configurable.py --incremental --venues AFS,Hyperreal

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

The application follows a multi-venue pipeline architecture with three main components:

### 1. **Multi-Venue Scraper** (`src/scraper.py`): 
Comprehensive web scraping for 7 Austin cultural venues:

**Film Venues:**
- `AFSScraper` - Austin Film Society calendar and event details
- `HyperrealFilmClubScraper` - Hyperreal Film Club events

**Music Venues:**  
- `ParameterTheaterScraper` - Paramount Theater events
- `AustinSymphonyOrchestraScraper` - Symphony season data (static)
- `EarlyMusicAustinScraper` - Early music concerts (static)
- `LaFolliaAustinScraper` - Chamber music events (static)

**Book Clubs:**
- `AlienatedMajestyBooksScraper` - Real web scraping with fallback data
- `FirstLightAustinScraper` - Real web scraping with fallback data

### 2. **AI Processor** (`src/processor.py`): 
Event enrichment and intelligent rating:
- **Movie Analysis**: Perplexity AI for cinematic critique and ratings
- **Concert Analysis**: Classical music analysis for symphony/chamber events  
- **Book Club Analysis**: Literary criticism for book discussions
- **Preference Integration**: `preferences.txt` scoring (+2 points per match)
- **Special Event Bonuses**: +3 points for special screenings
- **Final Rating Calculation**: AI score + preferences + bonuses

### 3. **Website Generator** (`update_website_data.py`): 
Modern web application creation:
- **Event Aggregation**: Groups multiple screenings by movie/event
- **JSON API**: Generates `docs/data.json` for website consumption
- **ICS Calendars**: Multiple rating-filtered calendar files
- **Incremental Updates**: Smart duplicate detection and merging
- **Venue-Specific Processing**: Handles different event types appropriately

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