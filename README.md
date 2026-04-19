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
- **ICS Downloads**: Generate calendar files on demand
- **Download ICS**: Rating-filtered calendar files created when you click download
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
- Download **custom .ics calendar files** generated when you click "Download"
- Read **AI-powered cultural analysis** for films, concerts, and books
- Export events to your calendar via **on-the-fly ICS download**

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
   Edit `preferences.txt` with your favorite directors, genres, and keywords. For book club events, you can also add classic authors in `literature_preferences.txt`.

5. **Enable GitHub Pages & Actions**
   - Go to repository Settings > Pages
   - Set source to "main branch /docs folder"
   - Go to Settings > Actions > General  
   - Enable "Read and write permissions"
   - Add `PERPLEXITY_API_KEY` to repository secrets

6. **Install Node Dependencies & Index with GitNexus** _(optional, for AI code intelligence)_
   ```bash
   npm install
   npm run analyze
   # Output: 781 nodes | 1,928 edges | 56 clusters | 63 flows

   # Generate wiki (requires OPENAI_API_KEY or GITNEXUS_API_KEY):
   export OPENAI_API_KEY=sk-...
   npm run wiki
   ```
   > **Note**: Do not use `npx gitnexus` — it fails on Node v24. Use `npm run analyze` instead.

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
    ├── literature_preferences.txt  # Classic literature interests
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
- **🟢 9-10**: Timeless classics and masterpieces
- **🟡 7-8**: Strong recommendations with notable merit
- **⚪ 5-6**: Average quality
- **⚫ 1-4**: Lower priority or niche appeal

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
  - **Alamo Drafthouse**: Classic Austin cinema experience
  - **Violet Crown Cinema**: Independent and international films
  - **East Austin Movie Theater**: Revived single-screen cinema
  - **The Long Center**: Performing arts, including opera and ballet
  - **The VORTEX**: Experimental theater and performance art
  - **Beerthoven Concert Series**: Casual classical music events
  - **BookPeople**: Author events and readings
  - **Austin Public Library**: Author talks, readings, and workshops
- **🔗 Phase 5**: Direct Google Calendar API integration  
- **🎨 Phase 6**: Enhanced recommendations and discovery features
- **📱 Phase 7**: Mobile app or PWA version
- **ექს Phase 8**: Experimental and niche venues
  - **The Museum of Human Achievement**: Unconventional performances and art
  - **Fusebox Festival**: Annual festival for innovative and genre-defying work
  - **dadaLab**: Tech-art gallery and event space

## Venue Wishlist

Roadmap candidates for future scraper integration. Each entry is `venue-name (category) — why-interesting`. Sourced from the existing Phase 4 and Phase 8 entries in the Roadmap above; `scripts/prospect_venues.py` (T4.2) later appends Perplexity-discovered additions below the seed list.

<!-- venue-wishlist:begin -->
- [ ] Alamo Drafthouse (movie) — classic Austin cinema experience with programming flavor beyond the chains
- [ ] Violet Crown Cinema (movie) — independent and international films, art-house booking
- [ ] East Austin Movie Theater (movie) — revived single-screen cinema with neighborhood curation
- [ ] The Long Center (concert) — performing arts venue, including opera and ballet touring
- [ ] The VORTEX (dance/theater) — experimental theater and performance art
- [ ] Beerthoven Concert Series (concert) — casual classical music events in non-traditional settings
- [ ] BookPeople (book_club) — author events and readings from Austin's flagship indie bookstore
- [ ] Austin Public Library (book_club) — author talks, readings, and workshops across branches
- [ ] The Museum of Human Achievement (visual_arts) — unconventional performances and installation art
- [ ] Fusebox Festival (visual_arts) — annual festival for innovative and genre-defying work
- [ ] dadaLab (visual_arts) — tech-art gallery and event space

### Prospecting additions — 2026-04-19

Sourced from `scripts/prospect_venues.py` runs against Perplexity Sonar; deduped against the seed list above. URLs are the candidate event-calendar pages reported by the prospector — verify before onboarding.

- [ ] Dougherty Arts Center (visual_arts) — community arts venue hosting exhibitions and workshops with browsable online calendar — https://www.austintexas.gov/department/dougherty-arts-center/events
- [ ] Blanton Museum of Art (visual_arts) — university museum with gallery programs and a dedicated online programs calendar — https://blantonmuseum.org/programs/
- [ ] The Contemporary Austin (visual_arts) — major visual arts museum with exhibitions and public events on a browsable online calendar — https://thecontemporaryaustin.org/calendar/
- [ ] Umlauf Sculpture Garden and Museum (visual_arts) — sculpture garden and museum hosting visual arts events with online calendar — https://umlaufsculpture.org/events/
- [ ] ICOSA Collective (visual_arts) — artist collective hosting visual arts exhibitions and public events with browsable online listings — https://icosacollective.com/events/
- [ ] Ivester Contemporary (visual_arts) — contemporary art gallery with exhibitions and events on online calendar — https://ivestercontemporary.com/events/
- [ ] Paggi House (visual_arts) — venue hosting visual arts exhibitions open to the public with event listings — https://paggihouse.com/events
- [ ] Neill-Cochran House Museum (visual_arts) — historic house museum with visual arts exhibitions and public receptions listed online — https://www.neillcochranhousemuseum.org/events/
- [ ] Saxon Pub (concert) — listed in the Austin Chronicle music calendar with regular live music events — https://calendar.austinchronicle.com/austin/EventSearch?eventSection=2163369&sortType=date&v=g
- [ ] Continental Club (concert) — popular Austin venue for live music concerts featured in online event calendars — https://calendar.austinchronicle.com/austin/EventSearch?eventSection=2163369&sortType=date&v=g
- [ ] Mohawk (concert) — venue hosting public concerts listed in the official Austin music events calendar — https://www.austintexas.org/things-to-do/music/concerts-in-austin/
- [ ] Sahara Lounge (concert) — intimate live music venue with events in the Austin tourism calendar — https://www.austintexas.org/things-to-do/music/concerts-in-austin/
- [ ] Emo's Austin (concert) — iconic punk/rock concert venue with a ticketed public events calendar — https://www.ticketmaster.com/discover/austin?categoryId=KZFzniwnSyZfZ7v7nJ
- [ ] Scoot Inn (concert) — outdoor/indoor concert space with browsable event listings — https://www.ticketmaster.com/discover/austin?categoryId=KZFzniwnSyZfZ7v7nJ
- [ ] Empire Control Room & Garage (concert) — multi-room venue for public concerts with online Bandsintown calendar — https://www.bandsintown.com/c/austin-tx
- [ ] Lone Star Court (concert) — hosts regular public live music events with dedicated browsable calendar — https://www.lonestarcourt.com/live-music-and-events.aspx
<!-- venue-wishlist:end -->

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

___

Problems : 

- not all scrapers work in parallel because of 'pyppeteer link extraction error: signal only works in main thread of the main interpreter'
- read review button crasher site
- ratings are not very customized and spread out enough