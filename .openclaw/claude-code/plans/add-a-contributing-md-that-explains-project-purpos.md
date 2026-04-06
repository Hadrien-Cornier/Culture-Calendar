# Plan: Add CONTRIBUTING.md

## Context

The Culture-Calendar repo has a detailed README.md and CLAUDE.md but no contributor guide. A concise CONTRIBUTING.md will help new contributors get set up quickly without duplicating the README or CLAUDE.md content.

## Preconditions

- No existing `CONTRIBUTING.md` (confirmed).
- Key references already in the repo: `README.md`, `CLAUDE.md`, `requirements.txt`, `.env.example`, `pre_commit_checks.py`.
- Python 3.11+ required (runtime is 3.12.3).
- Tests use `pytest`; formatting uses `black`.

## Step 1: Create `CONTRIBUTING.md` at repo root

**File**: `/root/Culture-Calendar/CONTRIBUTING.md`

Create a single new file with these sections (concise, no fluff):

1. **Project Purpose** — 2-3 sentences: automated scraper + AI enrichment pipeline for Austin cultural events, published to GitHub Pages.
2. **Prerequisites** — Python 3.11+, git, API keys (PERPLEXITY_API_KEY, ANTHROPIC_API_KEY).
3. **Setup** — Clone, create venv (`python3 -m venv .venv && source .venv/bin/activate`), `pip install -r requirements.txt`, `cp .env.example .env` and fill in keys.
4. **Running the Scraper** — `python update_website_data.py` (full), `--test-week` (current week only), `--validate` (fail-fast checks).
5. **Running Tests** — `pytest tests/ -m "not live and not integration"` (unit), `pytest tests/` (all).
6. **Code Style** — Format with `black src/ tests/ *.py`. Run `python pre_commit_checks.py` before committing. snake_case everywhere per project convention.
7. **Adding a New Venue** — Brief pointer to the 7-step process already documented in CLAUDE.md.

No duplicate content from README (no feature lists, no screenshots, no live site links).

## Affected Files

| File | Action |
|------|--------|
| `CONTRIBUTING.md` | Create (new) |

## Commit

```
Add CONTRIBUTING.md with setup, usage, and code style guide

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
```

## Verification

1. Confirm file renders correctly: `cat CONTRIBUTING.md` — check markdown structure.
2. Verify all referenced commands work: `python update_website_data.py --help`, `pytest --co -q tests/`, `black --check src/`.
3. Ensure no duplication with README.md or CLAUDE.md content.
