# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overnight Loop Protocol (active through 2026-04-15)

If you are running inside `scripts/overnight_loop.sh` on branch `fix/calendar-oracle`:

1. **Read CHANGELOG.md.** Pick the first `- [ ]` line under the "Calendar fix" section. That is your subtask. Do **not** pick a later one — the queue is ordered by dependency.
2. **Do that subtask, nothing else.** No refactors, no drive-by cleanups. If you spot a separate bug, add a new `- [ ]` line instead of fixing it inline.
3. **Verify before declaring done:**
   ```
   .venv/bin/python -m pytest -q
   .venv/bin/python scripts/verify_calendar.py --offline
   ```
   Both must print success. If either fails, keep iterating on the same subtask.
4. **Commit with the required identity and push:**
   ```
   git -c user.name=Hadrien-Cornier -c user.email=hadrien.cornier@gmail.com commit -m "feat(calendar): <subtask-id> <what>"
   git push origin fix/calendar-oracle
   ```
   Never touch `main`. Never `--no-verify`. Never force-push. Never `git reset --hard` — the only destructive move allowed is reverting a single just-made commit via `git revert HEAD --no-edit` if its tests regressed.
5. **Tick the box in CHANGELOG.md** before committing: replace `- [ ]` with `- [x] YYYY-MM-DD HH:MM`.
6. **If blocked**, append `BLOCKED: <subtask-id>: <why>` under the queue and move on. Don't thrash.
7. **Exit criterion:** `scripts/verify_calendar.py --live` prints PASS two iterations in a row. Until then, keep picking subtasks.

## Project Overview

Culture Calendar is an automated system that scrapes Austin cultural events (films, concerts, book clubs, opera, ballet) from multiple venues, enriches them with AI-powered analysis and ratings, and publishes them to a GitHub Pages website with calendar/ICS export functionality.

**Current Venues**: Austin Film Society, Hyperreal Film Club, Austin Symphony, Early Music Austin, La Follia, Austin Opera, Ballet Austin, Alienated Majesty Books, First Light Austin, Arts on Alexander

## Development Commands

### Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Setup environment
cp .env.example .env
# Add PERPLEXITY_API_KEY and ANTHROPIC_API_KEY to .env
```

### Running the System
```bash
# Full scrape and update (all venues, all events)
python update_website_data.py

# Test mode (current week only)
python update_website_data.py --test-week

# Force reprocess all events (ignore cache)
python update_website_data.py --force-reprocess

# Enable smart validation (fail-fast on scraper failures)
python update_website_data.py --validate
```

### Testing
```bash
# Run all tests
pytest tests/

# Run unit tests only (no live scraping)
pytest tests/ -m "not live and not integration"

# Run specific scraper tests
pytest tests/test_afs_scraper_unit.py -v
pytest tests/test_enrichment_layer.py -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html
```

### Code Quality
```bash
# Format code with Black
black src/ tests/ *.py

# Pre-commit checks (formatting + tests)
python pre_commit_checks.py

