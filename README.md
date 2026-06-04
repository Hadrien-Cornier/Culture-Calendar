# 🎬 Culture Calendar

An automated system that transforms Austin cultural events into a curated, intelligent calendar experience. Features AI-powered analysis across film, classical music, opera, ballet, book clubs, and visual arts, with personalized ratings and a beautiful web interface covering **13 active Austin cultural venues**.

## 🌟 Features

### 🤖 Smart Event Processing
- **Multi-Venue Integration**: Comprehensive coverage across film, classical music, opera, ballet, literary, and visual-arts venues
- **AI-Powered Analysis**: French cinéaste film reviews, distinguished music criticism, sophisticated literary analysis, and art-critic exhibition writeups
- **Multi-Format Support**: Movies, concerts, opera, ballet/dance, book-club discussions, and visual-arts exhibitions
- **Dynamic Web Scraping**: Real-time data extraction with intelligent fallbacks
- **Personal Preference Scoring**: Customizable ratings based on your cultural taste
- **Special Event Detection**: Q&As, 35mm prints, special screenings, and exclusive performances
- **Work Hours Filtering**: Automatically excludes 9am-6pm weekday events

### 🌐 Modern Web Interface
- **GitHub Pages Website**: Beautiful, responsive single-page application
- **Multi-Venue Coverage**: Film, music, opera, ballet, book-club, and visual-arts events with distinctive venue tags
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
- Browse cultural events across 13 active Austin venues
- Filter by **venue, rating, country** with real-time updates
- Switch between **list and calendar views** 
- Download **custom .ics calendar files** generated when you click "Download"
- Read **AI-powered cultural analysis** for films, concerts, opera, ballet, books, and exhibitions
- Export events to your calendar via **on-the-fly ICS download**

**Current Venues** (active in `config/master_config.yaml` + `src/scraper.py`):

🎬 **Film**: Austin Film Society, Hyperreal Film Club, Paramount Theatre  
🎼 **Classical / Opera / Ballet**: Austin Symphony, Early Music Austin, La Follia, Austin Chamber Music, Austin Opera, Ballet Austin  
📚 **Book Clubs**: Alienated Majesty Books, First Light Austin, Livra Books  
🎨 **Visual Arts**: NowPlayingAustin (visual-arts listings)

