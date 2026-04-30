# CLAUDE.md

Guidance for Claude Code working in this repository.

## Project Overview

Culture Calendar scrapes Austin cultural events (films, concerts, book clubs, opera, ballet, visual arts) from multiple venues, enriches them with AI ratings/analysis, and publishes them to GitHub Pages at `https://hadrien-cornier.github.io/Culture-Calendar/` with ICS/RSS export.

**Current venues**: Austin Film Society, Hyperreal Film Club, Austin Symphony, Early Music Austin, La Follia, Austin Opera, Ballet Austin, Alienated Majesty Books, First Light Austin, Arts on Alexander, NowPlayingAustin (visual arts).

## Development Commands

### Setup
```bash
pip install -r requirements.txt
cp .env.example .env  # add PERPLEXITY_API_KEY + ANTHROPIC_API_KEY
```

### Running
```bash
python update_website_data.py              # full scrape + update
python update_website_data.py --test-week  # current week only
python update_website_data.py --force-reprocess  # ignore cache
python update_website_data.py --validate   # fail-fast on scraper failures
```

### Testing
```bash
pytest tests/                                     # all tests
pytest tests/ -m "not live and not integration"   # unit only
pytest tests/test_afs_scraper_unit.py -v          # specific scraper
pytest tests/ --cov=src --cov-report=html         # with coverage
```

### Code quality
```bash
black src/ tests/ *.py
python pre_commit_checks.py                 # format + tests
python pre_commit_checks.py --fix-only
```

## Architecture

### Two-phase pipeline

**Phase 1 — Normalization.** Each scraper extends `BaseScraper` (src/base_scraper.py:20), extracts raw events, normalizes to the config-driven schema (snake_case, YYYY-MM-DD, HH:mm). LLM extraction used for dynamic sites (Hyperreal, Alienated Majesty, First Light).

**Phase 2 — Enrichment** (optional per venue). LLM classifies `event_category` and fills missing required fields with evidence validation. Orchestrated at src/enrichment_layer.py:40.

### Key components

- **Config** — `config/master_config.yaml` is single source of truth (templates: movie, concert, book_club, opera, dance, visual_arts, other; per-venue policies for frequency, classification on/off, assumed category). Loaded via `ConfigLoader` (src/config_loader.py).
- **BaseScraper** (src/base_scraper.py) — abstract base with LLM service, session management, `format_event()`, `validate_event()`.
- **MultiVenueScraper** (src/scraper.py:28) — orchestrates all venue scrapers, handles dedup.
- **LLMService** (src/llm_service.py) — abstracts Perplexity (Sonar) + Anthropic (Claude).
- **EventProcessor** (src/processor.py:19) — AI ratings/reviews via Perplexity.
- **EnrichmentLayer** (src/enrichment_layer.py:17) — classification + field extraction with evidence validation.
- **SummaryGenerator** (src/summary_generator.py) — one-line hooks via Claude.

Static JSON loading is used for season-based venues (Symphony, Opera, Ballet).

### Data flow

1. `MultiVenueScraper.scrape_all_venues()` → raw events (Phase 1).
2. `EventValidationService` (optional, `--validate`) → health check; fail-fast on systematic failures.
3. `EventProcessor.process_events()` → AI ratings + descriptions.
4. `SummaryGenerator` → one-line hooks.
5. `update_website_data.py` → `docs/data.json` (grouped by title for movies, unique for others).
6. ICS/RSS builders → `docs/calendar.ics`, `docs/top-picks.ics`, per-event `docs/events/<slug>.ics`, `docs/feed.xml`.
7. GitHub Pages serves `docs/`.

### Event schema

Common fields (per master_config.yaml):
- `dates` / `times` — arrays with pairwise `zip` rule (YYYY-MM-DD, HH:mm).
- `occurrences` — `[{date, time, url, venue}, ...]`.
- `event_category` — movie | concert | book_club | opera | dance | visual_arts | other.
- `rating` — 0–10 AI score on artistic merit.
- `review_confidence` — low | medium | high | unknown.
- `description` — AI analysis (French cinéaste style for films, distinguished criticism for music).
- `one_liner_summary` — Claude-generated hook.
- `venue_address`, `venue_display_name`.

Category-specific fields per template (movies: director/country/language; concerts: composers/works; etc.).

## Common Development Tasks

### Add a new venue
1. Extend `BaseScraper` in `src/scrapers/<venue>_scraper.py`; implement `scrape_events()`.
2. Add venue config under `venues:` in `config/master_config.yaml`.
3. Register in `src/scrapers/__init__.py` + `MultiVenueScraper.__init__()` + `scrape_all_venues()` (src/scraper.py).
4. Unit tests at `tests/test_<venue>_scraper_unit.py`.
5. Smoke: `python update_website_data.py --test-week`.

### Debug scraper failures
- Run with `--validate` for health report.
- Check if the website structure changed (most common cause).
- Review LLM extraction prompts for smart scrapers.
- Inspect enrichment telemetry (classifications, abstentions, fields accepted/rejected).

### Modify schema
- Edit template in `config/master_config.yaml`.
- Update scraper to populate new fields.
- Update enrichment prompts if the field needs LLM extraction.
- Adjust `update_website_data.py:build_event_from_template()` for special handling.
- Update tests.

### Classical refresh pipeline

