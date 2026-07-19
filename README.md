# 🎬 Culture Calendar

An automated calendar of Austin cultural events — film, classical music, opera, ballet, book clubs, and visual arts — with AI-written reviews and 1–10 ratings, published as a static website on GitHub Pages.

**Live site → [hadrien-cornier.github.io/Culture-Calendar](https://hadrien-cornier.github.io/Culture-Calendar)**

Every week a GitHub Action scrapes 13 Austin venues, enriches each event with an AI rating and review, and rebuilds the site. No server, no database — just static files.

## How it works

A two-phase, config-driven pipeline. `config/master_config.yaml` is the single source of truth for venues, event templates, and enrichment policy.

```
venues (HTML pages + static season JSON)
   │
   │  Phase 1 — scrape         src/scrapers/*.py  (subclasses of BaseScraper)
   │                           src/scraper.py:MultiVenueScraper  → orchestrate + dedup
   ▼
raw events
   │
   │  Phase 2 — enrich         src/enrichment_layer.py  → classify + fill fields
   │                           src/processor.py         → Perplexity rating + review
   │                           src/summary_generator.py → Claude one-line hook
   ▼
update_website_data.py  →  writes docs/data.json
scripts/build_site.py   →  assembles the full site  →  published to gh-pages
```

Most venues are scraped from their websites. The six classical/opera/ballet venues
(Austin Symphony, Early Music Austin, La Follia, Austin Chamber Music, Austin Opera,
Ballet Austin) are **not** scraped per-event — they ship as static season JSON
(`docs/classical_data.json`, `docs/ballet_data.json`), refreshed monthly by
`scripts/refresh_classical_data.py`. The `static_json_scrapers:` block in
`master_config.yaml` defines each one, and `src/scraper.py` builds them in a loop.

### Venues (13 active)

| Category | Venues |
|---|---|
| 🎬 Film | Austin Film Society, Hyperreal Film Club, Paramount Theatre |
| 🎼 Classical / Opera / Ballet | Austin Symphony, Early Music Austin, La Follia, Austin Chamber Music, Austin Opera, Ballet Austin |
| 📚 Book clubs | Alienated Majesty Books, First Light Austin, Livra Books |
| 🎨 Visual arts | NowPlayingAustin |

## Quick start

### Use the live website

Visit **[hadrien-cornier.github.io/Culture-Calendar](https://hadrien-cornier.github.io/Culture-Calendar)** to browse events, filter by venue / rating / country, switch between list and calendar views, read the AI reviews, and download `.ics` calendar files on demand.

### Run your own instance

1. **Clone and install**
   ```bash
   git clone https://github.com/your-username/Culture-Calendar.git
   cd Culture-Calendar
   pip install -r requirements.txt
   ```

2. **Configure API keys** — copy `.env.example` to `.env` and fill in:
   ```bash
   PERPLEXITY_API_KEY=...   # ratings + reviews (required)
   ANTHROPIC_API_KEY=...    # one-line event summaries (recommended)
   OPENROUTER_API_KEY=...   # LLM Council quality gate (optional)
   ```

3. **Generate the data**
   ```bash
   python update_website_data.py              # full scrape + enrichment
   python update_website_data.py --test-week  # current week only (fast)
   ```

4. **Enable GitHub Pages & Actions** (for the automated site)
   - Settings → Actions → General → enable **Read and write permissions**
   - Add `PERPLEXITY_API_KEY` (and `ANTHROPIC_API_KEY`) to repository secrets
   - After the first deploy creates the `gh-pages` branch, set **Settings → Pages → Source → `gh-pages` / (root)** (see [Deployment](#deployment))

## Commands

```bash
# Data pipeline
python update_website_data.py                    # full scrape + enrich → docs/data.json
python update_website_data.py --test-week        # current week only
python update_website_data.py --force-reprocess  # ignore cache
python update_website_data.py --validate         # fail-fast if a scraper breaks

# Tests
pytest tests/ -m "not live and not integration"  # unit tests (no network)
pytest tests/                                     # everything

# Code quality
black src/ tests/ *.py        # format
python pre_commit_checks.py   # format + tests
```

## Automated updates

GitHub Actions keep the site fresh with no manual work:

- **Weekly** — Saturdays 9 PM UTC: scrape + enrich the upcoming month → `main`, then send the weekly tipsheet email (see below)
- **Monthly** — 1st of month 6 AM UTC: full refresh

### Email newsletter (Buttondown)

The masthead signup form posts to Buttondown, and the Saturday workflow emails next week's top picks to subscribers via `scripts/send_weekly_email.py` (idempotent per ISO week; no-ops cleanly until configured). One-time setup:

1. Create a [Buttondown](https://buttondown.email) account with username `culture-calendar` (or update `distribution.buttondown_endpoint` in `config/master_config.yaml` to match whatever username you pick).
2. Verify your sender address in Buttondown (Settings → Sending). Optionally point the confirmation/unsubscribe redirects at `/subscribed.html` and `/unsubscribed.html`.
3. Add `BUTTONDOWN_API_KEY` (Buttondown → Settings → API) to the GitHub repo secrets (Settings → Secrets and variables → Actions).

Until step 3 is done, the send step prints a skip notice and CI stays green.
- **Classical refresh** — 1st of month 12 PM UTC: `refresh-classical-data.yml` re-fetches the season JSON for the six classical/opera/ballet venues and opens a **PR**. It is never auto-merged — a human reviews each refresh before the new `classical_data.json` / `ballet_data.json` ships.
- **Manual** — any workflow can be triggered on demand from the Actions tab.

## Deployment

`main` is **source-only**. The rendered site lives on a separate `gh-pages` branch, so `main` never tracks the ~900 generated files (`events/`, `api/`, `people/`, `venues/`, `weekly/`, feeds, sitemap, `llms.txt`).

- **`main` tracks** the hand-authored `docs/` source (`index.html`, `script.js`, `styles.css`, `config.json`, `ABOUT.md`) plus the canonical data files (`data.json`, `classical_data.json`, `ballet_data.json`, `source_update_times.json`).
- **`deploy-pages.yml`** runs on push to `main`. It builds the full site with `python scripts/build_site.py --out _site --docs-dir docs`, then publishes `_site/` to `gh-pages` (`force_orphan: true`, so `gh-pages` stays a single rolling commit).

## For AI agents

Culture Calendar publishes machine-readable surfaces as static files — no auth, no rate limits beyond GitHub Pages defaults.

- **[`llms.txt`](https://hadrien-cornier.github.io/Culture-Calendar/llms.txt)** — [llmstxt.org](https://llmstxt.org/)-formatted index of every page and feed. Start here.
- **[`llms-full.txt`](https://hadrien-cornier.github.io/Culture-Calendar/llms-full.txt)** — plain-text dump of the top events, HTML stripped.
- **[`/api/`](https://hadrien-cornier.github.io/Culture-Calendar/api/)** — JSON aggregates: `events.json`, `top-picks.json`, `venues.json`, `people.json`, `categories.json`. Per-event JSON at `/events/<slug>.json`.
- **[`.well-known/ai-agent.json`](https://hadrien-cornier.github.io/Culture-Calendar/.well-known/ai-agent.json)** — agent manifest describing every endpoint. Use as the discovery entry point.
- **Feeds** — `feed.xml` (RSS), `calendar.ics` (all events), `top-picks.ics` (top picks), `sitemap.xml`.
- **Crawler policy** — `robots.txt` explicitly allows GPTBot, ClaudeBot, PerplexityBot, CCBot, Google-Extended, Meta-ExternalAgent, and Amazonbot.

## Rating system

Each event is rated **1–10 by an LLM** (Perplexity) that writes a short review in a
style matched to the medium: French cinéaste critiques for film, classical-criticism
for music, literary criticism for books, art-critic writeups for exhibitions. The
score is parsed from the model's review; events the model can't evaluate fall back to
a neutral 5. Weekday 9am–6pm events are filtered out as inaccessible.

| Range | Meaning |
|---|---|
| 🟢 9–10 | Timeless classics and masterpieces |
| 🟡 7–8 | Strong recommendations with notable merit |
| ⚪ 5–6 | Average |
| ⚫ 1–4 | Lower priority / niche appeal |

Example:

```
⭐ 9/10 — NIGHT OF THE LIVING DEAD

A study in fear, isolation, and the breakdown of societal norms, following
seven people trapped in a farmhouse besieged by reanimated corpses. A seminal
work of horror cinema that rewards contemplation.

Director: George A. Romero
Screenings: Jun 18 · 8:45 PM   ·   Jun 23 · 7:00 PM
```

## LLM Council quality gate

Output quality is enforced by the reusable **`llm-council`** skill — a judge panel with **enforced cross-family diversity**: the maker family (Anthropic) is excluded from judging, and every juror is a distinct non-Anthropic family (OpenAI, DeepSeek, Moonshot, z-ai, Google, Xiaomi). It needs `OPENROUTER_API_KEY` and degrades gracefully — it skips, never hard-blocks, when the key is absent.

Judge personas live in `personas/council/*.json`; manifests in `.council/` pin each persona to a model. The council runs as a report-only gate on PR diffs (`pr-validation.yml`) and as a pre-push hook for live-site checks. See `personas/README.md` for the full layout.

## Project structure

```
Culture-Calendar/                  # main is SOURCE-ONLY (see Deployment)
├── docs/                          # site source + canonical data
│   ├── index.html / script.js / styles.css / config.json
│   ├── data.json                  # enriched event data (committed)
│   ├── classical_data.json        # season JSON — classical/opera venues
│   └── ballet_data.json           # season JSON — ballet
├── src/
│   ├── scraper.py                 # MultiVenueScraper orchestrator + dedup
│   ├── scrapers/                  # per-venue BaseScraper subclasses
│   ├── enrichment_layer.py        # LLM classification + field extraction
│   ├── processor.py               # AI ratings/reviews (Perplexity)
│   ├── summary_generator.py       # one-line hooks (Claude)
│   └── calendar_generator.py      # ICS file creation
├── scripts/
│   ├── build_site.py              # assemble full site → _site/
│   └── refresh_classical_data.py  # monthly season-JSON refresh
├── config/master_config.yaml      # single source of truth
├── personas/ + .council/          # LLM Council judge personas + manifests
├── .github/workflows/             # update, deploy, PR-validation pipelines
└── update_website_data.py         # scrape + enrich pipeline entry point
```

## Troubleshooting

- **Website not loading** — confirm Pages Source is `gh-pages` / (root) and that `deploy-pages.yml` ran successfully.
- **No calendar data** — verify GitHub Actions have repository write permissions (Settings → Actions → General).
- **API errors** — ensure `PERPLEXITY_API_KEY` is in repository secrets.
- **Missing events** — a venue's site structure may have changed; check `src/scrapers/` and run `python update_website_data.py --validate`.

### Known limitations

- Scrapers don't all run in parallel — pyppeteer raises `signal only works in main thread of the main interpreter` under concurrency.
- Ratings cluster and could be spread out / personalized more.

## Roadmap

**Done:** Austin Film Society, Hyperreal, Paramount, the six classical/opera/ballet
season venues, the three book clubs, and NowPlayingAustin visual arts — all live with
the GitHub Pages site (list + calendar views, AI reviews, ICS export).

**Next:** more venues (Alamo Drafthouse, Violet Crown, The Long Center, BookPeople,
Austin Public Library, and others — see the [venue wishlist](#venue-wishlist) below),
direct Google Calendar integration, better recommendations, and a possible PWA.

## Venue wishlist

Candidate venues not yet scraped. `scripts/build_wishlist.py` renders these into
`docs/wishlist.html`; keep the `- [ ] Name (category) — why` format so the parser
picks them up.

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

<details>
<summary>Auto-prospected additions (2026-04-19) — from <code>scripts/prospect_venues.py</code>; verify URLs before onboarding</summary>

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

</details>
<!-- venue-wishlist:end -->

## Contributing

Fork, branch (`git checkout -b feature/your-feature`), commit, push, and open a PR.

## License

MIT — see [LICENSE](LICENSE).

## Acknowledgments

Thanks to the Austin venues whose programming makes this project worthwhile —
[Austin Film Society](https://www.austinfilm.org/), [Hyperreal Film Club](https://hyperrealfilm.club/),
[Paramount Theatre](https://www.austinparamount.com/), [Austin Symphony](https://austinsymphony.org/),
[Texas Early Music Project](https://www.early-music.org/), [La Follia Austin](https://www.tickettailor.com/events/lafolliaaustin/),
[Alienated Majesty Books](https://www.alienatedmajestybooks.com/), and [First Light Austin](https://www.firstlightaustin.com/) —
and to [Perplexity AI](https://www.perplexity.ai/) for the cultural analysis. Built for Austin culture lovers. ❤️
