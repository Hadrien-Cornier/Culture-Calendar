# CLAUDE.md

Guidance for Claude Code working in this repository.

## Project Overview

Culture Calendar scrapes Austin cultural events (films, concerts, book clubs, opera, ballet, visual arts) from multiple venues, enriches them with AI ratings/analysis, and publishes them to GitHub Pages at `https://hadrien-cornier.github.io/Culture-Calendar/` with ICS/RSS export.

**Current venues**: Austin Film Society, Hyperreal Film Club, Austin Symphony, Early Music Austin, La Follia, Austin Opera, Ballet Austin, Alienated Majesty Books, First Light Austin, Arts on Alexander, NowPlayingAustin (visual arts).

## Development Commands

```bash
# Setup
pip install -r requirements.txt
cp .env.example .env  # add PERPLEXITY_API_KEY + ANTHROPIC_API_KEY

# Running
python update_website_data.py              # full scrape + update
python update_website_data.py --test-week  # current week only
python update_website_data.py --force-reprocess  # ignore cache
python update_website_data.py --validate   # fail-fast on scraper failures

# Testing
pytest tests/                                     # all tests
pytest tests/ -m "not live and not integration"   # unit only
pytest tests/ --cov=src --cov-report=html         # with coverage

# Code quality
black src/ tests/ *.py
python pre_commit_checks.py                 # format + tests
```

## Architecture

**Two-phase pipeline.** Phase 1 — each scraper extends `BaseScraper` (src/base_scraper.py:20), extracts raw events, normalizes to schema (snake_case, YYYY-MM-DD, HH:mm). LLM extraction for dynamic sites (Hyperreal, Alienated Majesty, First Light). Phase 2 (optional per venue) — `EnrichmentLayer` (src/enrichment_layer.py:40) classifies `event_category` and fills missing required fields with evidence validation.

**Key components**:
- `config/master_config.yaml` — single source of truth (templates: movie, concert, book_club, opera, dance, visual_arts, other; per-venue policies). Loaded via `ConfigLoader` (src/config_loader.py).
- `BaseScraper` (src/base_scraper.py) — abstract base with LLM service, `format_event()`, `validate_event()`.
- `MultiVenueScraper` (src/scraper.py:28) — orchestrates all venue scrapers, handles dedup.
- `LLMService` (src/llm_service.py) — abstracts Perplexity (Sonar) + Anthropic (Claude).
- `EventProcessor` (src/processor.py:19) — AI ratings/reviews via Perplexity.
- `SummaryGenerator` (src/summary_generator.py) — one-line hooks via Claude.

Static JSON loading is used for season-based venues (Symphony, Opera, Ballet) — see Classical refresh below.

**Data flow**: `MultiVenueScraper.scrape_all_venues()` → `EventProcessor.process_events()` → `SummaryGenerator` → `update_website_data.py` writes `docs/data.json` + ICS/RSS builders → GitHub Pages serves `docs/`.

**Event schema** (per master_config.yaml): `dates`/`times` arrays (pairwise zip), `occurrences`, `event_category`, `rating` (0–10 AI artistic merit), `review_confidence`, `description`, `one_liner_summary`, `venue_address`, `venue_display_name`. Category-specific fields per template (movies: director/country/language; concerts: composers/works; etc.).

## Common Development Tasks

- **Add a venue**: extend `BaseScraper` in `src/scrapers/<venue>_scraper.py`; add config under `venues:` in master_config.yaml; register in `src/scrapers/__init__.py` + `MultiVenueScraper`; unit tests at `tests/test_<venue>_scraper_unit.py`; smoke with `python update_website_data.py --test-week`.
- **Debug scraper failures**: run with `--validate`; check if site structure changed (most common cause); review LLM prompts for smart scrapers; inspect enrichment telemetry.
- **Modify schema**: edit template in master_config.yaml; update scraper; update enrichment prompts; adjust `update_website_data.py:build_event_from_template()`; update tests.

### Classical refresh pipeline

Season-based classical/ballet venues (Austin Symphony, Early Music Austin, La Follia, Austin Chamber Music, Austin Opera, Ballet Austin) ship as static JSON in `docs/classical_data.json` + `docs/ballet_data.json`, not via per-event scrapers. `scripts/refresh_classical_data.py` is the LLM-driven monthly refresh.