Season-based classical/ballet venues (Austin Symphony, Early Music Austin, La Follia, Austin Chamber Music, Austin Opera, Ballet Austin) ship as static JSON in `docs/classical_data.json` + `docs/ballet_data.json`, not via per-event scrapers. `scripts/refresh_classical_data.py` is the LLM-driven monthly refresh that keeps those two files in sync with each venue's published season.

- **Cron**: `.github/workflows/refresh-classical-data.yml` fires at `0 12 1 * *` (12:00 UTC, 1st of month). Manual run: `gh workflow run refresh-classical-data.yml`.
- **What the workflow does**: runs `python scripts/refresh_classical_data.py --dry-run --use-perplexity`, parses the JSON summary from stdout, writes the validated `classical_payload` and `ballet_payload` to disk, and opens a PR titled `chore: monthly classical/ballet data refresh` on a `bot/classical-refresh-<date>` branch. **The PR is intentionally never auto-merged** — a human reviews the LLM-fetched diff before it ships.
- **Local dry-run**: `.venv/bin/python scripts/refresh_classical_data.py --dry-run` uses the in-memory stub fetcher; add `--use-perplexity` for the live API. `--venue <key>` (any key in `CLASSICAL_VENUE_KEYS` / `BALLET_VENUE_KEYS`, e.g. `austinSymphony`) restricts to one venue.
- **Schema validation**: `validate_classical_data` in the same script enforces `dates` (YYYY-MM-DD) / `times` (HH:mm) / `type ∈ {concert, opera, dance}` / `REQUIRED_EVENT_FIELDS`. It runs before any disk write in both dry-run and live modes; a `ValueError` aborts the refresh.
- **Failure modes**: Perplexity sporadically returns `{events: []}` for individual venues, which raises `LLMFetchError` from `src/llm_service.py` and (correctly) aborts the pipeline before the curated on-disk JSON gets clobbered with sparser LLM output. This is why the cadence is monthly, not weekly.
- **Secrets**: the workflow needs `PERPLEXITY_API_KEY` and `ANTHROPIC_API_KEY` in repo secrets, plus `contents: write` + `pull-requests: write` permissions (already declared in the YAML).

## Known Issues

1. **Pyppeteer threading** — can't run all scrapers in parallel ("signal only works in main thread").
2. **Read-review button** — can crash the site (README problems).
3. **Rating distribution** — not well spread; needs preference tuning.

## Testing Strategy

- **Unit**: mock scrapers, parsing logic, no network.
- **Integration**: full pipeline with cached responses.
- **Live**: `@pytest.mark.live`, real scraping.
- Fixtures under `tests/{Venue}_test_data/`.
- Validation service: `tests/test_validation_integration.py`.

## Configuration Notes

- `master_config.yaml` is single source of truth.
- Book-club year inferred at runtime (current vs next).
- Venue policies drive classification (e.g. AFS assumes `movie`, classification disabled).
- Field defaults at config level.
- `snake_case` enforced.

---

## GitNexus — code intelligence

Indexed as **Culture-Calendar** (1511 symbols, 3370 relationships, 119 execution flows). If any tool warns the index is stale, run `npm run analyze` — **not `npx gitnexus`** (breaks on Node v24 via tree-sitter-swift rebuild bug).

### Hard rules
- MUST run `gitnexus_impact({target, direction: "upstream"})` before editing any function/class/method. Report blast radius; WARN on HIGH/CRITICAL.
- MUST run `gitnexus_detect_changes()` before committing to confirm scope.
- For unfamiliar code, `gitnexus_query({query: "concept"})` beats grep.
- Rename via `gitnexus_rename({dry_run: true})` → review → `dry_run: false`. Never find-and-replace.
- Extract/split: `gitnexus_context({name})` + `gitnexus_impact({direction: "upstream"})` before moving code.
- Never ignore HIGH/CRITICAL risk warnings.
- After any refactor: `gitnexus_detect_changes({scope: "all"})` to verify only expected files changed.

### Tools
| Tool | When | Example |
|------|------|---------|
| `query` | find code by concept | `gitnexus_query({query: "auth validation"})` |
| `context` | 360° symbol view | `gitnexus_context({name: "validateUser"})` |
| `impact` | blast radius before edit | `gitnexus_impact({target: "X", direction: "upstream"})` |
| `detect_changes` | pre-commit scope | `gitnexus_detect_changes({scope: "staged"})` |
| `rename` | safe multi-file rename | `gitnexus_rename({symbol_name, new_name, dry_run: true})` |
| `cypher` | custom graph queries | `gitnexus_cypher({query: "MATCH ..."})` |

### Risk levels
- **d=1** — WILL BREAK (direct callers) → MUST update.
- **d=2** — LIKELY AFFECTED (indirect deps) → should test.
- **d=3** — MAY NEED TESTING (transitive) → test if critical path.

### Debugging flow
1. `gitnexus_query({query: "<error/symptom>"})` → find execution flows.
2. `gitnexus_context({name: "<suspect>"})` → callers + callees + process participation.
3. `READ gitnexus://repo/Culture-Calendar/process/{name}` → step-by-step trace.
4. Regression: `gitnexus_detect_changes({scope: "compare", base_ref: "main"})` → see what the branch changed.

### Resources
- `gitnexus://repo/Culture-Calendar/context` — overview, freshness.
- `gitnexus://repo/Culture-Calendar/clusters` — functional areas.
- `gitnexus://repo/Culture-Calendar/processes` — execution flows.
- `gitnexus://repo/Culture-Calendar/process/{name}` — step-by-step trace.