# Auto-fix only
python pre_commit_checks.py --fix-only
```

## Architecture

### Two-Phase Scraping Pipeline

**Phase One: Normalization**
- Each venue scraper extends `BaseScraper` (src/base_scraper.py:20)
- Scraper-specific logic extracts raw event data from websites
- Events normalized to config-driven schema (snake_case, YYYY-MM-DD dates, HH:mm times)
- LLM extraction used for complex/dynamic websites (book clubs, some film venues)

**Phase Two: Enrichment** (Optional per venue)
- Classification: LLM determines event_category (movie/concert/book_club/opera/dance/other)
- Field Extraction: LLM fills missing required fields with evidence validation
- Only proceeds if classification enabled in config/master_config.yaml
- See src/enrichment_layer.py:40 for orchestration logic

### Key Components

**Configuration System** (config/master_config.yaml)
- Centralized schema definitions via templates (movie, concert, book_club, opera, dance, other)
- Per-venue policies: scraping frequency, classification enabled/disabled, assumed categories
- Field requirements, validation rules, date/time formats
- Loaded via ConfigLoader (src/config_loader.py)

**Scraper Architecture**
- `BaseScraper` (src/base_scraper.py): Abstract base with LLM service, session management, format_event(), validate_event()
- Individual scrapers in src/scrapers/: Each implements scrape_events() method
- `MultiVenueScraper` (src/scraper.py:28): Orchestrates all venue scrapers, manages duplicate detection
- LLM-powered extraction for dynamic content (Hyperreal, Alienated Majesty, First Light)
- Static JSON loading for season-based venues (Symphony, Opera, Ballet)

**Event Processing Pipeline**
1. Scraping: MultiVenueScraper.scrape_all_venues() � normalized events
2. Validation (optional): EventValidationService checks scraper health, fail-fast on widespread failures
3. Enrichment: EventProcessor.process_events() � AI ratings, descriptions, one-liners
4. Website Generation: update_website_data.py � docs/data.json with grouped events

**AI Integration**
- `LLMService` (src/llm_service.py): Abstracts Perplexity (Sonar) and Anthropic (Claude) APIs
- `EventProcessor` (src/processor.py:19): Generates AI ratings/reviews using Perplexity
- `EnrichmentLayer` (src/enrichment_layer.py:17): Classification and field extraction with evidence validation
- `SummaryGenerator` (src/summary_generator.py): Creates one-line summaries using Claude

### Event Schema

All events follow master_config.yaml templates with these common fields:
- **dates/times**: Arrays with pairwise_equal_length zip rule (YYYY-MM-DD, HH:mm)
- **occurrences**: Generated array of {date, time, url, venue} objects for each showing
- **event_category**: movie | concert | book_club | opera | dance | other
- **rating**: 0-10 AI-generated score based on artistic merit
- **description**: AI-generated analysis (French cin�aste style for films, distinguished criticism for music)
- **one_liner_summary**: Claude-generated concise hook

Type-specific fields defined in config templates (e.g., movies have director/country/language, concerts have composers/works).

## Common Development Tasks

### Adding a New Venue

1. Create scraper class in src/scrapers/new_venue_scraper.py extending BaseScraper
2. Implement scrape_events() method returning normalized events
3. Add venue config to config/master_config.yaml under venues:
4. Register in src/scrapers/__init__.py
5. Add to MultiVenueScraper.__init__() and scrape_all_venues() in src/scraper.py
6. Create unit tests in tests/test_new_venue_scraper_unit.py
7. Test with: `python update_website_data.py --test-week`

### Debugging Scraper Failures

1. Check validation report if using --validate flag
2. Run individual scraper in test mode
3. Verify website structure hasn't changed (common failure cause)
4. Check LLM extraction prompts if using smart extraction
5. Review enrichment telemetry: classifications, abstentions, fields_accepted/rejected

### Modifying Event Schema

1. Update template in config/master_config.yaml (add fields, change requirements)
2. Update scraper to populate new fields
3. Update enrichment prompts if field requires LLM extraction
4. Modify update_website_data.py:build_event_from_template() if special handling needed
5. Update tests with new schema

## Known Issues

1. **Pyppeteer threading**: Cannot run all scrapers in parallel due to "signal only works in main thread" error with pyppeteer
2. **Read review button**: Can crash site (mentioned in README problems section)
3. **Rating distribution**: Ratings not very customized/spread out (needs preference tuning)

## Data Flow

1. **Scraping**: MultiVenueScraper � raw events (Phase One normalization)
2. **Validation**: EventValidationService � health checks, fail-fast on systematic failures
3. **Enrichment**: EventProcessor � AI ratings + descriptions
4. **Summary Generation**: SummaryGenerator � one-line hooks
5. **Website Data**: update_website_data.py � docs/data.json (grouped by title for movies, unique for others)
6. **ICS Export**: Calendar files generated on-demand via website download button
7. **GitHub Pages**: docs/ folder served at hadrien-cornier.github.io/Culture-Calendar

## Testing Strategy

- **Unit tests**: Mock scrapers, test parsing logic without network calls
- **Integration tests**: Test full pipeline with cached responses
- **Live tests**: Marked with @pytest.mark.live, test actual website scraping
- Test data stored in tests/{Venue}_test_data/ directories
- Validation service has comprehensive integration tests (tests/test_validation_integration.py)

## Configuration Notes

- All scrapers use master_config.yaml as single source of truth
- Date inference handled dynamically at runtime for book clubs (current year vs next year logic)
- Venue policies control classification/enrichment (AFS has classification disabled, assumed movie category)
- Field defaults defined at config level to ensure consistency
- snake_case enforced across all field names per config style rules

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **Culture-Calendar** (1511 symbols, 3370 relationships, 119 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npm run analyze` (or `./node_modules/.bin/gitnexus analyze`) in terminal first. **Do not use `npx gitnexus`** — it fails on Node v24 due to a tree-sitter-swift rebuild bug.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## When Debugging

