# Culture Calendar Website

This is the GitHub Pages website for the Culture Calendar project. It provides a user-friendly interface to browse Austin Film Society events with AI-powered ratings and download filtered calendar files.

## Features

- **Movie Listings**: Browse upcoming movies sorted by rating (highest first)
- **Expandable Descriptions**: Click to read full French cinéaste-style film analyses
- **Rating Filter**: Use the slider to filter movies by minimum rating
- **Calendar Downloads**: Generate .ics files with only movies meeting your rating criteria
- **Work Hours Filtering**: Automatically excludes screenings during 9am-6pm weekdays
- **Mobile Responsive**: Works great on phones, tablets, and desktop

## Files

- `index.html` - Main website page
- `style.css` - Responsive styling and design
- `script.js` - Interactive features and calendar generation
- `data.json` - Movie data (updated weekly by GitHub Actions)
- `calendars/` - Pre-generated calendar files for different rating thresholds

## Automatic Updates

The website data is automatically updated every Saturday evening via GitHub Actions, maintaining a rolling 30-day window of upcoming events.

## Local Development

To test locally:
```bash
cd docs
python3 -m http.server 8000
# Visit http://localhost:8000
```

## Deployment

This site is automatically deployed via GitHub Pages from the `docs/` folder.