### Keeping the index fresh
After committing, run `npm run analyze` (deletes prior embeddings) or `./node_modules/.bin/gitnexus analyze --embeddings` (preserves). Check `.gitnexus/meta.json` `stats.embeddings`. A PostToolUse hook handles this after `git commit`/`git merge`.

### Skill files
| Task | File |
|------|------|
| Understand architecture | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

### Self-check before finishing
1. `gitnexus_impact` was run on all modified symbols.
2. No HIGH/CRITICAL risk ignored.
3. `gitnexus_detect_changes()` scope matches expected.
4. All d=1 (WILL BREAK) dependents updated.

---

## Feature Inventory

Canonical list of user-visible features lives at `config/feature-inventory.json`. Each entry records the CSS selector + smoke assertion proving the feature is live.

**Discipline:** every task adding or changing a user-visible feature MUST append its entry BEFORE committing. The continuity-user persona asserts each listed selector on the live site on every run. Skipping the append step is the regression pattern that previously dropped the TTS button (`986877e` → `c45fdfd`) and the About section (`c03f617` → v12i promotion).

Entry shape:
```json
{
  "id": "<slug>",
  "name": "<human name>",
  "selector": "<CSS selector>",
  "since_commit": "<introducing or restoring commit>",
  "smoke_assertion": "selector_exists | contains_text:<...> | js_truthy:<...>"
}
```

Rules:
- Append only; never reorder or rewrite existing entries (preserves git-blame).
- If removing a feature, delete the entry in the same commit and note it in CHANGELOG.
- Selectors must resolve on the LIVE site, not just source.

---

## Persona critique gate

Two persona layers, both authored as JSON specs that an LLM consumes. See `personas/README.md` for per-persona detail.

### Live-site UX critique (`personas/live-site/`)
Six personas — logistics-user, review-reader, search-user, comprehensiveness-user, continuity-user, mobile-user — critique the deployed site via `scripts/persona_critique.py`. Model: Claude Sonnet 4.6 by default, chosen by `scripts/bench_personas.py`; see `docs/persona_model_benchmark.md`.

**Local-only.** Council runs on your workstation before push, not in CI — no Anthropic API key on GitHub, no per-push CI cost. Trade-off: regressions between `[persona-gate]` runs aren't auto-detected; run `scripts/persona_critique.py` manually for a fresh scorecard.

### Code-review critique (`personas/code-review/`)
Two permanent reviewers grade pending diffs, not the website:
- `review-quality.json` — senior-engineer lens; flags diffs that weaken AI review generation (dropped evidence requirements, lowered confidence thresholds, generic prompts replacing category-specific dispatch).
- `repo-minimalism.json` — Karpathy/nanochat lens; flags ceremony, helper graveyards, premature abstraction, parallel near-duplicate files, bloat in `CLAUDE.md` / `CHANGELOG.md`.

Manual run: `.venv/bin/python scripts/review_quality_check.py` (defaults to staged + worktree; `--commit` for `HEAD~1..HEAD`, `--staged` for cached only, `--no-llm` to print the prompt). Both reviewers also fire automatically inside the long-run council harness; any FAIL re-queues the task.

`.githooks/pre-push` validates `personas/code-review/repo-minimalism.json` parses on every push and announces the gate.

### `[persona-gate]` commit tag
Tag the commit subject with literal `[persona-gate]` for significant changes (architectural UI refactors, feature removals/restorations, redesigns). Example:
```
feat(ui): [persona-gate] replace chip drawer with combobox search
```
`.githooks/pre-push` scans outgoing commits for the marker. On match:
1. Starts `python -m http.server` rooted at `docs/` on a free port.
2. Copies persona JSONs to tempdir, rewriting URLs to `http://127.0.0.1:<port>/`.
3. Runs `scripts/require_persona_approval.py` → persona_critique in LLM mode.
4. Aborts push on any FAIL; scorecard at `.overnight/gate-b-scorecard.md`.

Activate per-clone: `git config core.hooksPath .githooks`.

**Tag when:** removing a user-visible feature; redesigning a primary surface; any change a reviewer would call "a new direction" rather than "a fix."
**Don't tag:** bug fixes, copy tweaks, CSS polish, data refreshes, dep bumps.
**Emergency bypass:** `git push --no-verify` — revisit the failing verdict afterward.

### On-demand audit
`./venv/bin/python scripts/persona_critique.py --out docs/PERSONAS.md` — commit if you want audit history, skip for local review.

### Key files
| File | Purpose |
|---|---|
| `personas/README.md` | Per-persona index and schema reference |
| `personas/live-site/*.json` | 6 UX-critique persona specs |
| `personas/code-review/*.json` | 2 diff-critique reviewer specs (review-quality, repo-minimalism) |
| `config/feature-inventory.json` | Continuity-user truth source |
| `scripts/persona_critique.py` | Runs live-site personas, emits scorecard + cost JSONL |
| `scripts/bench_personas.py` | Benchmarks Haiku/Sonnet/Opus to pick cheapest w/ ≥5/6 agreement |
| `scripts/require_persona_approval.py` | Local preflight for Gate B |
| `scripts/check_live_site.py` | Pyppeteer structural-assertion runner |
| `scripts/review_quality_check.py` | Manual driver for the review-quality reviewer |
| `config/persona_model.json` | Selected model (written by bench) |
| `docs/PERSONAS.md` | Latest scorecard |
| `docs/persona_model_benchmark.md` | Benchmark results |
| `.githooks/pre-push` | Opt-in pre-push hook (repo-minimalism gate + Gate B) |

