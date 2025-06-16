# Culture Calendar - Phase 1

An automated system to aggregate, enrich, and consolidate cultural events from Austin Film Society into a personalized ICS calendar file.

## Features

- **Automated Web Scraping**: Fetches events from Austin Film Society calendar
- **AI-Powered Ratings**: Uses Perplexity AI to research and rate films
- **Personal Preferences**: Customizable scoring based on your preferences
- **Special Screening Detection**: Identifies Q&As, 35mm prints, and other special events  
- **ICS Calendar Generation**: Creates importable calendar files for Google Calendar
- **Scheduling**: Optional automated runs via cron or built-in scheduler

## Setup

1. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure API Keys**
   ```bash
   cp .env.example .env
   # Edit .env and add your API keys:
   # PERPLEXITY_API_KEY=your_key_here
   # FIRECRAWL_API_KEY=your_key_here (optional for Phase 1)
   ```

3. **Customize Preferences**
   Edit `preferences.txt` to include directors, genres, and keywords you're interested in.

## Usage

### Manual Run
```bash
python main.py
```

This will:
- Scrape the AFS calendar
- Process and rate events based on AI analysis and your preferences  
- Generate an ICS file named `afs_calendar_YYYYMMDD_HHMM.ics`

### Scheduled Runs
```bash
python scheduler.py
```

Runs the calendar generator:
- Daily at 9:00 AM
- Wednesday evenings at 6:00 PM

### Import to Google Calendar
1. Open Google Calendar
2. Click the "+" next to "Other calendars"
3. Select "Import"
4. Upload the generated `.ics` file

## Project Structure

```
Culture-Calendar/
├── main.py                 # Main application entry point
├── scheduler.py            # Automated scheduling
├── requirements.txt        # Python dependencies
├── preferences.txt         # Personal preferences for rating
├── .env.example           # Environment variables template
└── src/
    ├── scraper.py         # Web scraping logic
    ├── processor.py       # Event enrichment and rating
    └── calendar_generator.py # ICS file generation
```

## Rating System

Events are rated on a 1-10 scale using:

- **AI Base Rating**: Perplexity AI research on the film
- **Preference Boost**: +2 points per matching keyword/director
- **Special Screening Bonus**: +3 points for Q&As, special prints, etc.

## Example Output

```
⭐8/10 - RAN 4K
📍 Austin Film Society Cinema
🎬 AI Rating: 7/10 | Personal preference boost: +1 | ✨ Special screening
📝 Akira Kurosawa's epic masterpiece, widely considered one of the greatest films...
```

## Troubleshooting

- **No events found**: Check if AFS website structure has changed
- **API errors**: Verify your Perplexity API key in `.env`
- **Import issues**: Ensure the `.ics` file was generated successfully

## Roadmap

- **Phase 2**: Add more event sources (bookstores, music venues)
- **Phase 3**: Direct Google Calendar API integration  
- **Phase 4**: Web interface for management and configuration