1. `gitnexus_query({query: "<error or symptom>"})` — find execution flows related to the issue
2. `gitnexus_context({name: "<suspect function>"})` — see all callers, callees, and process participation
3. `READ gitnexus://repo/Culture-Calendar/process/{processName}` — trace the full execution flow step by step
4. For regressions: `gitnexus_detect_changes({scope: "compare", base_ref: "main"})` — see what your branch changed

## When Refactoring

- **Renaming**: MUST use `gitnexus_rename({symbol_name: "old", new_name: "new", dry_run: true})` first. Review the preview — graph edits are safe, text_search edits need manual review. Then run with `dry_run: false`.
- **Extracting/Splitting**: MUST run `gitnexus_context({name: "target"})` to see all incoming/outgoing refs, then `gitnexus_impact({target: "target", direction: "upstream"})` to find all external callers before moving code.
- After any refactor: run `gitnexus_detect_changes({scope: "all"})` to verify only expected files changed.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Tools Quick Reference

| Tool | When to use | Command |
|------|-------------|---------|
| `query` | Find code by concept | `gitnexus_query({query: "auth validation"})` |
| `context` | 360-degree view of one symbol | `gitnexus_context({name: "validateUser"})` |
| `impact` | Blast radius before editing | `gitnexus_impact({target: "X", direction: "upstream"})` |
| `detect_changes` | Pre-commit scope check | `gitnexus_detect_changes({scope: "staged"})` |
| `rename` | Safe multi-file rename | `gitnexus_rename({symbol_name: "old", new_name: "new", dry_run: true})` |
| `cypher` | Custom graph queries | `gitnexus_cypher({query: "MATCH ..."})` |

## Impact Risk Levels

| Depth | Meaning | Action |
|-------|---------|--------|
| d=1 | WILL BREAK — direct callers/importers | MUST update these |
| d=2 | LIKELY AFFECTED — indirect deps | Should test |
| d=3 | MAY NEED TESTING — transitive | Test if critical path |

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/Culture-Calendar/context` | Codebase overview, check index freshness |
| `gitnexus://repo/Culture-Calendar/clusters` | All functional areas |
| `gitnexus://repo/Culture-Calendar/processes` | All execution flows |
| `gitnexus://repo/Culture-Calendar/process/{name}` | Step-by-step execution trace |

## Self-Check Before Finishing

Before completing any code modification task, verify:
1. `gitnexus_impact` was run for all modified symbols
2. No HIGH/CRITICAL risk warnings were ignored
3. `gitnexus_detect_changes()` confirms changes match expected scope
4. All d=1 (WILL BREAK) dependents were updated

## Keeping the Index Fresh

After committing code changes, the GitNexus index becomes stale. Re-run analyze to update it:

```bash
npm run analyze
```

If the index previously included embeddings, preserve them by adding `--embeddings`:

```bash
./node_modules/.bin/gitnexus analyze --embeddings
```

To check whether embeddings exist, inspect `.gitnexus/meta.json` — the `stats.embeddings` field shows the count (0 means no embeddings). **Running analyze without `--embeddings` will delete any previously generated embeddings.**

> Claude Code users: A PostToolUse hook handles this automatically after `git commit` and `git merge`.

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->

<!-- BEGIN OVERNIGHT-PLAN: 2026-04-18 -->
## Overnight run — 2026-04-18

