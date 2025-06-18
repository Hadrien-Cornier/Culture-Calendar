# 🎬 Culture Calendar

An automated system that transforms Austin cultural events into a curated, intelligent calendar experience. Features AI-powered analysis for films, classical music, and book clubs, with personalized ratings and a beautiful web interface covering **7 major Austin cultural venues**.

## 🌟 Features

### 🤖 Smart Event Processing
- **7-Venue Integration**: Comprehensive coverage across film, music, and literary venues
- **AI-Powered Analysis**: French cinéaste film reviews, distinguished music criticism, and sophisticated literary analysis
- **Multi-Format Support**: Movies, concerts, chamber music, and book club discussions
- **Dynamic Web Scraping**: Real-time data extraction with intelligent fallbacks
- **Personal Preference Scoring**: Customizable ratings based on your cultural taste
- **Special Event Detection**: Q&As, 35mm prints, special screenings, and exclusive performances
- **Work Hours Filtering**: Automatically excludes 9am-6pm weekday events

### 🌐 Modern Web Interface
- **GitHub Pages Website**: Beautiful, responsive single-page application
- **7-Venue Coverage**: Film, music, and book club events with distinctive venue tags
- **Dual View Modes**: Toggle between list and calendar views  
- **Event Aggregation**: Multiple showtimes/dates grouped under single event cards
- **Rich Event Cards**: Duration, director/author, country, year, language, and venue badges
- **Interactive Calendar**: Visual month view with color-coded ratings and venue indicators
- **Advanced Filtering**: Filter by venue, country, rating, and special events
- **Google Calendar Export**: One-click integration with personal calendars
- **Download ICS**: Rating-filtered calendar files for any calendar app
- **Mobile Responsive**: Works perfectly on all devices

### ⚡ Automated Updates
- **Weekly Refresh**: Every Saturday evening (upcoming month)
- **Monthly Refresh**: 1st of each month (complete coverage)
- **GitHub Actions**: Fully automated via CI/CD
- **No Maintenance Required**: Set it and forget it

## 🚀 Quick Start

### 🌐 Use the Live Website
Visit **[hadrien-cornier.github.io/Culture-Calendar](https://hadrien-cornier.github.io/Culture-Calendar)** to:
- Browse **117+ cultural events** across 7 Austin venues
- Filter by **venue, rating, country** with real-time updates
- Switch between **list and calendar views** 
- Download **custom .ics calendar files** filtered by rating
- Read **AI-powered cultural analysis** for films, concerts, and books
- Export events directly to **Google Calendar**

**Current Venues:**
🎬 **Film**: Austin Film Society, Hyperreal Film Club  
🎼 **Music**: Paramount Theater, Austin Symphony, Early Music Austin, La Follia  
📚 **Books**: Alienated Majesty Books, First Light Austin

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
│       ├── scraper.py              # 7-venue web scraping with intelligent fallbacks
│       ├── processor.py            # AI analysis for films, concerts, and book clubs
│       └── calendar_generator.py   # ICS file creation
│
└── ⚙️ Configuration
    ├── preferences.txt             # Personal taste preferences
    ├── requirements.txt            # Python dependencies
    ├── .env.example               # Environment template
    └── CLAUDE.md                  # AI assistant instructions
```

## 🎯 Rating System

All cultural events are intelligently rated on a 1-10 scale using:

- **🤖 AI Analysis**: 
  - **Films**: French cinéaste-style critiques focusing on artistic merit
  - **Music**: Distinguished classical music criticism and performance analysis
  - **Books**: Sophisticated literary criticism and discussion value assessment
- **❤️ Personal Preferences**: +2 points per matching director/author/genre/keyword  
- **✨ Special Events**: +3 points for Q&As, special screenings, exclusive performances
- **🎯 Smart Classification**: Proper categorization by event type and venue
- **⏰ Accessibility**: Automatic filtering of work-hour events

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

### 📋 Completed Features ✅
- ✅ **Phase 1**: Austin Film Society integration
- ✅ **Phase 2**: GitHub Pages website with calendar view
- ✅ **Phase 2.1**: Enhanced UI with movie aggregation and markdown rendering
- ✅ **Phase 2.2**: Multi-venue support with Hyperreal Film Club integration
- ✅ **Phase 2.3**: Austin Symphony Orchestra integration with full 2025-2026 season data
- ✅ **Phase 3**: Complete 7-venue integration
  - ✅ **Paramount Theatre**: Full web scraping and event processing
  - ✅ **Early Music Austin**: Season-based classical music events
  - ✅ **La Follia Austin**: Chamber music concerts with AI analysis
  - ✅ **Alienated Majesty Books**: Dynamic book club scraping with fallbacks
  - ✅ **First Light Austin**: Multiple book clubs with intelligent parsing

### 🔮 Future Enhancements
- **📚 Phase 4**: Additional Austin venues
  - **The ABGB**: Music and film events
  - **BookPeople**: Author events and readings
  - **Independent galleries**: Art house screenings and exhibitions
  - **Ballet Austin**: Dance performances
- **🔗 Phase 5**: Direct Google Calendar API integration  
- **🎨 Phase 6**: Enhanced recommendations and discovery features
- **📱 Phase 7**: Mobile app or PWA version

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

**🎬 Film Venues:**
- [Austin Film Society](https://www.austinfilm.org/) for providing amazing film programming
- [Hyperreal Film Club](https://hyperrealfilm.club/) for curated independent cinema

**🎼 Music Venues:**
- [Paramount Theatre](https://www.austinparamount.com/) for diverse cultural programming
- [Austin Symphony Orchestra](https://austinsymphony.org/) for world-class classical performances
- [Texas Early Music Project](https://www.early-music.org/) for authentic historical performances
- [La Follia Austin](https://www.tickettailor.com/events/lafolliaaustin/) for intimate chamber music

**📚 Literary Venues:**
- [Alienated Majesty Books](https://www.alienatedmajestybooks.com/) for thoughtful book discussions
- [First Light Austin](https://www.firstlightaustin.com/) for diverse literary programming

**🤖 Technology:**
- [Perplexity AI](https://www.perplexity.ai/) for intelligent cultural analysis
- Built with ❤️ for Austin culture enthusiasts