- **Cron**: `.github/workflows/refresh-classical-data.yml` fires `0 12 1 * *` (12:00 UTC, 1st of month). Manual: `gh workflow run refresh-classical-data.yml`.
- **Workflow**: runs `python scripts/refresh_classical_data.py --dry-run --use-perplexity`, parses JSON summary, writes validated payloads, opens a PR `chore: monthly classical/ballet data refresh` on `bot/classical-refresh-<date>`. **PR is intentionally never auto-merged** — human review required.
- **Local**: `.venv/bin/python scripts/refresh_classical_data.py --dry-run` (in-memory stub). Add `--use-perplexity` for live API. `--venue <key>` (any key in `CLASSICAL_VENUE_KEYS`/`BALLET_VENUE_KEYS`) restricts to one.
- **Validation**: `validate_classical_data` enforces `dates` (YYYY-MM-DD) / `times` (HH:mm) / `type ∈ {concert, opera, dance}` / `REQUIRED_EVENT_FIELDS`. Runs before any disk write; `ValueError` aborts the refresh.
- **Failure mode**: Perplexity occasionally returns `{events: []}` per venue → `LLMFetchError` aborts before clobbering on-disk JSON. This is why cadence is monthly.
- **Secrets**: `PERPLEXITY_API_KEY` + `ANTHROPIC_API_KEY` in repo secrets; `contents: write` + `pull-requests: write` permissions.

## Known Issues

Pyppeteer threading blocks running all scrapers in parallel ("signal only works in main thread"). Read-review button can crash the site. Rating distribution needs preference tuning.

## Testing Strategy

Unit tests mock scrapers, no network. Integration tests use cached responses. Live tests via `@pytest.mark.live`. Fixtures under `tests/{Venue}_test_data/`. Validation service: `tests/test_validation_integration.py`.

## GitNexus — code intelligence

Indexed as **Culture-Calendar**. Refresh: `npm run analyze` (NOT `npx gitnexus` — breaks on Node v24).

**Hard rules**:
- MUST run `gitnexus_impact({target, direction: "upstream"})` before editing any function/class/method.
- MUST run `gitnexus_detect_changes()` before committing.
- For unfamiliar code, `gitnexus_query({query: "concept"})` beats grep.
- Rename via `gitnexus_rename({dry_run: true})` then `dry_run: false`. Never find-and-replace.
- Never ignore HIGH/CRITICAL risk warnings (d=1 WILL BREAK; d=2 LIKELY AFFECTED; d=3 MAY NEED TESTING).

Skill files at `.claude/skills/gitnexus/`. Resources via `gitnexus://repo/Culture-Calendar/`.

## Feature Inventory

Canonical user-visible feature list at `config/feature-inventory.json` — entries record CSS selector + smoke assertion. Every task adding/changing a user-visible feature MUST append its entry BEFORE committing. The continuity-user persona asserts each selector on the live site on every run. Skipping is the regression pattern that previously dropped the TTS button (`986877e` → `c45fdfd`) and the About section (`c03f617` → v12i promotion).

Entry shape: `{id, name, selector, since_commit, smoke_assertion}` where `smoke_assertion` is `selector_exists | contains_text:<...> | js_truthy:<...>`. Append-only; never reorder. If removing a feature, delete the entry in the same commit and note in CHANGELOG. Selectors must resolve on the LIVE site.

## Persona critique gate

Two persona layers, both authored as JSON specs an LLM consumes. See `personas/README.md` for per-persona detail.

**Live-site UX critique** (`personas/live-site/`): six personas (logistics-user, review-reader, search-user, comprehensiveness-user, continuity-user, mobile-user) critique the deployed site via `scripts/persona_critique.py`. Default model: Claude Sonnet 4.6. **Local-only** — runs on workstation before push, not in CI.

**Code-review critique** (`personas/code-review/`): two permanent reviewers grade pending diffs:
- `review-quality.json` — senior-engineer lens; flags diffs that weaken AI review generation (dropped evidence requirements, lowered confidence thresholds, generic prompts).
- `repo-minimalism.json` — Karpathy/nanochat lens; flags ceremony, helper graveyards, premature abstraction, parallel near-duplicates, bloat in `CLAUDE.md`/`CHANGELOG.md`.

Manual run: `.venv/bin/python scripts/review_quality_check.py` (defaults to staged + worktree; `--commit` for `HEAD~1..HEAD`, `--staged` for cached only, `--no-llm` to print prompt). Both reviewers also fire automatically inside the long-run council; any FAIL re-queues the task. `.githooks/pre-push` validates `personas/code-review/repo-minimalism.json` parses on every push.

**`[persona-gate]` commit tag**: tag commit subject with literal `[persona-gate]` for significant changes (architectural UI refactors, feature removals/restorations, redesigns — anything a reviewer would call "a new direction"). Don't tag bug fixes, copy tweaks, CSS polish, data refreshes, or dep bumps. `.githooks/pre-push` scans outgoing commits for the marker; on match starts a local server, runs `scripts/require_persona_approval.py` → `persona_critique` in LLM mode, aborts push on any FAIL. Activate per-clone: `git config core.hooksPath .githooks`. Emergency bypass: `git push --no-verify`.

## Autonomous Run Baseline