> **AUTONOMOUS RUN — do not edit while running.**
> Owner: HCornier · Branch: `overnight/2026-04-18` · Deadline: 2026-04-19T12:00:00Z (safety cap; open-ended)
> Runner: `~/.claude/skills/overnight-plan/scripts/overnight-runner.sh` via `nohup`. Queue: `.overnight/queue.tsv`.

### Goal

Five fixes on the promoted v11 site:
1. **Rating "/10" clarity** — bare integers on badges gain a scale suffix + aria-label.
2. **Incomplete reviews** (Nish Kumar + Paper Cuts) — add description-level refusal filter in `src/processor.py`; classify Paper Cuts as a pop-up bookshop with factual pre-filled text; harden Paramount scraper against sparse metadata.
3. **Duplicate "Opera" in tags** — case-insensitive dedup in the category chips + subtitle.
4. **About section** — collapsible methodology at page bottom.
5. **Read-aloud via Web Speech API** — client-side TTS button on every expanded review. Cross-browser targets: iPhone Safari, iOS DuckDuckGo, Android Chrome, Android DuckDuckGo, mobile Firefox, desktop Chrome/Safari/Firefox. No generated audio files, no repo growth.

### Definition of done

- `.venv/bin/python -m pytest -q` green
- Rating badge shows "X / 10" with aria-label "rated X out of 10"
- No duplicate category chip or subtitle tag; case-insensitive dedup in JS
- `is_refusal_response(e.description)` is False for every event in `docs/data.json`
- Paper Cuts events have `type != "book_club"` and factual pre-filled descriptions
- Paramount scraper skips (or placeholder-fills) events with only a bare title
- `docs/ABOUT.md` exists and the About section is visible in `docs/index.html`
- `docs/script.js` calls `window.speechSynthesis.speak()` and listens for `voiceschanged`
- `STATUS-2026-04-18.md` written with morning checklist

### Hard constraints

- Branch: `overnight/2026-04-18` only. Never touch `main` / `master`. Never `git reset --hard`, `git push --force`, or rewrite history. Runner does **NOT** push.
- No new paid API deps. Web Speech API is browser-native, free, client-side only.
- No new Python deps. If a task thinks it needs one → write BLOCKED with reason `needs-dep: <name>`.
- No generated audio files committed. TTS runs in the browser; no MP3s in the repo, no GHA changes needed.
- No interactive prompts. No `--no-verify` on commits.
- Git identity: every commit via `git -c user.name=Hadrien-Cornier -c user.email=hadrien.cornier@gmail.com commit -m '...'`. Never mutate `~/.gitconfig`.
- Never commit `.env`, `cache/llm_cache.json`, `.agents/`, `skills-lock.json`. `.overnight/` is gitignored; do not `git add` it.
- Scope fence: `src/`, `scripts/`, `docs/`, `tests/`, `update_website_data.py`, `config/master_config.yaml`, `CLAUDE.md`, `CHANGELOG.md`, `STATUS-2026-04-18.md`.
- GitNexus impact analysis MANDATORY before editing `src/processor.py`, `src/scrapers/alienated_majesty_scraper.py`, `src/scrapers/paramount_scraper.py`.

### Validation oracle (run before every commit)

```
.venv/bin/python -m pytest -q
```

Pytest must exit 0. The task's own `validate` command (from queue.tsv) is also required.

**Do NOT run `verify_calendar.py --offline` as a per-task oracle** — its 22 checks include some that pre-exist red and would block unrelated tasks. Only T6.1 runs it.

If the per-task oracle fails twice in a row, write BLOCKED and rotate.

### Commit cadence

One commit per DONE task. Message format: `<type>(task-<ID>): <TITLE>` (feat/fix/docs/chore/refactor/test). Stage only files in the task's `files` column; never `git add -A`.

### Changelog entry per task

After each DONE commit, append one entry to the fenced overnight block in `CHANGELOG.md`:

```
### task-<ID> — DONE — <ISO timestamp>
- commit: <sha>
- files: <comma-separated>
- validation: green
```

### Stop conditions

