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

This project is indexed by GitNexus as **Culture-Calendar** (781 symbols, 1929 relationships, 63 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

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

<!-- BEGIN OVERNIGHT-PLAN: 2026-04-15 -->
## Overnight run — 2026-04-15

> **AUTONOMOUS RUN — do not edit while running.**
> Owner: HCornier · Branch: `overnight/2026-04-15` · Deadline: 2026-04-16T12:00:00 (safety cap; open-ended per user)
> Runner: `~/.claude/skills/overnight-plan/scripts/overnight-runner.sh` via `nohup`. Queue: `.overnight/queue.tsv`.

### Goal

Three deliverables in one branch:
1. Fix the missing-event bug: THE STRANGER (L'ETRANGER) on April 19 @ 3:15 PM (and its 5 other screenings) must render correctly. Generalize: every event's `dates[]` must equal the set of `screenings[].date`.
2. Kill AI-smell in reviews: add a style rubric + banned-phrase list to every LLM prompt; rewrite cached reviews that match the banned list.
3. Produce 10 design variants under `docs/variants/v{1..10}/` with a gallery at `docs/variants/index.html`, each with an impeccable (or axe-core fallback) audit.

### Definition of done

- `.venv/bin/python -m pytest -q` green.
- `.venv/bin/python scripts/verify_calendar.py --offline` PASS.
- `.venv/bin/python scripts/check_ai_smell.py docs/data.json` exits 0.
- THE STRANGER has `dates == [2026-04-17, 18, 19, 24, 26, 27]` in `docs/data.json`.
- All 10 `docs/variants/v{N}/` load without JS errors, read `../../data.json`, render >= 200 events, pass `scripts/check_variant.mjs`, have an `audit.md`.
- `STATUS.md` written with disposition, commit shas, blockers, morning checklist.

### Hard constraints

- Branch: `overnight/2026-04-15` only. Never touch `main` / `master` / `trunk`. Never `git reset --hard`, `git push --force`, or rewrite history. Runner does **NOT** push; user reviews and merges manually.
- No new dependencies: no `pip install`, `npm install`, `cargo add`, `go get`. If you think you need one, write BLOCKED with reason `needs-dep: <name>`.
- No interactive prompts. No `--no-verify` on commits.
- Git identity: every commit via `git -c user.name=Hadrien-Cornier -c user.email=hadrien.cornier@gmail.com commit -m '...'`. Never mutate `~/.gitconfig` or `.git/config`.
- Never commit `.env`, `cache/`, or anything matching `*secret*`. `.overnight/` is gitignored; do not `git add` it.
- Scope fence: `src/`, `scripts/`, `tests/`, `docs/`, `update_website_data.py`, `config/master_config.yaml`, `CLAUDE.md`, `CHANGELOG.md`, `STATUS.md`. Nothing else.

### Validation oracle (run before every commit)

```
.venv/bin/python -m pytest -q
.venv/bin/python scripts/verify_calendar.py --offline
```

Both must exit 0. If oracle fails twice in a row for the same task, write BLOCKED and rotate.

### Commit cadence

One commit per DONE task. Message format: `<type>(task-<ID>): <TITLE>` where type is feat/fix/docs/chore/refactor/test. Stage only files in the task's `files` column; never `git add -A`.

### Changelog entry per task

After each DONE commit, append one line to the fenced overnight block in `CHANGELOG.md`:

```
### task-<ID> — DONE — <ISO timestamp>
- commit: <sha>
- files: <comma-separated>
- validation: green
```

### Stop conditions

- All queue tasks DONE → `RUN_COMPLETE`
- Deadline reached → `RUN_HALTED: deadline`
- 3 consecutive BLOCKED tasks → `RUN_HALTED: consecutive-blockers`
- `STATUS.md` contains line `HALT` (manual override) → `RUN_HALTED: manual`

### Blocker protocol

A task blocks when validation fails twice. Append to CHANGELOG under today's fenced block:
```
BLOCKED: task-<ID>: <one-line reason + failing-command head/tail>
```
Then write `.overnight/task-result.json` with `{"status": "BLOCKED", "task_id": "task-<ID>", "reason": "<one line>"}`. The runner rotates to the next eligible task.

### Task queue

Source of truth: `.overnight/queue.tsv`. Human view below:

- **T0.2** — Bootstrap `docs/variants/_shared/reset.css`
- **T0.3** — Attempt install pbakaus/impeccable; record outcome in `docs/variants/PLUGIN_STATUS.md`
- **T1.1** — Regression test pinning THE STRANGER 6-date coverage (committed RED)
- **T1.2** — Fix `update_website_data.py` to hoist `dates` from `screenings`
- **T1.3** — Frontend audit: migrate remaining `.date`/`.dates[0]` readers to `screenings[]`
- **T1.4** — Regen `docs/data.json` offline; verify THE STRANGER
- **T2.1** — Add `_style_rubric()` helper to `src/processor.py`
- **T2.2** — Wire rubric into all 9 prompts in `src/processor.py`
- **T2.3** — Replace AI-smell examples + wire rubric in `src/summary_generator.py`
- **T2.4** — Write `scripts/check_ai_smell.py` linter
- **T2.5** — Write `scripts/regen_smelly_reviews.py` cache invalidator
- **T2.6** — Run regen for smelly entries; verify clean
- **T2.7** — Rerun `verify_calendar.py --offline`
- **T3.1..T3.10** — Generate one design variant each (see queue.tsv for brief)
- **T3.11** — Gallery `docs/variants/index.html`
- **T3.12** — Audit every variant (impeccable or axe-core)
- **T4.1** — Final gate: pytest + verify_calendar.py
- **T4.2** — Write STATUS.md handoff

<!-- END OVERNIGHT-PLAN: 2026-04-15 -->

<!-- BEGIN OVERNIGHT-PLAN: 2026-04-16 -->
## Overnight run — 2026-04-16

> **AUTONOMOUS RUN — do not edit while running.**
> Owner: HCornier · Branch: `overnight/2026-04-16` · Deadline: 2026-04-17T12:00:00Z (safety cap; open-ended per user)
> Runner: `~/.claude/skills/overnight-plan/scripts/overnight-runner.sh` via `nohup`. Queue: `.overnight/queue.tsv`.

### Goal

Three deliverables on one branch:
1. **Polish v11-picks-plus** with critic formatting (byline, small-caps dateline, drop-cap, paragraph-aware rendering, WCAG-AA neutrals, 65–75ch measure, non-Inter pair); impeccable `detect` findings addressed.
2. **Ten stylistic variants of v11** under `docs/variants/v11a..v11j/` reusing v11's IA (picks + sorted listings + always-visible showings + click-to-expand). Gallery updated.
3. **Review-quality pilot** on 5 hand-picked films: factual dossier from Wikipedia (stdlib) + Letterboxd (bs4) injected into the Perplexity prompt, output to `docs/data-pilot.json` + side-by-side A/B preview at `docs/variants/v11-review-uplift/`. Zero risk to the 233-event `docs/data.json`.
4. **Residual 04-15 cleanup**: 8 AI-smell violations → 0, AFS one-liners 43→56/56, Today-view ≥1.

### Definition of done

- `.venv/bin/python -m pytest -q` green
- `.venv/bin/python scripts/verify_calendar.py --offline` PASS (all 22 checks)
- `.venv/bin/python scripts/check_ai_smell.py docs/data.json` exits 0
- `docs/variants/v11-picks-plus/` polished; `audit.md` no CRITICAL
- `docs/variants/v11a..v11j/` exist, each passes `scripts/check_variant.mjs`, each has `audit.md`
- `docs/variants/v11-review-uplift/` renders side-by-side comparison from `docs/data.json` vs `docs/data-pilot.json` (5 events)
- `STATUS-2026-04-16.md` with disposition, commit shas, morning checklist

### Hard constraints

- Branch: `overnight/2026-04-16` only. Never touch `main` / `master`. Never `git reset --hard`, `git push --force`, or rewrite history. Runner does **NOT** push; user reviews and merges manually.
- No new dependencies: no `pip install`, `npm install`, `cargo add`, `go get`. If a task thinks it needs one, write BLOCKED with reason `needs-dep: <name>`.
- No interactive prompts. No `--no-verify` on commits.
- Git identity: every commit via `git -c user.name=Hadrien-Cornier -c user.email=hadrien.cornier@gmail.com commit -m '...'`. Never mutate `~/.gitconfig` or `.git/config`.
- Never commit `.env`, `cache/`, `.agents/`, `skills-lock.json`. `.overnight/` is gitignored; do not `git add` it. `docs/data-pilot.json` **is** committed (A/B artifact).
- Scope fence: `src/`, `scripts/`, `tests/`, `docs/`, `update_website_data.py`, `config/master_config.yaml`, `CLAUDE.md`, `CHANGELOG.md`, `STATUS-2026-04-16.md`. Nothing else.
- **GitNexus impact analysis MANDATORY** before editing `src/processor.py`, `src/llm_service.py`, `src/enrichment_layer.py`. T7.1 does this explicitly.
- HTTP sourcing (Wikipedia / Letterboxd) rate-limited 1 qps, cached, attributed. On 403/429 → graceful fallback, log the skip, no aggressive retry.

### Validation oracle (run before every commit)

Per-task oracle — each worker MUST pass only these before committing:

```
.venv/bin/python -m pytest -q
```

Pytest must exit 0. The task's own `validate` command (from queue.tsv) is also required.

**Do NOT run `verify_calendar.py --offline` as a per-task gate.** It contains pre-existing known-red checks (AFS one-liner coverage, Today-view date) that specific tasks (T8.4, T8.5) are responsible for fixing; running it as a universal oracle blocks unrelated tasks. `verify_calendar.py --offline` runs only in **T9.1 final gate** after all fix tasks complete.

Same rule for `scripts/check_ai_smell.py` — only T8.2, T8.3, and T9.1 gate on it.

If the per-task oracle fails twice in a row for the same task, write BLOCKED and rotate.

### Commit cadence

One commit per DONE task. Message format: `<type>(task-<ID>): <TITLE>` (feat/fix/docs/chore/refactor/test). Stage only files in the task's `files` column; never `git add -A`.

### Changelog entry per task

After each DONE commit, append one line to the fenced overnight block in `CHANGELOG.md`:

```
### task-<ID> — DONE — <ISO timestamp>
- commit: <sha>
- files: <comma-separated>
- validation: green
```

### Stop conditions

- All queue tasks DONE → `RUN_COMPLETE`
- Deadline (2026-04-17T12:00:00Z) reached → `RUN_HALTED: deadline`
- 3 consecutive BLOCKED tasks → `RUN_HALTED: consecutive-blockers`
- `STATUS-2026-04-16.md` contains line `HALT` (manual override) → `RUN_HALTED: manual`

### Blocker protocol

A task blocks when validation fails twice. Append to CHANGELOG under today's fenced block:
```
BLOCKED: task-<ID>: <one-line reason + failing-command head/tail>
```
Then write `.overnight/task-result.json` with `{"status": "BLOCKED", "task_id": "task-<ID>", "reason": "<one line>"}`. The runner rotates to the next eligible task.

### Task queue (human view; source of truth is `.overnight/queue.tsv`)

- **T8.1** — Verify branch + startup checks
- **T8.2** — Targeted regen of 4 remaining banned-phrase events
- **T8.3** — Raise em-dash threshold 5 → 8 in `scripts/check_ai_smell.py`
- **T8.4** — Backfill 13 missing AFS one-liners
- **T8.5** — Fix Today-view synthetic date in `scripts/verify_calendar.py`
- **T5.2** — Polish `v11-picks-plus/styles.css` (impeccable refs)
- **T5.3** — Polish `v11-picks-plus/script.js` (paragraph parsing + byline + dateline)
- **T5.4** — `npx impeccable detect` on v11-picks-plus; fix findings
- **T6.1..T6.10** — Generate v11a..v11j variants (IA preserved, styles vary)
- **T6.11** — Update gallery with v11 variants section
- **T6.12** — Aggregate V11_AUDIT_SUMMARY.md
- **T7.1** — GitNexus impact analysis for review-uplift touch points
- **T7.2** — `src/sources/wikipedia.py` (stdlib only)
- **T7.3** — `src/sources/letterboxd.py` (bs4, polite)
- **T7.4** — `_fact_dossier()` in `src/processor.py`
- **T7.5** — `--pilot` flag in `update_website_data.py` → `docs/data-pilot.json`
- **T7.6** — `docs/variants/v11-review-uplift/` A/B preview
- **T9.1** — Final gate: pytest + verify_calendar + check_ai_smell
- **T9.2** — Write `STATUS-2026-04-16.md` handoff

<!-- END OVERNIGHT-PLAN: 2026-04-16 -->
