# 🎬 Culture Calendar

An automated system that transforms Austin cultural events into a curated, intelligent calendar experience. Features AI-powered film and classical music analysis, personalized ratings, and a beautiful web interface with downloadable calendars covering Austin Film Society, Hyperreal Film Club, and Austin Symphony Orchestra.

## 🌟 Features

### 🤖 Smart Event Processing
- **Structure-Based Movie Detection**: Identifies real movies vs festivals using AFS page format
- **Multi-Venue Support**: Fetches events from Austin Film Society, Hyperreal Film Club, and Austin Symphony Orchestra
- **AI-Powered Analysis**: French cinéaste-style film reviews and distinguished music critic classical analysis using Perplexity AI
- **Clean Metadata Extraction**: Country, year, duration, language from structured format
- **Personal Preference Scoring**: Customizable ratings based on your taste
- **Special Screening Detection**: Identifies Q&As, 35mm prints, and rare screenings
- **Work Hours Filtering**: Automatically excludes 9am-6pm weekday events

### 🌐 Modern Web Interface
- **GitHub Pages Website**: Beautiful, responsive single-page application
- **Multi-Venue Support**: AFS, Hyperreal Film Club, and Austin Symphony events with venue tags
- **Dual View Modes**: Toggle between list and calendar views
- **Movie Aggregation**: Multiple showtimes grouped under single movie cards
- **Rich Movie Cards**: Duration, director, country, year, language, and venue badges
- **Interactive Calendar**: Visual month view with color-coded ratings and filtering
- **Country Filtering**: Filter movies by country of origin
- **Rating Filter**: Download custom calendars filtered by minimum rating (1-10)
- **Mobile Responsive**: Works perfectly on all devices

### ⚡ Automated Updates
- **Weekly Refresh**: Every Saturday evening (upcoming month)
- **Monthly Refresh**: 1st of each month (complete coverage)
- **GitHub Actions**: Fully automated via CI/CD
- **No Maintenance Required**: Set it and forget it

## 🚀 Quick Start

