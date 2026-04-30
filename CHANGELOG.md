# CHANGELOG

<!-- BEGIN LONG-RUN: 20260430-102637 -->
## Long run — 20260430-102637

Scope: typography overhaul + ballet review fix + classical refresh automation + new LLM reviewers + aggressive nanochat-style minimalism. 38 tasks, 12h budget, branch-only on `long-run/20260430-102637`. Plan: `~/.claude/plans/i-want-to-improve-sparkling-simon.md`.

Per-task entries below — one per completed task, appended by the runner.

### task-1.1 — DONE — 2026-04-30T15:34:52Z
- commit: 3ac999b
- files: src/summary_generator.py, tests/test_summary_generator.py
- summary: `_build_book_prompt` now returns `None` (and the caller in `generate_one_liner_summary` short-circuits with a skip message and returns `None`) when both `book` and `author` are absent from the event dict, replacing the prior `ValueError` raise. The other validation guards (missing title, missing description, sub-50-char analysis, missing event dict) still raise `ValueError` because those represent upstream pipeline failures rather than normal-shape data gaps. Net effect: book-club events that arrive with only a title (e.g. "Book Club at Alienated Majesty") no longer error out the summary stage; they simply skip one-liner generation while the rest of enrichment proceeds. Test coverage added covers both the new None-return paths (no metadata, only-book, only-author) and the still-raising paths (empty title/description/event, short analysis).
- validation: green

### task-1.2 — DONE — 2026-04-30T15:51:30Z
- commit: 627bd63
- files: src/summary_generator.py, tests/test_summary_generator.py
- summary: `_is_specific_event` no longer rejects events solely because the title contains "festival", "workshop", "gala", or "tribute" when the event carries rich metadata (director / book / author / featured_artist / composers). A new `metadata_overridable_indicators` set carves out those four keywords (plus `movie festival` and `auteur festival`) from both the `title_non_specific_indicators` and `series_indicators` rejection loops (substring `in` checks, not regex — task title was loose shorthand), so a "Bergman Festival" with director set, a "Workshop with Pollini" with featured_artist, a "Symphony Gala" with composers, or a "Tribute to Toni Morrison" with author all pass through to summary generation. The short-circuit `has_key_metadata` predicate also gained `composers` so concert events qualify under the same override. Strict rejection still applies for unambiguous non-events (symposium, conference, lecture, seminar, panel discussion, awards ceremony, retrospective) regardless of metadata. Tests cover the four allow-with-metadata paths, three still-reject-without-metadata paths, and two still-reject-even-with-metadata paths for unambiguous formats.
- validation: green
- council-round-1: morning-reviewer FAIL — commit subject said "regex" but implementation is substring matching. Amended subject to suggested "Allow festival/workshop/gala/tribute in titles when metadata present"; CHANGELOG body now explicitly notes substring-vs-regex distinction. Other 3 reviewers passed unchanged.

### task-1.3 — DONE — 2026-04-30T15:49:30Z
- commit: cdd536c
- files: tests/Hyperreal_test_data/event_xxx_return_xander_cage_2026.html (renamed from event_xxx_return_of_xander_cage_2026.html)
- summary: `verify_calendar.py:68` maps the `/events/4-30/xxx-return-of-xander-cage-movie-screening` URL to fixture filename `event_xxx_return_xander_cage_2026.html` (no `_of_`), but the on-disk fixture was committed in `20447c7` as `event_xxx_return_of_xander_cage_2026.html` (with `_of_`), so offline oracle runs returned a 404 from `_hyperreal_mock_get`. Renamed the fixture to match the verify_calendar expectation. No code references the old `_of_` filename anywhere in repo (grep confirmed), so the rename is purely an alignment with the existing mapping — no scraper, test, or script edits needed. The URL slug itself (with `of`) is unchanged; only the local filename drops the `of` to match `verify_calendar.HYPERREAL_SAVED_PATHS`.
- validation: green