- All queue tasks DONE → `RUN_COMPLETE`
- Deadline (2026-04-19T12:00:00Z) reached → `RUN_HALTED: deadline`
- 3 consecutive BLOCKED tasks → `RUN_HALTED: consecutive-blockers`
- `STATUS-2026-04-18.md` contains line `HALT` (manual override) → `RUN_HALTED: manual`

### Blocker protocol

A task blocks when validation fails twice. Append to CHANGELOG under today's fenced block:
```
BLOCKED: task-<ID>: <one-line reason + failing-command head/tail>
```
Then write `.overnight/task-result.json` with `{"status": "BLOCKED", "task_id": "task-<ID>", "reason": "<one line>"}`. The runner rotates.

### Task queue (human view; source of truth is `.overnight/queue.tsv`)

- **T1.2** — Rating badge `/10` suffix + aria-label (picks + listings)
- **T1.3** — Case-insensitive category dedup (`uniqueCategories`, subtitle)
- **T2.1** — Description-level refusal filter in `src/processor.py` + test
- **T2.2** — Classify Paper Cuts as pop-up bookshop (type=other, pre-filled)
- **T2.3** — Paramount scraper: skip/placeholder sparse-metadata events
- **T2.4** — Clean existing refusal-shaped descriptions in `docs/data.json`
- **T3.1** — Methodology `docs/ABOUT.md` + collapsible `.about-section`
- **T4.1** — Read-aloud button via Web Speech API (cross-browser)
- **T6.1** — Final gate
- **T6.2** — `STATUS-2026-04-18.md` handoff

<!-- END OVERNIGHT-PLAN: 2026-04-18 -->

<!-- BEGIN OVERNIGHT-PLAN: 2026-04-19 -->
## Overnight run — 2026-04-19

> **AUTONOMOUS RUN — do not edit while running.**
> Owner: HCornier · Branch: `overnight/2026-04-19` · Deadline: 2026-04-19T03:38:09Z (24h safety cap; user requested open-ended)
> Runner: `~/.claude/skills/overnight-plan/scripts/overnight-runner.sh` via `nohup`. Queue: `.overnight/queue.tsv`. Date tag passed to runner: `2026-04-19`.

### Goal

Three threads bundled as one batch:

**Primary (must ship):** A `visual_arts` event category lands in the schema, a NowPlayingAustin visual-arts scraper feeds events into `docs/data.json`, an art-critic AI rating branch runs in `src/processor.py`, and tests cover all of it.

**Secondary (best-effort):** Audit Alienated Majesty for artist-talk events and extend its scraper. Add a Libra Books scraper if T0.1 finds a public events page; if not, T2.2 self-blocks and the run continues.

**Tertiary (best-effort):** 10-variant filter-bar redesign under `docs/variants/v12{a..j}/`. Each variant scored by `critique` (40%) + `layout` (30%) + `audit` (20%) + `polish` (10%). Winner promoted to live `docs/`.

**Quaternary (last-hour polish):** Coverage matrix in `docs/COVERAGE.md` proving every event category has ≥1 well-formed event in `docs/data.json`.

### Hard constraints

- Branch `overnight/2026-04-19` only. Never touch `main`. Never `git reset --hard`, `git push --force`, or rewrite history. Runner does NOT push.
- No new Python deps (`pip install` forbidden). If a task thinks it needs one → BLOCKED with reason `needs-dep: <name>`.
- No new paid API deps. LLM calls reuse Perplexity (Sonar) + Anthropic from `.env`.
- Web Speech API stays browser-native — no audio files committed.
- No interactive prompts. No `--no-verify`.
- Git identity: every commit via `git -c user.name=Hadrien-Cornier -c user.email=hadrien.cornier@gmail.com commit -m '...'`. Never mutate `~/.gitconfig`.
- Never commit `.env`, `cache/llm_cache.json`, `.agents/`, `skills-lock.json`. `.overnight/` stays gitignored.
- Scope fence: `src/`, `scripts/`, `docs/`, `tests/`, `update_website_data.py`, `config/master_config.yaml`, `CLAUDE.md`, `CHANGELOG.md`, `STATUS-2026-04-19.md`.
- GitNexus impact analysis MANDATORY before editing `src/processor.py`, `src/scraper.py`, `src/scrapers/alienated_majesty_scraper.py`, `update_website_data.py`.
- **Filter-redesign scope fence:** T3.x writes only under `docs/variants/v12<x>/` until T3.4, which promotes the winner to `docs/index.html` / `script.js` / `styles.css`.

