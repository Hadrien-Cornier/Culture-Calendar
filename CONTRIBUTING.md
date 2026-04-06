# Contributing to Culture Calendar

## Project Purpose

Culture Calendar is an automated pipeline that scrapes Austin cultural events (films, concerts, opera, ballet, book clubs) from venue websites, enriches them with AI-generated ratings and descriptions, and publishes the result to a GitHub Pages site with calendar/ICS export. The scraper runs weekly via GitHub Actions.

## Prerequisites

- Python 3.11+
- git
- API keys: `PERPLEXITY_API_KEY` and `ANTHROPIC_API_KEY`

## Setup

```bash
git clone https://github.com/hadrien-cornier/Culture-Calendar.git
cd Culture-Calendar
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and fill in your API keys
```

## Running the Scraper

```bash
# Full scrape + enrichment (all venues)
python update_website_data.py

# Current week only (faster, good for development)
python update_website_data.py --test-week

# Fail-fast on scraper health check failures
python update_website_data.py --validate

# Force reprocess all events (ignore cache)
python update_website_data.py --force-reprocess
```

## Running Tests

```bash
# Unit tests only (no network calls) — use this for fast iteration
pytest tests/ -m "not live and not integration"

# Full test suite (includes integration tests)
pytest tests/
```

## Code Style

- Format with `black` before committing:
  ```bash
  black src/ tests/ *.py
  ```
- Run the pre-commit checks script:
  ```bash
  python pre_commit_checks.py
  ```
- Use `snake_case` for all field names and function names — this is enforced by the config schema.

## Adding a New Venue

See the 7-step process in [CLAUDE.md](CLAUDE.md) under "Adding a New Venue". In brief: create a scraper subclassing `BaseScraper`, add venue config to `config/master_config.yaml`, register in `src/scrapers/__init__.py` and `src/scraper.py`, write unit tests.