### task-1.4 — DONE — 2026-04-30T15:55:27Z
- commit: f9a9074
- files: scripts/verify_calendar.py
- summary: Both Weekend window checks (`Site: This Weekend` in `check_site_views`, `data.json: Weekend` in `check_data_json_site_views`) now emit a passing `_ok(...)` with a "tolerated" detail string when the Fri..Sun window contains zero events, instead of `_fail(...)`. Rationale: the `Site:` view scrapes only AFS+Hyperreal, so an upcoming weekend with no scheduled screenings at those two venues was forcing offline verify to exit non-zero on otherwise-healthy runs (observed today, Thu 2026-04-30: Fri 5/1..Sun 5/3 had zero AFS/HR events while data.json's cross-venue weekend window had 19). Today and This Week remain hard `_fail` gates because empty values there indicate a real data outage; the cross-venue `data.json` Today/This Week checks also stay strict. Verified offline: 22/22 checks now pass and `verify_calendar.py --offline` exits 0.
- validation: green

### task-1.5 — Decision: do not merge `claude-code-review.yml`
Triage outcome for `.github/workflows/claude-code-review.yml`. The file is NOT in `main`, NOT in this run's branch, and NOT in any commit reachable from `long-run/20260430-102637`. It exists only on the unmerged GitHub-UI install branches `origin/add-claude-github-actions-1777167371353` and `origin/add-claude-github-actions-1777497502714` (both committed `0ee35d3` / `297189d` from the Anthropic Claude GitHub app, Apr 29). Local `.github/workflows/` continues to contain only `complete-data-wipe-reload.yml`, `pr-validation.yml`, `update-calendar.yml`. So "remove" is moot — there is nothing in this tree to remove.

**Recommendation to user: close those two install PRs without merging.** Rationale: (a) the workflow's trigger is `pull_request: [opened, synchronize, ready_for_review, reopened]` invoking `anthropics/claude-code-action@v1` against `secrets.CLAUDE_CODE_OAUTH_TOKEN`, so every push to any PR branch (including the noisy codex/* and 1m6mz3-codex/* speculative branches that already populate `git branch -r`) bills against the OAuth token — lopsided cost-vs-value for a solo-maintainer repo. (b) Phase 4 of this run is building two local LLM reviewers (`personas/code-review/review-quality.json` T4.2 and `personas/code-review/repo-minimalism.json` T4.3) wired into `.githooks/pre-push` (T4.4) plus a manual `scripts/review_quality_check.py` command (T4.5); same review coverage, zero cloud spend, runs only on the user's push not on every speculative branch update. (c) Run-level minimalism principle: CLAUDE.md `### Hard constraints` already forbids new paid-API deps, and the karpathy/nanochat aesthetic the repo-minimalism reviewer is being trained on would itself flag a third LLM-driven reviewer as accretion. (d) Plan default at `~/.claude/plans/i-want-to-improve-sparkling-simon.md` T1.5: "leave alone unless it's actively harmful" — the workflow is not actively harmful (it isn't in any merged tree and produces no failing run on `main`), so "leave alone" maps to "do not promote." `[persona-gate]` tag applied per the plan because declining to add a future review-gate is itself a gate-config decision.

### task-1.5 — DONE — 2026-04-30T15:57:36Z
- commit: 465c12b
- files: CHANGELOG.md
- validation: green

### task-2.1 — DONE — 2026-04-30T16:02:08Z
- commit: 1510b62
- files: src/scrapers/ballet_austin_scraper.py
- validation: green

### task-2.2 — DONE — 2026-04-30T16:03:56Z
- commit: 4cb1cdb
- files: src/processor.py, tests/test_processor.py
- validation: green

### task-2.3 — DONE — 2026-04-30T16:07:11Z
- commit: a4d537a
- files: src/summary_generator.py, tests/test_summary_generator.py
- validation: green

### task-2.4 — DONE — 2026-04-30T16:10:00Z
- commit: 617f912
- files: tests/test_ballet_dance_review.py
- validation: green

### task-2.5 — DONE — 2026-04-30T16:16:14Z
- commit: 14a4caa
- files: docs/data.json, cache/summary_cache.json
- validation: green

### task-3.1a — DONE — 2026-04-30T16:24:00Z
- commit: 6d62375
- files: scripts/refresh_classical_data.py, tests/test_refresh_classical_data.py
- validation: green

### task-3.1b — DONE — 2026-04-30T16:32:00Z
- commit: f5ead36
- files: scripts/refresh_classical_data.py, config/master_config.yaml
- validation: green

### task-3.2 — DONE — 2026-04-30T16:45:00Z
- commit: 22409d0
- files: .github/workflows/refresh-classical-data.yml
- validation: green

### task-3.3 — DONE — 2026-04-30T16:55:00Z
- commit: a85c1c7
- files: docs/classical_data.json, docs/ballet_data.json
- validation: green
- notes: ran `refresh_classical_data.py --dry-run --use-perplexity --venue austinSymphony` end-to-end against the live Perplexity API; the LLM returned one well-formed event matching an entry already on disk (Masterworks 7, 2026-04-10). A full --venue all run is non-deterministic — Perplexity sporadically responds with `{events: []}` for individual venues which (correctly) raises LLMFetchError and aborts the pipeline. To avoid clobbering the manually curated season data with sparser LLM output, this commit only refreshes the schema metadata: bumps classical_data.json `lastUpdated` to 2026-04-30 and adds the optional `lastUpdated`/`season` keys to ballet_data.json so both files share the same shape. Event arrays unchanged.

### task-3.4 — DONE — 2026-04-30T16:45:54Z
- commit: 150d183
- files: CLAUDE.md, README.md
- validation: green

### task-4.1 — DONE — 2026-04-30T16:48:55Z
- commit: 4a6b304
- files: personas/live-site/comprehensiveness-user.json, personas/live-site/continuity-user.json, personas/live-site/logistics-user.json, personas/live-site/mobile-user.json, personas/live-site/review-reader.json, personas/live-site/search-user.json, config/feature-inventory.json, scripts/persona_critique.py, scripts/require_persona_approval.py
- validation: green

### task-4.2 — DONE — 2026-04-30T16:55:23Z
- commit: 1037ab5
- files: personas/code-review/review-quality.json
- validation: green

### task-4.3 — DONE — 2026-04-30T16:58:40Z
- commit: 50b87dc
- files: personas/code-review/repo-minimalism.json
- validation: green

### task-4.4 — DONE — 2026-04-30T17:04:32Z
- commit: c6665a5
- files: .githooks/pre-push
- validation: green

### task-4.5 — DONE — 2026-04-30T17:11:24Z
- commit: 49bf4bf
- files: scripts/review_quality_check.py
- validation: green

### task-4.6 — DONE — 2026-04-30T17:15:09Z
- commit: 3f3e0c7
- files: personas/README.md, CLAUDE.md, config/feature-inventory.json
- validation: green

### task-5.1 — DONE — 2026-04-30T17:21:57Z
- commit: 02675a7
- files: docs/TYPOGRAPHY.md
- validation: green

### task-5.2 — DONE — 2026-04-30T17:24:34Z
- commit: 851bd76
- files: docs/index.html, docs/styles.css
- validation: green

### task-5.3 — DONE — 2026-04-30T17:26:29Z
- commit: 80c6705
- files: docs/styles.css
- validation: green

### task-5.4 — DONE — 2026-04-30T17:30:17Z
- commit: 82e7849
- files: docs/styles.css
- validation: green

### task-5.5 — DONE — 2026-04-30T17:32:50Z
- commit: 693f2d6
- files: docs/styles.css
- validation: green

### task-5.6 — DONE — 2026-04-30T17:35:40Z
- commit: 5920ed4
- files: docs/styles.css, config/feature-inventory.json
- validation: green

### task-6.1 — DONE — 2026-04-30T17:42:17Z
- commit: 23fdf56
- files: .gitignore, archive/runs/STATUS-2026-04-16.md, archive/runs/STATUS-2026-04-17.md, archive/runs/STATUS-2026-04-18-2.md, archive/runs/STATUS-2026-04-18-3.md, archive/runs/STATUS-2026-04-18.md, archive/runs/STATUS-2026-04-19.md, archive/runs/STATUS-20260419-235117.md, archive/runs/STATUS-20260421-225013.md, archive/runs/STATUS-20260422-203219.md, archive/runs/STATUS-20260425-175347.md, after_merge_run.log, quick_update.log, update_after_summary_patch.log, update_final.log, update_fix_movies.log, update_full.log, update_run_1775348131.log
- validation: green

### task-6.2 — DONE — 2026-04-30T17:44:22Z
- commit: c57cd3e
- files: CLAUDE.md, archive/CLAUDE-runs.md
- validation: green

### task-6.3 — DONE — 2026-04-30T18:25:18Z
- commit: 30fc1fb
- files: CHANGELOG.md, archive/CHANGELOG-history.md
- validation: green
<!-- END LONG-RUN: 20260430-102637 -->

<!-- BEGIN LONG-RUN: 20260425-175347 -->
## Long run — 20260425-175347

*Branch:* `long-run/20260425-175347` · *Started:* 2026-04-25T17:53:47Z · *Deadline:* 2026-04-25T23:53:47Z (6h) · *Scope:* Editorial Polish (5 tasks — past-events filter, search-titles drop, NYT chevron, aged-paper bg, final gate)

### task-SCAFFOLD — DONE — 2026-04-25T17:53:47Z
- queue.tsv written with 5 tasks (T1, T2, T3, T4, T5)
- runner-prompt.txt copied from long-run skill template
- personas copied (4 task-level: scope-fence-auditor, test-integrity-critic, regression-sentinel, morning-reviewer; 1 run-level: run-summary-skeptic)
- CLAUDE.md run-log entry appended
- CHANGELOG.md fenced block prepended

### task-T1 — DONE — 2026-04-25T23:23:29Z
- commit: 685b09c
- files: docs/script.js, .overnight/feature-inventory.json
- summary: Added isFutureOrToday(ev, now) helper; renderAll() now mutates merit through it before rendering, so renderListings(merit) and downstream picks both see only events with showings[0].date >= today's midnight (reusing the Top Picks 7-day-window date-parse pattern).
- validation: green

### task-T2 — DONE — 2026-04-25T23:26:33Z
- commit: 4e6a581
- files: docs/script.js, .overnight/feature-inventory.json
- summary: Removed the titles bucket from collectSuggestions() and the third appendSuggestionGroup("Titles", ...) call in renderSuggestions(); search autocomplete dropdown now lists only Venues + Categories groups while typing into #event-search still narrows listings via the unchanged title-text branch in filterEvents().
- validation: green

### task-T3 — DONE — 2026-04-25T23:29:33Z
- commit: f032697
- files: docs/script.js, docs/styles.css, .overnight/feature-inventory.json
- summary: Replaced both `arrow.textContent = "▶"` assignments in buildPickCard and buildListingCard with an inline SVG polyline chevron (viewBox 0 0 10 10, stroke-width 1.5, currentColor); added a `.expand-indicator svg { width:14px; height:14px; display:block }` rule plus inline-flex centering on `.expand-indicator` so the chevron sizes cleanly on mobile while the existing `.event-card.is-expanded .expand-indicator { transform: rotate(90deg) }` rotation continues to work on the parent span.
- validation: green

### task-T4 — DONE — 2026-04-25T23:33:15Z
- commit: ad74205
- files: docs/styles.css, .overnight/feature-inventory.json
- summary: Switched `:root` design tokens `--bg` and `--chip-bg` from `#fff` to `#f5efe1` (warm aged-paper off-white) so the body, event-card, and form-input backgrounds inherit a newsprint tone via the existing `var(--bg)` references; verified WCAG AAA contrast on `--ink #111` (~15.8:1) and AA on `--muted #666` (~5.3:1) against the new background.
- validation: green

### task-T5 — DONE — 2026-04-25T23:36:30Z
- commit: 562d9e5
- files: STATUS-20260425-175347.md
- summary: Wrote STATUS-20260425-175347.md handoff at repo root (disposition RUN_COMPLETE, per-task code+changelog SHAs for T1..T4, suggested next actions, verification checklist); pytest green at 777 passed / 22 skipped; verified `.overnight/feature-inventory.json` has 4 new entries (`hide-past-events`, `search-suggestions-no-titles`, `expand-chevron-svg`, `aged-paper-bg`, total 65) and the CHANGELOG run-block reads cold.
- validation: green

<!-- END LONG-RUN: 20260425-175347 -->

<!-- BEGIN LONG-RUN: 20260422-203219 -->
## Long run — 20260422-203219

*Branch:* `long-run/20260422-203219` · *Started:* 2026-04-22T20:32:19Z · *Deadline:* 2026-04-24T08:32:21Z (36h) · *Scope:* Persona-Gate Resolution + Calendar Intents v3 (24 tasks across 6 phases — venue addresses, per-event ICS, Google/Apple Calendar share intents, persona harness truthfulness fixes, card-face logistics, mobile hardening, 6/6 persona council gate)

### task-SCAFFOLD — DONE — 2026-04-22T20:32:19Z
- queue.tsv written with 24 tasks
- runner-prompt.txt copied from long-run skill template
- personas copied from v2 (4 task-level + 1 run-level)
- CLAUDE.md fenced block appended
- CHANGELOG.md fenced block prepended
- .gitignore v3 runtime patterns appended

### task-T0.1 — DONE — 2026-04-22T20:37:48Z
- commit: 9ebd4a766f92eeef31e68e7db8a832b8895cd4f2
- files: config/master_config.yaml, tests/test_venue_addresses.py
- validation: green

### task-T0.2 — DONE — 2026-04-22T21:42:00Z
- commit: b7b36cb2698948a3e8a1d68768a78ebdb0de9085
- files: update_website_data.py
- validation: green

### task-T0.3 — DONE — 2026-04-22T21:54:30Z
- commit: a1a75778e2b9c4c3c7a1511354bcf73e39e24bd7
- files: scripts/build_api_json.py, docs/api/venues.json, tests/test_build_api_json.py
- validation: green

### task-TA.1 — DONE — 2026-04-23T03:40:40Z
- commit: db647fc8c6adce373d6eb0c0d7fc5630297c3a0a
- files: scripts/persona_critique.py, scripts/bench_personas.py, tests/test_persona_critique_bedrock.py
- validation: green

### task-T0.4 — DONE — 2026-04-23T04:35:51Z
- commit: 52bba7f6cf691ebb4e274c9a0e53bed0edab6a5d
- files: scripts/build_event_shells.py, tests/test_build_event_shells.py, docs/events/*.html (229 shells regenerated)
- summary: Regenerated 229 event shells with venue display names, streetAddress/postalCode in PostalAddress blocks, offers, aggregateRating, and BreadcrumbList JSON-LD. Adds _parse_postal_address and _load_venue_metadata_from_config helpers; grows test suite from 15 to 33 cases.
- validation: green

### task-T1.1 — DONE — 2026-04-23T05:02:10Z
- commit: 7c71e94bdeb792bb26c2cdf045262f051dc3d932
- files: scripts/build_event_ics.py, tests/test_build_event_ics.py, docs/events/*.ics (229 per-event ICS files)
- validation: green

### task-T1.2 — DONE — 2026-04-23T04:56:55Z
- commit: 6d62ee2af8c71c83434c56034d333ceec71d809a
- files: update_website_data.py
- validation: green

### task-T1.3 — DONE — 2026-04-23T05:02:23Z
- commit: baf68f8178176c86a9fb5bac4aada9636800fad4
- files: docs/script.js
- validation: green

### task-T1.4 — DONE — 2026-04-23T05:23:15Z
- commit: 9874b0a109052a3d472b034e440cdb881a7117e9
- files: docs/script.js
- summary: Added Apple Calendar platform to the PLATFORMS share-menu registry using a webcal:// URL pointing at the per-event .ics file under docs/events/<slug>.ics (emitted by T1.1); gated by appliesTo(shareable.icsUrl) so per-event shares surface it and weekly-digest shares don't; wired Plausible tracking as cc_share_apple_calendar via the existing id→underscore slug path.
- validation: green

### task-T2.1 — DONE — 2026-04-23T05:36:44Z
- commit: 98ba2137284b1d3e41186f57485d0da93ce31005
- files: scripts/check_live_site.py, scripts/persona_critique.py, tests/test_persona_critique_shared_page.py
- summary: Unified persona critique into a single pyppeteer session (one page.goto per persona instead of two back-to-back loads) so the assert phase and the screenshot phase share DOM state. Fixes the below-the-fold false-negatives v2's council flagged — personas were reporting "section missing" when the section existed but was merely scrolled out of view on the second, independent navigation. Legacy two-session capture_fn path preserved for bench_personas.py backward-compat; new shared-page contract covered by tests/test_persona_critique_shared_page.py.
- validation: green

### task-T3.1 — DONE — 2026-04-23T06:19:54Z
- commit: a6256dde008d26d3717951460256e2b09b6c0ecc (code), 6bbb0df1dccf0f3beca50a0e811b032b1f8a0b9a (tests)
- files: docs/script.js, docs/styles.css, tests/test_venue_card_rendering.py
- summary: buildPickCard and buildListingCard now surface venue_display_name as the primary venue label (falling back to the raw venue field) and append a new .event-venue-address line below the subtitle whenever the event carries a street address; matching CSS rule added to docs/styles.css. Test coverage in tests/test_venue_card_rendering.py extracts each card-builder body and asserts (1) the venue_display_name || venue fallback, (2) the conditional .event-venue-address render with ev.venue_address as textContent, (3) that the address node is gated on if (ev.venue_address) so no empty line leaks, and (4) that .event-venue-address has a stylesheet rule — addressing the council's NO_TEST_COVERAGE_FOR_BEHAVIOR finding without introducing a pyppeteer dependency.
- validation: green

### task-T3.2 — DONE — 2026-04-23T06:38:12Z
- commit: 5ebec75d28a833687ba2f4428ef1cf0b13f4b821
- files: docs/script.js, docs/styles.css
- validation: green

### task-T3.3 — DONE — 2026-04-23T06:48:54Z
- commit: 5458bc5e9dc0077ad4fe9a864655fabca1d3a418
- files: docs/script.js
- validation: green

### task-T3.4 — DONE — 2026-04-23T07:03:53Z
- commit: fb8574be04060ded34072b22af9d22a8a42a412b
- files: docs/styles.css
- validation: green

### task-T3.5 — DONE — 2026-04-23T07:21:45Z
- commit: 60f18844c55637f33dd8ced80d8cab36720f496d
- files: .overnight/feature-inventory.json
- validation: green

### task-T4.1 — DONE — 2026-04-23T07:29:39Z
- commit: 30fc8b024752de92cbce8b52babe25086b6c6ed8
- files: docs/styles.css
- validation: green

### task-T1.5 — DONE — 2026-04-23T15:36:01Z
- commit: 6df2b2ddfc0250e9be7bc273fe4d63d988145f2c
- files: .overnight/feature-inventory.json
- validation: green

### task-T2.2 — DONE — 2026-04-23T15:44:18Z
- commit: caf94985a7469226d739a91edff0c165afc916e5
- files: scripts/persona_critique.py, tests/test_persona_fullpage_screenshot.py
- validation: green

### task-T2.3 — DONE — 2026-04-23T15:56:47Z
- commit: 40a1976ddeecf7ed64fc688ba5349e95039dd418
- files: scripts/check_live_site.py, tests/test_check_live_site_pre_actions.py
- validation: green

### task-T2.4 — DONE — 2026-04-23T16:25:00Z
- commit: 82dda4d88c12e5442228eba79bd610e293beec34
- files: scripts/check_live_site.py, scripts/persona_critique.py, tests/test_persona_ground_truth.py
- validation: green

### task-T2.5 — DONE — 2026-04-23T16:46:37Z
- commit: 21fe849c457f7a42973c20637b4ab304f3d63ced
- files: .overnight/personas/comprehensiveness-user.json, .overnight/personas/continuity-user.json, .overnight/personas/logistics-user.json, .overnight/personas/mobile-user.json, .overnight/personas/review-reader.json, .overnight/personas/search-user.json
- validation: green

### task-T5.1 — DONE — 2026-04-23T16:59:43Z
- commit: 23c316f5aba7f0a0c3c9a0c90140e339d8bbda1d
- files: .overnight/feature-inventory.json
- validation: green

### task-T5.2 — DONE — 2026-04-23T18:15:00Z
- commit: 67ca88c93f7457cd06c72f8ce8f742977d998fac
- files: docs/PERSONAS-fast.md, scripts/persona_critique.py
- validation: green

### task-T5.3 — DONE — 2026-04-23T19:15:00Z
- commit: 32579e8
- files: .overnight/personas/search-user.json, .overnight/personas/logistics-user.json, docs/script.js, docs/data.json, docs/PERSONAS.md, scripts/backfill_venue_metadata.py, tests/test_persona_spec_consistency.py, .gitignore, .long-run/20260422-203219/queue.tsv
- validation: green (6/6 LLM PASS; 0 Verdict.*FAIL)
- summary: Closed the strict persona gate by fixing three stacked issues — (a) search-user persona double-typed "Para" via assert+pre_actions producing "ParaPara" vs intermediate ground truth; dropped the redundant pre_actions; (b) logistics-user asserts didn't include .event-venue-address so the LLM couldn't ground-truth verify it; added the assert plus system-prompt naming of venue DOM nodes; (c) docs/script.js:groupEvents() dropped venue_display_name + venue_address when rebuilding event dicts by title; widened the whitelist. Backfilled venue metadata into 229 events of stale docs/data.json via new scripts/backfill_venue_metadata.py. Added tests/test_persona_spec_consistency.py as regression guard on "asserts and pre_actions may not both drive the same input selector" invariant.

### task-T5.4 — DONE — 2026-04-23T19:45:00Z
- commit: 8086dc8
- files: STATUS-20260422-203219.md, .long-run/20260422-203219/queue.tsv
- validation: green
- summary: Final handoff for long-run 20260422-203219. Documents 26/26 tasks DONE, the T5.3 halt-and-recover flow, per-task commit SHAs, verification checklist, and merge instructions.

<!-- END LONG-RUN: 20260422-203219 -->

Older runs (20260421-225013 and earlier) live in `archive/CHANGELOG-history.md`.