All long runs inherit these rules. Each run's section below lists unique goals, scope, queue. Driven by `~/.claude/skills/overnight-plan/scripts/overnight-runner.sh` via `nohup`, with per-run `queue.tsv` as task source.

**Hard constraints**:
- Branch: the run's own branch only (or `main` if explicitly authorized). Never `git reset --hard`, `git push --force`, `git rebase`, or rewrite history. Runner does NOT push unless the run specifies otherwise.
- No new deps — no `pip install`, no `npm install`. Need one → BLOCKED `needs-dep: <name>`.
- No paid API deps. LLM calls reuse Perplexity + Anthropic from `.env`.
- No interactive prompts. No `--no-verify` on commits.
- Git identity: `git -c user.name=Hadrien-Cornier -c user.email=hadrien.cornier@gmail.com`. Never mutate `~/.gitconfig`.
- Never commit `.env`, `cache/llm_cache.json`, `.agents/`, `skills-lock.json`, or runtime working files under `.long-run/<RUN_ID>/`.
- Feature-inventory discipline: append to `config/feature-inventory.json` BEFORE committing any user-visible change.
- GitNexus impact analysis MANDATORY before editing any symbol.

**Validation oracle** (every task before commit):
```
.venv/bin/python -m pytest -q
```
Plus the task's own `validate` from `queue.tsv`. Both must exit 0. Never run `scripts/verify_calendar.py --offline` per-task — only explicit final-gate tasks.

**Commit cadence**: One commit per task (or two-commit template adds CHANGELOG commit). Format: `<type>(task-<ID>): <title>` where `<type>` matches the task's `ctype=` prefix. Stage only `files` from the task; never `git add -A`. Append CHANGELOG entry inside run's fenced block:
```
### task-<ID> — DONE — <ISO timestamp>
- commit: <sha>
- files: <comma-separated>
- validation: green
```

**Deploy-wait** (runs pushing directly to `main`): after `git push origin main`, poll a changed file at `https://hadrien-cornier.github.io/Culture-Calendar/<file>` every 15–20s until served content matches pushed. Timeout 5 min → BLOCKED `deploy-timeout`. Each task adds a unique grep-able marker.

**Revert protocol** (live-check fails on docs/ task pushing to `main`): `git revert HEAD --no-edit` + push, wait for deploy, BLOCKED with attempted + reverted shas + reason in CHANGELOG.

**Stop conditions**: All DONE → `RUN_COMPLETE`. Past deadline → `RUN_HALTED: deadline`. 3 consecutive BLOCKED → `RUN_HALTED: consecutive-blockers`. Bare `STATUS.md` at root contains `HALT` → `RUN_HALTED: manual`.

**Handoff**: Runner emits final event to `.long-run/<RUN_ID>/events.log`. Branch stays local; user reviews scorecard + merges to `main` manually unless run authorized direct-main pushes.

## Run log

Historical run summaries (2026-04-15 → 20260425-175347) live in `archive/CLAUDE-runs.md`. The active run section follows.

<!-- BEGIN LONG-RUN: 20260430-102637 -->
## Long run — 20260430-102637

> **AUTONOMOUS RUN — do not edit while running.**
> Owner: Hadrien-Cornier · Started: 2026-04-30T15:32:24Z · Deadline: 2026-05-01T03:32:24Z · Branch: `long-run/20260430-102637`

### Goal

Five overlapping workstreams: (1) NYT-inspired typography on docs/ with real web fonts; (2) fix Ballet review quality (root cause: `ballet_austin_scraper.py:66` hardcodes `type=concert` instead of `dance`, and there is no `_get_dance_rating()` method); (3) automate the classical-music data refresh via a monthly LLM-driven script + new GitHub Action (existing `update-calendar.yml` has been failing weekly cron since Apr 18); (4) introduce two permanent LLM reviewers (`personas/code-review/review-quality.json` + `personas/code-review/repo-minimalism.json`) wired into pre-push and a manual command; (5) aggressive karpathy/nanochat-style cleanup including removing `.overnight/`, trimming CLAUDE.md + CHANGELOG.md, archiving `.long-run/` history, and consolidating 5 near-identical classical-music scrapers.

### Definition of done

By the deadline above, the following must all be true:

- `update-calendar.yml` and `pr-validation.yml` workflows pass on the long-run branch.
- Ballet events tagged `type=dance`; `_get_dance_rating()` exists and is invoked; reviews mention choreographer/company/repertoire.
- `scripts/refresh_classical_data.py` exists with `--dry-run` mode + `.github/workflows/refresh-classical-data.yml` cron monthly.
- `personas/live-site/*.json` × 6 (migrated) and `personas/code-review/{review-quality,repo-minimalism}.json` (new) exist and are wired in.
- Source Serif 4 + Inter loaded as web fonts; CSS type-scale variables drive every typographic font-size in `docs/styles.css`.
- `.overnight/` deleted; root has no `*.log`; `CLAUDE.md` < 250 lines; `CHANGELOG.md` < 800 lines; `.long-run/` retains only the active run dir.
- 5 classical scrapers consolidated into `_static_json_scraper.py` + thin per-venue config.
- `.venv/bin/python -m pytest -q` exits 0; `scripts/verify_calendar.py --offline` passes; live-site persona council 6/6 PASS.
- ≥6 new feature-inventory entries (typography surfaces + new reviewers).
- `STATUS-20260430-102637.md` handoff written.