> _Disabled in config (not scraped):_ Arts on Alexander. The classical/opera/ballet venues are not scraped per-event — they ship as static season JSON via a config-driven registry (see [Architecture](#-architecture)).

## 🤖 For AI agents

Endpoints designed for agents — LLM tools, crawlers, and downstream automations. Culture Calendar publishes several machine-readable surfaces as static files on GitHub Pages; no auth, no rate limits beyond Pages defaults.

- **[`llms.txt`](https://hadrien-cornier.github.io/Culture-Calendar/llms.txt)** — [llmstxt.org](https://llmstxt.org/)-formatted index of every page and feed on the site. Start here.
- **[`llms-full.txt`](https://hadrien-cornier.github.io/Culture-Calendar/llms-full.txt)** — plain-text dump of the top events with HTML stripped, for reasoning over the corpus without per-event fetches.
- **[`/api/`](https://hadrien-cornier.github.io/Culture-Calendar/api/)** — JSON aggregates: [`events.json`](https://hadrien-cornier.github.io/Culture-Calendar/api/events.json), [`top-picks.json`](https://hadrien-cornier.github.io/Culture-Calendar/api/top-picks.json), [`venues.json`](https://hadrien-cornier.github.io/Culture-Calendar/api/venues.json), [`people.json`](https://hadrien-cornier.github.io/Culture-Calendar/api/people.json), [`categories.json`](https://hadrien-cornier.github.io/Culture-Calendar/api/categories.json). Per-event JSON at `/events/<slug>.json` mirrors the page-level JSON-LD.
- **[`.well-known/ai-agent.json`](https://hadrien-cornier.github.io/Culture-Calendar/.well-known/ai-agent.json)** — agent manifest describing every endpoint above plus the feeds. Use as the entry point for automated discovery.
- **Feeds** — [`feed.xml`](https://hadrien-cornier.github.io/Culture-Calendar/feed.xml) (RSS 2.0 of top picks), [`calendar.ics`](https://hadrien-cornier.github.io/Culture-Calendar/calendar.ics) (all events, iCal), [`top-picks.ics`](https://hadrien-cornier.github.io/Culture-Calendar/top-picks.ics) (top picks only, iCal), [`sitemap.xml`](https://hadrien-cornier.github.io/Culture-Calendar/sitemap.xml).
- **Crawler policy** — `robots.txt` explicitly allows GPTBot, ClaudeBot, PerplexityBot, CCBot, Google-Extended, Meta-ExternalAgent, and Amazonbot.

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
   # PERPLEXITY_API_KEY=your_key_here    # AI ratings/reviews (required)
   # ANTHROPIC_API_KEY=your_key_here     # one-line summaries
   # OPENROUTER_API_KEY=your_key_here    # LLM Council quality gate (optional)
   ```

4. **Customize Preferences**
   Edit `preferences.txt` with your favorite directors, genres, and keywords. For book club events, you can also add classic authors in `literature_preferences.txt`.

5. **Enable GitHub Pages & Actions**
   - Go to Settings > Actions > General, enable "Read and write permissions"
   - Add `PERPLEXITY_API_KEY` (and `ANTHROPIC_API_KEY`) to repository secrets
   - Optionally add `OPENROUTER_API_KEY` to enable the LLM Council gate in CI
   - Configure GitHub Pages **after** the first deploy — see [Deployment](#-deployment) (Pages serves from the `gh-pages` branch, not `main`)

6. **Install Node Dependencies & Index with GitNexus** _(optional, for AI code intelligence)_
   ```bash
   npm install
   npm run analyze

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

### 🔧 Commands

```bash
# Setup
pip install -r requirements.txt

# Scrape + enrich + write docs/data.json
python update_website_data.py              # full scrape + enrichment
python update_website_data.py --test-week  # current week only
python update_website_data.py --force-reprocess  # ignore cache
python update_website_data.py --validate   # fail-fast on scraper failures

# Tests
pytest tests/ -m "not live and not integration"  # unit only (no network)
pytest tests/                                     # all tests

# Code quality
black src/ tests/ *.py            # format
python pre_commit_checks.py       # format + tests
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
- **Classical refresh**: 1st of month at 12 PM UTC — `.github/workflows/refresh-classical-data.yml` runs `scripts/refresh_classical_data.py --dry-run --use-perplexity` to re-fetch the season-based classical + ballet payloads (Austin Symphony, Early Music Austin, La Follia, Austin Chamber Music, Austin Opera, Ballet Austin) and opens a PR with the diff. The PR is **never auto-merged** — a human reviews each refresh before the new `docs/classical_data.json` / `docs/ballet_data.json` ships. Local dry-run: `python scripts/refresh_classical_data.py --dry-run [--use-perplexity] [--venue austinSymphony]`. Requires `PERPLEXITY_API_KEY` (and `ANTHROPIC_API_KEY` for downstream summary generation) in repo secrets.
- **Manual**: Trigger workflows anytime via GitHub Actions

## 📁 Project Structure

```
Culture-Calendar/                   # `main` is SOURCE-ONLY (see Deployment)
├── 🌐 Site source (docs/)
│   ├── index.html                  # Hand-authored single-page app
│   ├── styles.css                  # Responsive design
│   ├── script.js                   # Interactive features
│   ├── config.json                 # Front-end config
│   ├── ABOUT.md                    # About copy
│   ├── data.json                   # Enriched event data (canonical, committed)
│   ├── classical_data.json         # Season JSON for classical/opera venues
│   ├── ballet_data.json            # Season JSON for ballet
│   └── source_update_times.json    # Per-venue last-updated stamps
│       # Generated artifacts (events/, api/, people/, venues/, weekly/,
│       # feeds, sitemap, robots, llms.txt) are NOT tracked in main —
│       # scripts/build_site.py regenerates them for the gh-pages publish.
│
├── 🤖 Automation
│   ├── .github/workflows/
│   │   ├── update-calendar.yml         # Weekly scrape + enrich → main
│   │   ├── daily-calendar-update.yml   # Daily refresh
│   │   ├── refresh-classical-data.yml  # Monthly season-JSON refresh (PR)
│   │   ├── deploy-pages.yml            # Build full site → gh-pages
│   │   └── pr-validation.yml           # Tests + LLM Council on PR diff
│   ├── update_website_data.py          # Scrape + enrich pipeline entry point
│   └── scripts/build_site.py           # Assemble full site into _site/
│
├── 🔧 Core Logic
│   └── src/
│       ├── scraper.py              # MultiVenueScraper orchestrator + dedup
│       ├── scrapers/               # Per-venue BaseScraper subclasses
│       ├── enrichment_layer.py     # LLM classification + field extraction
│       ├── processor.py            # AI ratings/reviews (Perplexity)
│       ├── summary_generator.py    # One-line hooks (Claude)
│       └── calendar_generator.py   # ICS file creation
│
├── 🧪 Quality gates
│   ├── personas/council/           # Cross-family LLM Council judge personas
│   ├── personas/live-site-specs/   # Structural specs for check_live_site.py
│   └── .council/                   # Council manifests + vendored council-judge.sh
│
└── ⚙️ Configuration
    ├── config/master_config.yaml   # Single source of truth (venues, templates,
    │                               #   static_json_scrapers registry)
    ├── preferences.txt             # Personal taste preferences
    ├── literature_preferences.txt  # Classic literature interests
    ├── requirements.txt            # Python dependencies
    ├── .env.example                # Environment template
    └── CLAUDE.md                   # AI assistant instructions
```

## 🏗️ Architecture

**Two-phase, config-driven pipeline.** `config/master_config.yaml` is the single source of truth — event templates (`movie`, `concert`, `book_club`, `opera`, `dance`, `visual_arts`, `other`), per-venue scrape/classification/enrichment policies, and the static-JSON scraper registry.

```
venues (HTML / static season JSON)
    │
    ▼  Phase 1 — src/scrapers/*.py (extend BaseScraper)
    │  src/scraper.py:MultiVenueScraper.scrape_all_venues() — orchestrate + dedup
    │     • HTML scrapers: AFS, Hyperreal, Paramount, book clubs, visual arts
    │     • Static-JSON venues (Symphony, Early Music, La Follia, Chamber Music,
    │       Opera, Ballet) are built in a loop from the `static_json_scrapers:`
    │       registry — one StaticJsonScraper per entry, no per-venue wrapper class
    │
    ▼  Phase 2 (optional per venue) — src/enrichment_layer.py
    │  classify event_category, fill required fields with evidence validation
    │  src/processor.py (Perplexity ratings/reviews) → src/summary_generator.py (Claude hooks)
    │
    ▼  update_website_data.py → writes docs/data.json
    ▼  scripts/build_site.py → assembles full site → published to gh-pages
```

The six classical/opera/ballet venues are NOT scraped per event. They ship as static season JSON (`docs/classical_data.json` + `docs/ballet_data.json`), refreshed monthly by `scripts/refresh_classical_data.py`. The `static_json_scrapers:` block in `master_config.yaml` (read via `ConfigLoader.get_static_json_scrapers()`) defines each one; `src/scraper.py` builds them in a loop, which replaced six near-identical wrapper classes.

## 🚢 Deployment

`main` is **source-only**. The rendered site lives on a separate `gh-pages` branch so `main` does not track the ~900 generated files (`events/`, `api/`, `people/`, `venues/`, `weekly/`, feeds, sitemap, robots, `llms.txt`).

- **`main` tracks**: the hand-authored `docs/` source (`index.html`, `script.js`, `styles.css`, `config.json`, `ABOUT.md`) plus the canonical data/cache JSON (`docs/data.json`, `docs/classical_data.json`, `docs/ballet_data.json`, `docs/source_update_times.json`).
- **`.github/workflows/deploy-pages.yml`** runs on push to `main` (and manual dispatch). It builds the full site with `python scripts/build_site.py --out _site --docs-dir docs`, then publishes `_site/` to `gh-pages` via `peaceiris/actions-gh-pages` (`force_orphan: true`, so `gh-pages` stays a single rolling commit).
- **One-time maintainer step**: after the first successful deploy creates the `gh-pages` branch, set **Settings → Pages → Source → Deploy from a branch → `gh-pages` / (root)**. The public URL is unchanged.

## 🧑‍⚖️ LLM Council quality gate

Quality is enforced by the reusable **`llm-council`** skill — a judge panel with **enforced cross-family diversity**: the maker family (Anthropic) is **excluded from judging**, and every juror is a distinct non-Anthropic family (OpenAI, DeepSeek, Moonshot, z-ai, Google, Xiaomi). The vendored runtime is `.council/llm-council/scripts/council-judge.sh`. The council needs `OPENROUTER_API_KEY` and degrades gracefully (skips, never hard-blocks) when it is absent. See `personas/README.md` for the full layout.

Personas live in `personas/council/*.json` (judge specs, conforming to the llm-council skill schema); manifests in `.council/` pin each persona to a model/family. There are three gates:

1. **Pre-push** (`.githooks/pre-push`) — runs the live-site council (`.council/live-site.json`) against a local server rooted at `docs/`, triggered when an outgoing commit subject contains `[persona-gate]`. Activate per-clone: `git config core.hooksPath .githooks`.
2. **PR validation** (`.github/workflows/pr-validation.yml` → `council-review` job) — runs the council on the PR diff using `.council/culture-calendar.json`. Report-only; degrades gracefully without the secret.
3. **Long-run tasks** — the autonomous-run harness judges each task with `.council/culture-calendar.json`; any FAIL re-queues the task.

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
- **Website not loading**: Confirm GitHub Pages Source is set to `gh-pages` / (root), and that `deploy-pages.yml` ran successfully
- **No calendar data**: Verify GitHub Actions have repository write permissions  
- **API errors**: Ensure `PERPLEXITY_API_KEY` is added to repository secrets
- **Missing events**: a venue's website structure may have changed (check `src/scrapers/`); run `python update_website_data.py --validate`

### GitHub Actions Issues
- **403 Permission Error**: Enable "Read and write permissions" in Settings > Actions
- **Workflow not running**: Check cron schedule and repository activity requirements
- **API rate limiting**: Built-in delays handle this automatically

### Debug Mode
```bash
# Test locally on the current week only
python update_website_data.py --test-week --validate
```

## 🗺️ Roadmap

### 📋 Completed Features ✅
- ✅ **Phase 1**: Austin Film Society integration
- ✅ **Phase 2**: GitHub Pages website with calendar view
- ✅ **Phase 2.1**: Enhanced UI with movie aggregation and markdown rendering
- ✅ **Phase 2.2**: Multi-venue support with Hyperreal Film Club integration
- ✅ **Phase 2.3**: Austin Symphony Orchestra integration with full 2025-2026 season data
- ✅ **Phase 3**: Multi-venue integration
  - ✅ **Paramount Theatre**: Full web scraping and event processing
  - ✅ **Early Music Austin / La Follia / Austin Chamber Music**: Season-based classical events
  - ✅ **Austin Opera / Ballet Austin**: Season-based opera + dance
  - ✅ **Alienated Majesty / First Light / Livra Books**: Dynamic book-club scraping
  - ✅ **NowPlayingAustin**: Visual-arts exhibition listings

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