---

## Autonomous Run Baseline

All autonomous overnight/long runs inherit these rules. Each run's own section below only lists its unique goals, scope, and task queue. Runs are driven by `~/.claude/skills/overnight-plan/scripts/overnight-runner.sh` via `nohup`, with a per-run `queue.tsv` as source of truth for tasks.

### Hard constraints
- Branch: the run's own branch only (or `main` if the run explicitly authorizes direct pushes). Never `git reset --hard`, `git push --force`, `git rebase`, or rewrite history. Runner does NOT push unless the run specifies otherwise.
- No new deps — no `pip install`, no `npm install`. A task needing one → BLOCKED `needs-dep: <name>`.
- No paid API deps. LLM calls reuse Perplexity + Anthropic from `.env`. Web Speech API and Plausible are browser-native/free.
- No interactive prompts. No `--no-verify` on commits.
- Git identity: every commit (incl. reverts) via `git -c user.name=Hadrien-Cornier -c user.email=hadrien.cornier@gmail.com`. Never mutate `~/.gitconfig`.
- Never commit `.env`, `cache/llm_cache.json`, `.agents/`, `skills-lock.json`, or runtime working files under `.overnight/` / `.long-run/<RUN_ID>/` (events.log, task-*.log, task-result.json, reviews/*.log, task-judge.log, active.pid, scorecard.md, check-*.json, archive-*, venue-prospects/, queue.tsv, runner-prompt.txt). Persistent whitelisted entries under `.overnight/`: `personas/*.json` + `feature-inventory.json`.
- Feature-inventory discipline: every task adding a user-visible feature appends its entry to `config/feature-inventory.json` BEFORE committing.
- GitNexus impact analysis MANDATORY before editing any symbol.

### Validation oracle
Every task before commit:
```
.venv/bin/python -m pytest -q
```
Must exit 0. Plus the task's own `validate` command from `queue.tsv`. **Never** run `scripts/verify_calendar.py --offline` as a per-task oracle — pre-existing red items block unrelated tasks. Only explicitly-named final-gate tasks run it.

### Commit cadence
One commit per task (runs using the two-commit template add a separate CHANGELOG commit). Message format: `<type>(task-<ID>): <title>` where `<type>` comes from the task's `ctype=` prefix (feat / fix / chore / refactor / test / docs). Stage only files listed in the task's `files` column; never `git add -A`. Append one CHANGELOG entry inside the run's fenced block:
```
### task-<ID> — DONE — <ISO timestamp>
- commit: <sha>
- files: <comma-separated>
- validation: green
```

### Deploy-wait (runs pushing directly to `main`)
After `git push origin main`, poll a changed file at `https://hadrien-cornier.github.io/Culture-Calendar/<file>` every 15–20s until served content matches pushed. Timeout 5 min → BLOCKED `deploy-timeout`. Each task adds a unique grep-able marker.

### Revert protocol (live-check fails on docs/ tasks pushing to `main`)
```
git -c user.name=Hadrien-Cornier -c user.email=hadrien.cornier@gmail.com revert HEAD --no-edit
git push origin main
# wait for deploy; re-run validate to confirm stable
```
Then BLOCKED with the failure reason + CHANGELOG entry:
```
### task-<ID> — BLOCKED — <ISO timestamp>
- attempted: <original-sha>
- reverted: <revert-sha>
- reason: <one-line>
```

### Stop conditions
- All queue tasks DONE → `RUN_COMPLETE`.
- Wall-clock past the deadline → `RUN_HALTED: deadline`.
- 3 consecutive BLOCKED tasks → `RUN_HALTED: consecutive-blockers`.
- Bare `STATUS.md` at repo root contains `HALT` → `RUN_HALTED: manual`.

### Handoff
Runner emits its final event to `.long-run/<RUN_ID>/events.log` (or `.overnight/events.log` for earlier runs). Branch stays local; user reviews scorecard + merges to `main` manually unless the run explicitly authorized direct-main pushes.

---

## Run log

Completed runs listed chronologically. Each entry gives goals, unique constraints, and task IDs — full queues live in the corresponding `queue.tsv`. All inherit the Autonomous Run Baseline above unless noted.

### 2026-04-15 → 2026-04-18 — `fix/calendar-oracle` (overnight loop, completed)
CHANGELOG-driven calendar-fix queue. Picks the first `- [ ]` line under "Calendar fix" in CHANGELOG.md — the queue is ordered by dependency. Workflow: do ONLY that subtask (no drive-by fixes; spotted bugs become new `- [ ]` lines); verify with `.venv/bin/python -m pytest -q` + `.venv/bin/python scripts/verify_calendar.py --offline` (both must be green); tick the box (replace `- [ ]` with `- [x] YYYY-MM-DD HH:MM`); commit `feat(calendar): <subtask-id> <what>` + push. Destructive moves: only `git revert HEAD --no-edit` of a just-made commit if tests regressed. Block protocol: append `BLOCKED: <subtask-id>: <why>` under the queue and move on. Exit criterion: `scripts/verify_calendar.py --live` prints PASS two iterations in a row.

### 2026-04-18 — `overnight/2026-04-18` (completed)
Five v11-site fixes, handoff `STATUS-2026-04-18.md`:
1. Rating `/10` suffix + aria-label "rated X out of 10" on badges (picks + listings).
2. Incomplete reviews — description-level refusal filter in `src/processor.py` + test; classify Paper Cuts as pop-up bookshop (type≠book_club, factual pre-filled descriptions); Paramount scraper skips or placeholder-fills events with only a bare title.
3. Case-insensitive category dedup in `uniqueCategories` + subtitle.
4. Collapsible About section from `docs/ABOUT.md`, visible in `docs/index.html`.
5. Web Speech API read-aloud button (`window.speechSynthesis.speak()`, `voiceschanged` listener) on every expanded review. Cross-browser: iOS Safari/DuckDuckGo, Android Chrome/DuckDuckGo, mobile Firefox, desktop Chrome/Safari/Firefox. No audio files committed.

Tasks: T1.2, T1.3, T2.1–T2.4, T3.1, T4.1, T6.1 (final gate runs `verify_calendar.py`), T6.2. Scope fence: `src/`, `scripts/`, `docs/`, `tests/`, `update_website_data.py`, `config/master_config.yaml`, `CLAUDE.md`, `CHANGELOG.md`, STATUS file. GitNexus impact required for `src/processor.py`, `src/scrapers/alienated_majesty_scraper.py`, `src/scrapers/paramount_scraper.py`. DoD includes `is_refusal_response(e.description) is False` for every event in `docs/data.json`.

### 2026-04-19 — `overnight/2026-04-19` (completed)
Three bundled threads, handoff `STATUS-2026-04-19.md`:

- **Primary (must ship):** `visual_arts` event category lands in the schema, NowPlayingAustin visual-arts scraper feeds into `docs/data.json`, art-critic AI rating branch in `src/processor.py`, tests cover it. Tasks T1.1 ontology.labels, T1.2 template (modeled on `concert`), T1.3 `now_playing_austin_visual_arts_scraper.py`, T1.4 register, T1.5 fixtures + unit tests, T1.6 `_get_visual_arts_rating()` branch, T1.7 end-to-end smoke (≥1 visual_arts event in data.json), T1.8 refusal-guard sweep.
- **Secondary (best-effort):** T2.1 extend Alienated Majesty scraper for artist-talks; T2.2 Libra Books scraper (self-blocks if T0.1 research finds no events page).
- **Tertiary (best-effort):** 10-variant filter-bar redesign under `docs/variants/v12{a..j}/`. Scored `critique(40%)+layout(30%)+audit(20%)+polish(10%)`. Winner promoted to live `docs/` (T3.4). T3.x writes only under `docs/variants/v12<x>/` until T3.4.
- **Quaternary:** T4.1 `scripts/check_event_coverage.py`, T4.2 `docs/COVERAGE.md` per-category counts.
- **Phase 5:** T5.1 full pytest + coverage + `verify_calendar.py` delta-vs-main, T5.2 STATUS handoff.

Research-only tasks (T0.1, T0.2, T3.1, T3.3, T5.1) skip commits/CHANGELOG and write `.overnight/task-result.json` with `status=DONE` directly. GitNexus impact required for `src/processor.py`, `src/scraper.py`, `src/scrapers/alienated_majesty_scraper.py`, `update_website_data.py`.

### 2026-04-18-2 — `main` direct-push (completed, live-verified)
Five regressions from the v12i promotion (`c45fdfd` + `7a477cb` + `2c83a39`):
1. Mobile filter sheet cut off + can't close.
2. Top Picks shows top-N by rating across all events — wants top picks of the week (next 7d).
3. Review expansion unformatted (lost pre-v12i `parseReview()` structured sections).
4. Subtitle leak — `"Sticky chip-drawer with active summary"` was v12i's internal design-note, not a user-facing tagline.
5. About section dropped (restored from `c03f617`); `docs/ABOUT.md` still existed but wasn't referenced from `index.html`.

User explicitly authorized per-task pushes to `main` because each fix must be verifiable live. Per-task contract: commit → push → deploy-wait → live-check via `scripts/check_live_site.py` → `git revert HEAD --no-edit` + push + BLOCK on failure. Never leaves a broken live state.

Live-site checker (T0.1): pyppeteer-based, loads a URL with optional mobile viewport, evaluates JSON spec, exits 0/non-zero. Spec schema `{url, mobile, wait_ms, wait_for_selector, click_before_assert[], asserts[]}`; assertion types `body_contains`, `body_not_contains`, `selector_exists`, `selector_min_count`, `selector_max_count`, `js_truthy`. Each task writes `.overnight/check-T<ID>.json`.

DoD goals verified live:
- Subtitle reads `"Austin cultural events, AI-curated"`.
- About section present with collapsible methodology from `docs/ABOUT.md`.
- Top Picks heading `"TOP PICKS OF THE WEEK"`, only events within next 7d.
- Review panels render with h3/h4 headings + paragraph spacing.
- Mobile filter sheet opens, closes (X button + escape + click-outside), stays within 375×812 viewport.

Tasks: T0.1 (checker + tests), T1.1, T1.2a, T1.2b, T2.1, T2.2, T3.1 (port `parseReview()` from `d13f975:docs/script.js:1157-1207`), T3.2, T4.1, T4.2, T5.1, T5.2. Scope fence: `docs/`, `src/`, `scripts/check_live_site.py`, `tests/test_check_live_site.py`, `CLAUDE.md`, `CHANGELOG.md`, STATUS file. Pyppeteer 2.0.0 already installed. Do NOT edit `docs/variants/v12i/` — archival variant.

CHANGELOG entry template adds `- live-check: passed after <N>s deploy wait`. BLOCKED entry includes attempted + reverted shas + reason. Handoff `STATUS-2026-04-18-2.md`.

### 2026-04-18-3 — `main` direct-push (completed, live-verified)
Nine deeper structural issues raised after 2026-04-18-2 shipped:
1. Filter chips cluttered — replace chip-drawer with search bar + autocomplete on venues/titles/categories.
2. Top Picks not readable — can't click through to the AI review.
3. Merit listings hide logistics — date/time only visible after expand.
4. Unfair low ratings — movies with sparse Perplexity sources default to 5/10; need a "couldn't research this well" surface.
5. One-liner contrast — italic `#d4a574` on white (~2.8:1) fails WCAG AA 4.5:1.
6. Read-aloud TTS regression — added `986877e`, silently removed `c45fdfd` (v12i promotion). Same pattern as About.
7. No persona-driven critique — every run rediscovers regressions by hand.
8. No feature inventory — features dropped silently during redesigns.
9. No venue prospecting — `visual_arts` has 8 events from one aggregator; user wants Perplexity-driven discovery.

Phases:
- **0 — inventory + wishlist seeds (backend):** T0.1 seed `.overnight/feature-inventory.json` with live features + add Feature Inventory section to CLAUDE.md; T0.2 seed `## Venue Wishlist` in README.md.
- **1 — user-visible UX (docs/, live-checked):** T1.1a remove chip-drawer; T1.1b add search bar + grouped suggestions in masthead; T1.2 Top Picks expand w/ review; T1.3 date/time on merit card headers; T1.4 raise one-liner contrast to WCAG AA; T1.5 restore TTS button.
- **2 — review_confidence backend + UI bucket:** T2.1 `review_confidence` signal in `_parse_ai_response`; T2.2 field in all category templates; T2.3 expose in JSON builder; T2.4 cache-aware re-rate of refusal-shaped cached entries; T2.5 render "Pending more research" section for low-confidence reviews; T2.6 harden tests.
- **3 — persona council framework:** T3.1 six persona spec files under `.overnight/personas/`; T3.2 `scripts/persona_critique.py` (LLM council default, `--fast` = DOM-asserts only); T3.3 extend personas with `goals` + `system_prompt` LLM framing.
- **4 — Perplexity venue prospecting:** T4.1 `scripts/prospect_venues.py`; T4.2 run for visual_arts + concert, append to README wishlist; T4.3 harden tests.
- **5 — gate + handoff:** T5.1 final structural gate (fast persona council); T5.2 full LLM council (6 Anthropic calls, ~$0.50); T5.3 `STATUS-2026-04-18-3.md`.

docs/ tasks live-checked with deploy-wait + revert. Backend tasks (`src/`, `scripts/`, `tests/`, `config/`) push without deploy-wait; validate runs immediately. Scope fence: `docs/` (+ PERSONAS.md, PERSONAS-fast.md), `src/processor.py`, `scripts/check_live_site.py`, `scripts/persona_critique.py`, `scripts/prospect_venues.py`, `tests/test_review_confidence.py`, `tests/test_persona_critique.py`, `tests/test_prospect_venues.py`, `update_website_data.py`, `config/master_config.yaml`, `CLAUDE.md`, `CHANGELOG.md`, STATUS file, `README.md` (Venue Wishlist append only), `.overnight/personas/*.json`, `.overnight/feature-inventory.json`. GitNexus impact required for `src/processor.py`, `update_website_data.py`, `src/scrapers/__init__.py`, `src/scraper.py`. Do NOT edit `docs/variants/v12i/`. CHANGELOG entry adds `- live-check: <passed after Ns | n/a (backend)>`.

### 20260419-235117 — `long-run/20260419-235117` (completed)
"Consumption Surface v1" — 28 tasks / 9 phases turning static listings into a subscribable/personalizable product. Handoff `STATUS-20260419-235117.md`. Strategic frame: gstack SCOPE EXPANSION + business-strategy-v2 frameworks (JTBD, Category Design, 7 Powers, Blue Ocean ERRC, AI Factory, Cold Start, Traction Bullseye). Full plan at `~/.claude/plans/use-the-gstack-skills-elegant-adleman.md`.

DoD (must all be true by deadline):
- `docs/calendar.ics` + `docs/top-picks.ics` parse as iCalendar; linked from masthead via `webcal://`.
- `docs/feed.xml` valid RSS/Atom.
- `docs/sitemap.xml` enumerates all pages (index + weekly + venues + people + features).
- Event modals inject JSON-LD `Event` schema; index head has OG + Twitter card meta.
- `#event=<id>` deep-link handler (load + scroll + expand).
- Thumbs up/down + save persist to localStorage; top picks re-rank on taste; "because you liked X" annotation renders.
- `docs/weekly/<yyyy-ww>.html` digest + 5-min audio-brief button (Web Speech API).
- ≥10 `docs/venues/<slug>.html`; `docs/people/<slug>.html` per composer/director/author with ≥2 events.
- `docs/people/<slug>.ics` per-person webcal follow feeds.
- Share button via Web Share API w/ mailto/twitter/clipboard fallbacks.
- Plausible tag + 7 custom events: `cc_subscribe_ics`, `cc_subscribe_rss`, `cc_thumb_up`, `cc_thumb_down`, `cc_save`, `cc_share`, `cc_play_brief`.
- Weekly composer essay at `docs/features/composer-<yyyy-ww>.html`.
- `docs/preview/` populated by pyppeteer screenshot harness.
- ≥18 new feature-inventory entries.

Scope: `scripts/` (build_*.py generators for ics/rss/og/weekly-digest/venues/people/sitemap/wishlist/composer-feature/screenshots), `tests/`, `docs/` (index/script/styles/ABOUT + new `docs/calendar.ics`, `docs/top-picks.ics`, `docs/feed.xml`, `docs/sitemap.xml`, `docs/robots.txt`, `docs/og/`, `docs/weekly/`, `docs/venues/`, `docs/people/`, `docs/features/`, `docs/preview/`, `docs/wishlist.html`), `update_website_data.py` (orchestrate new builders in final step), `CLAUDE.md` + `CHANGELOG.md` fenced blocks only, STATUS file, `.overnight/feature-inventory.json`, `.gitignore`. `src/` read-only except `src/processor.py` for composer-essay branch (T8.1) — GitNexus impact required. Network: LLM calls reuse Perplexity + Anthropic from `.env`. Plausible is a single `<script>` tag.

### 20260421-225013 — `long-run/20260421-225013` (completed)
"Consumption Surface v2" on v1's live foundation. Closes four post-v1 gaps. Handoff `STATUS-20260421-225013.md`. Plan: `~/.claude/plans/use-the-gstack-skills-elegant-adleman.md`.

1. **Rich social share** — extend pick-card share popover from 3 (mailto/Twitter/clipboard) to 9 (Twitter/X, Threads, Bluesky, Mastodon, LinkedIn, WhatsApp, SMS, Email, Copy); replace digest button's bare `mailto:` with same share module. Per-platform `cc_share_<platform>` Plausible events.
2. **Mailing list** — Buttondown (user-confirmed free tier). Masthead signup reads `window.CC_CONFIG.buttondown_endpoint` from `docs/config.json`; "Coming soon" stub fallback when unset; submits fire `cc_subscribe_email`. `docs/archive.html` lists every weekly digest; `docs/subscribed.html` + `docs/unsubscribed.html` exist.
3. **Agent-friendly surfaces** — `docs/llms.txt` + `docs/llms-full.txt`; `docs/api/{events,top-picks,venues,people,categories}.json`; per-event `docs/events/<slug>.json` mirror of JSON-LD; `docs/.well-known/ai-agent.json` with ≥5 endpoints; `docs/robots.txt` allows GPTBot, ClaudeBot, PerplexityBot, CCBot, Google-Extended, Meta-ExternalAgent, Amazonbot.
4. **SEO maximization** — WebSite + Organization + ItemList JSON-LD on index; BreadcrumbList on venue/people/weekly/event-shell pages; `aggregateRating` + `offers.url` in event JSON-LD; canonical + meta description on every page; rel=prev/next on weekly archive; humans.txt.

DoD additions: `docs/ABOUT.md` + `README.md` document mailing list + agent surfaces; ≥12 new feature-inventory entries (total ≥42).

Stdlib only for Python (`json`, `xml.etree.ElementTree`, `html`, `pathlib`). Share-menu icons via unicode or inline SVG. Scope: `docs/` (not `docs/variants/`), `scripts/` (new + extensions), `tests/`, `update_website_data.py` (orchestration only), `config/master_config.yaml` (add `distribution.buttondown_endpoint`), `README.md` (append "For AI agents" + "Subscribe"), `CLAUDE.md` + `CHANGELOG.md` fenced blocks, STATUS file, `.overnight/feature-inventory.json`, `.gitignore`. `src/` read-only.

Commit cadence: two small commits per task (code + CHANGELOG). LLM council active (4 task-level reviewers + 1 run-level); judge `claude-sonnet-4-6`; T6.3 opts out via `[no-council]` (it IS the council run). GitNexus impact required for `docs/script.js` + `update_website_data.py`. Persona-gate tag for T1.1 (share-menu refactor), T2.2 (signup form), T3.4 (AI-crawler allowlist policy).

### 20260422-203219 — `long-run/20260422-203219` (completed 2026-04-23; branched off `main` after v2 FF-merged)
"Persona-Gate Resolution + Calendar Intents v3" — quality pass making v2 persona council's 5/6 LLM FAIL verdicts actionable. Handoff `STATUS-20260422-203219.md`.

**Durable rule driving this run** (saved to memory as `feedback_persona_gate_strict.md`): every persona FAIL (LLM or structural) blocks delivery. Age of the issue is irrelevant. Two valid responses: fix the site, or fix the persona's view. "Pre-existing on main / inherited from v1" is never acceptable.

**Site fixes (9):**
- Venue addresses on every card face.
- "Get Tickets →" CTA inside expanded panel (`.event-ticket-link`).
- Full venue display-names replacing opaque short codes.
- Keyboard-accessible expand: `.event-header` has `role="button"`, `tabindex="0"`, `aria-label`, Enter/Space handler; `.expand-indicator` not `aria-hidden`.
- Mobile hardening: `.subscribe-links flex-wrap`, `.event-title-text word-break`, `.expand-indicator min-width: 32px + flex-shrink: 0`, `#event-search padding-right`, 320px breakpoint.
- 2-line clamp on `.event-oneliner` card face (`-webkit-line-clamp: 2`); full text in expanded panel.

**Harness fixes (4):**
- Share pyppeteer page between `check_live_site.py` and `persona_critique.py` (no fresh `page.goto()` before screenshot).
- `fullPage: True`.
- `DOM_SNIPPET_MAX_BYTES = 40_000` (up from 10 KB).
- `pre_screenshot_actions` replay (scroll/type/click); per-selector ground-truth JSON injected into persona LLM prompt so below-the-fold features aren't misreported missing.

**User ask bundled in:** per-event `docs/events/<slug>.ics` files (valid iCalendar); `PLATFORMS` in `docs/script.js` adds `google-calendar` (→ `calendar.google.com/calendar/render?action=TEMPLATE&...`) and `apple-calendar` (→ `webcal://…/events/<slug>.ics`); both fire `cc_share_<platform>` events.

Outputs: `config/master_config.yaml` venues block gets `address:` per venue; `docs/data.json` + `docs/api/venues.json` entries carry `venue_address` + `venue_display_name`; `docs/events/<slug>.html` JSON-LD `location` has `streetAddress` + `postalCode`; all 6 `.overnight/personas/*.json` updated with `pre_screenshot_actions` + ground-truth-aware `llm.goals`; ≥6 new feature-inventory entries (total ≥48).

**Final gate T5.3:** full LLM persona council returns 6/6 PASS on BOTH structural + LLM layers — zero `Verdict: FAIL` in `docs/PERSONAS.md`. Any remaining FAIL halts via BLOCKED `persona-regression-v3` (no retry, manual triage).

Scope: `config/master_config.yaml` (venue addresses), `docs/` (not `docs/variants/`), `scripts/` (extensions to persona_critique.py + check_live_site.py), `tests/`, `update_website_data.py` (orchestration + venue-metadata lookup), `.overnight/personas/*.json`, `.overnight/feature-inventory.json`, `CLAUDE.md` + `CHANGELOG.md` fenced blocks, STATUS file. `src/` read-only. Stdlib only. No new JS deps — calendar icons are unicode. GitNexus impact required for `update_website_data.py`, `docs/script.js`, `scripts/persona_critique.py`, `scripts/check_live_site.py`. Persona-gate tag for T2.5 (persona goals rewrite), T3.1 (venue display-name is a content-layer shift), T3.3 (keyboard-expand redefines interaction). Commit cadence: two small commits per task (code + CHANGELOG). LLM council active (4 task-level + 1 run-level), judge `claude-sonnet-4-6`; T5.3 opts out via `[no-council]`.

### 20260425-175347 — `long-run/20260425-175347` (in progress)
"Editorial Polish" — 5-task run on the live site. Sibling worktree at `~/Documents/Personal/Culture-Calendar-long-run-20260425-175347`. **Branch-only run**: tasks commit to `long-run/20260425-175347`, no per-task push to `main`; user reviews scorecard + merges manually after `RUN_COMPLETE`. Plan: `~/.claude/plans/ok-so-the-first-idempotent-newt.md`.

Goals (all presentation-layer; `src/` and `update_website_data.py` read-only):

1. **T1 — Hide past events from main listings.** Top Picks already filters to next 7 days at `docs/script.js:1296-1301`; `renderListings(merit)` at `:1303` shows everything. Pass `merit` through a today-anchored filter using the same date-parse pattern (extract a small `isFutureOrToday` helper if duplication is ugly).
2. **T2 — Drop the "Titles" group from search-bar autocomplete.** Surgical edit in `docs/script.js`: remove `titles` bucket (`:1535, 1543, 1548`) and the third `appendSuggestionGroup(...)` call (`:1560`). Search input still narrows listings via `filterEvents()` (title text match unchanged); only the dropdown's Titles category disappears.
3. **T3 — Replace `▶` with thin SVG chevron.** `arrow.textContent = "▶"` at `docs/script.js:1794, 1941` becomes inline SVG (single ~1.5px stroke, currentColor, ~10×10 viewBox). Existing `transform: rotate(90deg)` on `.event-card.is-expanded .expand-indicator` (`docs/styles.css:409`) keeps working.
4. **T4 — Aged-paper background.** `--bg: #fff` (`docs/styles.css:2`) → warm off-white (proposed `#f5efe1`; agent picks final value within the warm-paper range without dropping below ~#ede0c5 to keep AAA contrast on `--ink #111`). Audit `--chip-bg` and explicit `background: #fff` rules; switch to `var(--bg)` where appropriate. Persona-gate tag because palette redesign is a primary-surface shift.
5. **T5 — Final gate.** Pytest green; `STATUS-20260425-175347.md` handoff written; `.overnight/feature-inventory.json` has ≥4 new entries (one per T1..T4); CHANGELOG run-block readable cold. `[no-council]` opt-out — wrap-up task, not feature work.

DoD: zero `.event-card` with date < today's midnight in main listings; search dropdown shows only `Venues` + `Categories` group headers; every `.expand-indicator` contains an `<svg>` (no `▶` literal under `.event-card *`); `getComputedStyle(document.body).backgroundColor` ≠ `rgb(255, 255, 255)`.

Scope: `docs/` (not `docs/variants/`), `.overnight/feature-inventory.json`, `CLAUDE.md` + `CHANGELOG.md` fenced blocks, `STATUS-20260425-175347.md`. `src/`, `update_website_data.py`, `config/`, `scripts/` read-only. Stdlib only. No new deps (no `pip install`, no `npm install`). GitNexus impact required for `docs/script.js` and `docs/styles.css`. Commit cadence: two small commits per task (code + CHANGELOG). LLM council active (4 task-level + 1 run-level reviewers); judge `claude-sonnet-4-6`. T5 opts out via `[no-council]`. T4 carries `[persona-gate]` tag.

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