### Hard constraints

- Branch: `long-run/20260430-102637` only — no commits to `main`, no per-task push to `main`.
- Never `git push --force`, `git rebase`, `git reset --hard`, no rewriting history.
- No `pip install` / `npm install` / new deps. Stdlib only for new Python.
- Commits authored as `Hadrien-Cornier <hadrien.cornier@gmail.com>`. Never `hcornier@talroo.com`.
- Never `--no-verify` on commits.
- Touch only the files in each task's `files` column or in the scope fence below.

### Scope fence

In-scope:
- `src/` — for T2.x (dance handler), T6.6a/b (scraper consolidation).
- `scripts/` — for T1.x (verify_calendar tolerance), T3.x (refresh script), T4.5 (review_quality_check.py), T6.7 (audit).
- `tests/` — every task's tests live here.
- `docs/` (NOT `docs/variants/`) — for T5.x typography, T2.5 data refresh, T1.3 fixture, T7.1 data.json.
- `config/master_config.yaml` — for T3.1b (season URLs), T6.6 (scraper config), T4.1 (feature-inventory move).
- `personas/` (new directory) — for T4.x.
- `archive/` (new directory) — for T6.1, T6.2, T6.3 historical files.
- `.github/workflows/` — for T1.5, T3.2, plus targeted edits in T1.x.
- `.githooks/pre-push` — for T4.4.
- `.gitignore` — for T6.x cleanup additions.
- `.long-run/20260430-102637/` — runner state.
- `CLAUDE.md`, `CHANGELOG.md` — fenced blocks only.
- `STATUS-20260430-102637.md` — handoff in T7.2.

Read-only (must not edit):
- `docs/variants/` — archival.
- Other `STATUS-*.md` files — historical.
- Any prior `.long-run/2026*/` directories (those get DELETED in T6.5, not edited).

### Validation oracle

Every task before commit:
```
.venv/bin/python -m pytest -q
```
Plus the task's own `validate` from `.long-run/20260430-102637/queue.tsv`. Both must exit 0. Never run `scripts/verify_calendar.py --offline` as a per-task oracle — pre-existing red items would block unrelated tasks. Only T1.4 and T7.1 dispatch verify_calendar.

### Task queue

Source of truth: `.long-run/20260430-102637/queue.tsv` — 38 tasks across 7 phases (1.1 → 7.3). See `~/.claude/plans/i-want-to-improve-sparkling-simon.md` for the full plan.

Phase 1 (1.1–1.5) — fix GitHub Actions (data is stale).
Phase 2 (2.1–2.5) — Ballet dance handler.
Phase 3 (3.1a–3.4) — classical refresh script + new monthly workflow.
Phase 4 (4.1–4.6) — new LLM reviewers in `personas/`.
Phase 5 (5.1–5.6) — NYT-inspired typography (`[persona-gate]` on T5.6).
Phase 6 (6.1–6.7) — aggressive minimalism cleanup.
Phase 7 (7.1–7.3) — final gate + handoff.

### `[persona-gate]` tags

Apply to commits for: T1.5 (workflow gate change), T4.4 (gate-config change), T5.6 (typography redesign), T6.4 (`.overnight/` removal — discoverability shift). Pre-push hook will run live-site council against local server.

### GitNexus impact required before editing

- T2.1 — `ballet_austin_scraper.py` symbol used downstream.
- T2.2 — `processor._get_classical_rating` and the rating dispatch.
- T2.3 — `summary_generator._build_concert_prompt`.
- T4.1 — persona path constants.
- T6.4 — `.overnight/` references across scripts.
- T6.6a/b — every scraper class in `src/scrapers/__init__.py`.

### Stop conditions

- All tasks DONE → `RUN_COMPLETE`.
- Wall clock ≥ deadline (2026-05-01T03:32:24Z) → `RUN_HALTED: deadline`.
- 3 consecutive BLOCKED tasks → `RUN_HALTED: consecutive-blockers`.
- `STATUS.md` at repo root contains `HALT` → `RUN_HALTED: manual`.

### Handoff

Runner emits final event to `.long-run/20260430-102637/events.log`. Branch stays local; user reviews scorecard at `.long-run/20260430-102637/scorecard.md` and merges manually.
<!-- END LONG-RUN: 20260430-102637 -->