### Validation oracle (run before every commit)

```
.venv/bin/python -m pytest -q
```

Pytest must exit 0. Each task's per-task `validate` command (from queue.tsv) is also required.

**Do NOT run `scripts/verify_calendar.py --offline` as a per-task oracle** — same reasoning as 2026-04-18: pre-existing red items would block unrelated tasks. Only T5.1 runs it, and only as a delta-vs-main check.

### Commit cadence

One commit per DONE task. Message format: `<type>(task-<ID>): <TITLE>` (feat / fix / docs / chore / refactor / test). Stage only files in the task's `files` column; never `git add -A`. Research-only tasks (T0.1, T0.2, T3.1, T3.3, T5.1) write to gitignored `.overnight/` — they SKIP steps 4 (commit) and 5 (CHANGELOG) of the contract and write `task-result.json` with status=DONE directly.

### Changelog entry per task

After each DONE commit (skip for research-only tasks), append one entry to the fenced overnight block in `CHANGELOG.md`:

```
### task-<ID> — DONE — <ISO timestamp>
- commit: <sha>
- files: <comma-separated>
- validation: green
```

### Stop conditions

- All queue tasks DONE → `RUN_COMPLETE`
- Deadline reached (2026-04-19T03:38:09Z) → `RUN_HALTED: deadline`
- 3 consecutive BLOCKED tasks → `RUN_HALTED: consecutive-blockers`
- `STATUS.md` (not date-tagged — runner only watches this exact file) contains line `HALT` → `RUN_HALTED: manual`

### Task queue (human view; source of truth is `.overnight/queue.tsv`)

**Phase 0 — Research (no commits)**
- **T0.1** — Find Libra Books events page; write `.overnight/libra-resolution.md` with `url:` or `BLOCKED:` verdict
- **T0.2** — Audit Alienated Majesty events for artist-talk signals → `.overnight/am-artist-events.md`

**Phase 1 — visual_arts category (core goal)**
- **T1.1** — Add `visual_arts` to `ontology.labels`
- **T1.2** — Add `visual_arts` template (model on `concert`)
- **T1.3** — Build `now_playing_austin_visual_arts_scraper.py`
- **T1.4** — Register scraper in `__init__.py` + `MultiVenueScraper`
- **T1.5** — Snapshot fixtures + unit tests for the scraper
- **T1.6** — Add `_get_visual_arts_rating()` branch in `EventProcessor`
- **T1.7** — End-to-end smoke: pipeline emits ≥1 visual_arts event into data.json
- **T1.8** — Refusal-guard sweep on visual_arts entries

**Phase 2 — Bookstore artist-talks (secondary)**
- **T2.1** — Extend Alienated Majesty scraper for artist-talks
- **T2.2** — Build Libra Books scraper (auto-blocks if T0.1 BLOCKED)

**Phase 3 — Filter redesign (tertiary)**
- **T3.1** — Variant spec → `.overnight/filter-redesign-spec.md`
- **T3.2** — Generate 10 variants under `docs/variants/v12{a..j}/`
- **T3.3** — Score variants via critique+layout+audit+polish skills
- **T3.4** — Promote winner to `docs/index.html` / `script.js` / `styles.css`
- **T3.5** — Filter smoke test

**Phase 4 — Coverage (quaternary)**
- **T4.1** — `scripts/check_event_coverage.py` covers every event_category
- **T4.2** — `docs/COVERAGE.md` per-category counts table

**Phase 5 — Final gate**
- **T5.1** — Full pytest + coverage + verify_calendar.py delta check
- **T5.2** — `STATUS-2026-04-19.md` handoff

<!-- END OVERNIGHT-PLAN: 2026-04-19 -->