### 🌐 Use the Live Website
Visit **[hadrien-cornier.github.io/Culture-Calendar](https://hadrien-cornier.github.io/Culture-Calendar)** to:
- Browse AI-rated films and classical music concerts
- Toggle between list and calendar views  
- Download filtered .ics calendar files
- View detailed French cinéaste film analyses and music critic concert reviews

### 🔧 Setup Your Own Instance

1. **Fork & Clone**
   ```bash
   git clone https://github.com/your-username/Culture-Calendar.git
   cd Culture-Calendar
   ```

2. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment**
   ```bash
   cp .env.example .env
   # Edit .env and add:
   # PERPLEXITY_API_KEY=your_key_here
   ```

4. **Customize Preferences**
   Edit `preferences.txt` with your favorite directors, genres, and keywords.

5. **Enable GitHub Pages & Actions**
   - Go to repository Settings > Pages
   - Set source to "main branch /docs folder"
   - Go to Settings > Actions > General  
   - Enable "Read and write permissions"
   - Add `PERPLEXITY_API_KEY` to repository secrets

## 🎯 Usage

### 🌐 Web Interface
The GitHub Pages website provides the easiest way to use Culture Calendar:

- **📝 List View**: Browse movies sorted by rating with expandable reviews
- **📅 Calendar View**: Visual monthly calendar with color-coded events  
- **🎚️ Rating Filter**: Adjust slider to filter movies by minimum rating
- **⬇️ Download**: Generate custom .ics files for Google Calendar

### 🔧 Manual Local Run
```bash
# Activate virtual environment
source venv/bin/activate

# Generate calendar data
python main.py

# Update website data  
python update_website_data.py
```

### 📅 Import to Google Calendar
1. Download .ics file from website or use pre-filtered versions
2. Open Google Calendar
3. Click "+" next to "Other calendars" → Import
4. Upload the .ics file

### ⚡ Automated Updates
Once set up, the system runs automatically:
- **Weekly**: Saturdays at 9 PM UTC (fresh data)
- **Monthly**: 1st of month at 6 AM UTC (full refresh)
- **Manual**: Trigger workflows anytime via GitHub Actions

## 📁 Project Structure

```
Culture-Calendar/
├── 🌐 Website Files
│   └── docs/
│       ├── index.html              # Main website
│       ├── style.css               # Responsive design  
│       ├── script.js               # Interactive features
│       ├── data.json               # Movie data (auto-generated)
│       └── calendars/              # Pre-filtered .ics files
│
├── 🤖 Automation
│   ├── .github/workflows/
│   │   ├── update-calendar.yml     # Weekly updates
│   │   └── monthly-calendar-update.yml # Monthly updates
│   ├── update_website_data.py      # Website data generator
│   └── main.py                     # CLI calendar generator
│
├── 🔧 Core Logic  
│   └── src/
│       ├── scraper.py              # Multi-venue web scraping (AFS, Hyperreal, Symphony)
│       ├── processor.py            # AI analysis & rating for films and concerts
│       └── calendar_generator.py   # ICS file creation
│
└── ⚙️ Configuration
    ├── preferences.txt             # Personal taste preferences
    ├── requirements.txt            # Python dependencies
    ├── .env.example               # Environment template
    └── CLAUDE.md                  # AI assistant instructions
```

## 🎯 Rating System

Movies are intelligently rated on a 1-10 scale using:

- **🤖 AI Analysis**: French cinéaste-style research via Perplexity AI
- **❤️ Personal Preferences**: +2 points per matching director/genre/keyword  
- **✨ Special Screenings**: +3 points for Q&As, 35mm prints, rare formats
- **🎬 Smart Filtering**: Only actual movies (no festivals or events)
- **⏰ Accessibility**: Automatic filtering of work-hour screenings

### 📊 Rating Categories
- **🟢 8-10**: Masterpieces and must-sees
- **🟡 6-7**: Solid films worth considering  
- **⚫ 1-5**: Lower priority or niche appeal

## 🎬 Sample Analysis

```
⭐9/10 - NIGHT OF THE LIVING DEAD

Rating: 9/10 - Reflecting its artistic merit, cultural significance, and 
intellectual depth, "Night of the Living Dead" is a seminal work that 
rewards contemplation.

🎬 Synopsis: A study in fear, isolation, and the breakdown of societal 
norms, following seven people trapped in a farmhouse besieged by 
reanimated corpses.

👤 Director: George A. Romero - pioneering filmmaker known for his 
innovative approach to horror cinema and social commentary.

📅 Screenings:
• Jun 18 • 8:45 PM
• Jun 23 • 7:00 PM
```

## 🔧 Troubleshooting

### Common Issues
- **Website not loading**: Check GitHub Pages is enabled in repository settings
- **No calendar data**: Verify GitHub Actions have repository write permissions  
- **API errors**: Ensure `PERPLEXITY_API_KEY` is added to repository secrets
- **Missing events**: AFS website structure may have changed (check scraper.py)

### GitHub Actions Issues
- **403 Permission Error**: Enable "Read and write permissions" in Settings > Actions
- **Workflow not running**: Check cron schedule and repository activity requirements
- **API rate limiting**: Built-in delays handle this automatically

### Debug Mode
```bash
# Test locally with debug output
source venv/bin/activate  
python main.py --debug
```

## 🗺️ Roadmap

### 📋 Completed Features
- ✅ **Phase 1**: Austin Film Society integration
- ✅ **Phase 2**: GitHub Pages website with calendar view
- ✅ **Phase 2.1**: Enhanced UI with movie aggregation and markdown rendering
- ✅ **Phase 2.2**: Multi-venue support with Hyperreal Film Club integration
- ✅ **Phase 2.3**: Austin Symphony Orchestra integration with full 2025-2026 season data

### 🔮 Future Enhancements
- **📚 Phase 3**: Additional venues
  - **Paramount Theatre**: API investigation needed (endpoint restrictions)
  - **The ABGB**: Music and film events
  - **BookPeople**: Author events and film screenings
  - **Independent galleries**: Art house screenings
- **🔗 Phase 4**: Direct Google Calendar API integration  
- **🎨 Phase 5**: Enhanced UI with advanced filtering and recommendations
- **📱 Phase 6**: Mobile app or PWA version

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [Austin Film Society](https://www.austinfilm.org/) for providing amazing film programming
- [Hyperreal Film Club](https://hyperrealfilm.club/) for curated independent cinema
- [Austin Symphony Orchestra](https://austinsymphony.org/) for world-class classical music performances
- [Perplexity AI](https://www.perplexity.ai/) for intelligent cultural analysis
- Built with ❤️ for Austin culture enthusiasts
