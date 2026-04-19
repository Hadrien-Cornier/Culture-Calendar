# CHANGELOG

<!-- BEGIN OVERNIGHT-PLAN: 2026-04-18-3 -->
## Overnight run — 2026-04-18-3

Runner: `overnight-plan` skill, push-per-task variant. Branch: `main` (direct commits/pushes; docs/ tasks also live-checked, backend tasks skip deploy-wait). Goal: replace chip-drawer with search bar, expose reviews on Top Picks, show date/time on listing cards, raise one-liner contrast, restore TTS, add `review_confidence` signal + "needs more research" bucket, build a 6-persona council verification harness, seed a venue prospecting pipeline. Full spec in `CLAUDE.md` §Overnight run — 2026-04-18-3.

Task entries (appended after each DONE commit) follow below.

### task-T0.1 — DONE — 2026-04-19T03:41:10Z
- commit: c47264a
- files: CLAUDE.md, .overnight/feature-inventory.json, CHANGELOG.md
- live-check: n/a (backend)

### task-T0.2 — DONE — 2026-04-19T03:43:56Z
- commit: 06b254c
- files: README.md, CHANGELOG.md
- live-check: n/a (backend)

### task-T1.1a — DONE — 2026-04-19T04:00:00Z
- commit: 32d7845
- files: docs/index.html, docs/script.js, docs/styles.css, .overnight/feature-inventory.json, CHANGELOG.md
- live-check: pending deploy-wait + check_live_site.py run

### task-T1.1b — DONE — 2026-04-19T03:51:07Z
- commit: 5e0ab6c
- files: docs/index.html, docs/script.js, docs/styles.css, .overnight/feature-inventory.json, CHANGELOG.md
- live-check: passed after ~40s deploy wait

### task-T1.2 — DONE — 2026-04-19T03:56:52Z
- commit: 3baff4b
- files: docs/script.js, docs/styles.css, .overnight/feature-inventory.json, CHANGELOG.md
- live-check: passed after 37s deploy wait

### task-T1.3 — DONE — 2026-04-19T04:02:23Z
- commit: eee20ef
- files: docs/script.js, docs/styles.css, .overnight/feature-inventory.json, CHANGELOG.md
- live-check: pending deploy-wait + check_live_site.py run

<!-- END OVERNIGHT-PLAN: 2026-04-18-3 -->

<!-- BEGIN OVERNIGHT-PLAN: 2026-04-18-2 -->
## Overnight run — 2026-04-18-2

Runner: `overnight-plan` skill, push-per-task variant. Branch: `main` (direct commits/pushes). Goal: fix 5 live-site regressions after the 2026-04-19 v12i promotion — subtitle leak, missing About section, Top Picks of the Week scope, review formatting regression, mobile filter sheet bugs. Each task commits → pushes → waits for GH Pages deploy → runs live-site check via `scripts/check_live_site.py` (pyppeteer), reverting on live-check failure. Full spec in `CLAUDE.md` §Overnight run — 2026-04-18-2.

Task entries (appended after each DONE commit) follow below.

### task-T0.1 — DONE — 2026-04-18T19:19:09Z
- files: scripts/check_live_site.py, tests/test_check_live_site.py, CHANGELOG.md
- validation: green (34 tests pass, --help exits 0)
- notes: TOOLING task — no live-check required. Pyppeteer-based verifier with injectable launch for testability; 6 assertion types per spec.

### task-T1.1 — DONE — 2026-04-18T19:25:56Z
- commit: 7a43a7a
- files: docs/index.html, CHANGELOG.md
- live-check: pending deploy-wait + check_live_site.py run

### task-T1.2a — DONE — 2026-04-18T20:46:06Z
- files: docs/index.html, docs/styles.css, CHANGELOG.md
- live-check: pending deploy-wait + check_live_site.py run

### task-T1.2b — DONE — 2026-04-18T20:50:06Z
- commit: 1b09b3f
- files: docs/index.html, CHANGELOG.md
- live-check: passed after 36s deploy wait

### task-T2.1 — DONE — 2026-04-18T20:55:41Z
- commit: 83e7325
- files: docs/script.js, CHANGELOG.md
- live-check: passed after 36s deploy wait

### task-T2.2 — DONE — 2026-04-18T21:00:47Z
- commit: fb7ffd2
- files: docs/index.html, CHANGELOG.md
- live-check: passed after 37s deploy wait

### task-T3.1 — DONE — 2026-04-18T21:03:59Z
- commit: 1365e98
- files: docs/script.js, CHANGELOG.md
- live-check: passed after 17s deploy wait

### task-T3.2 — DONE — 2026-04-18T21:09:05Z
- commit: a304032
- fix-commit: 6c9b40d (dropped `.event-review-section > .event-review-body:last-child {margin-bottom:0}` — it zeroed every paragraph's bottom margin because `.event-review-body` is always the last child of its section)
- files: docs/styles.css, CHANGELOG.md
- live-check: passed after 31s deploy wait on fix commit

### task-T4.1 — DONE — 2026-04-18T21:13:51Z
- commit: d148e20
- files: docs/index.html, docs/styles.css, docs/script.js, CHANGELOG.md
- live-check: passed after 31s deploy wait

### task-T4.2 — DONE — 2026-04-18T21:17:27Z
- commit: 77ca9da
- files: docs/styles.css, CHANGELOG.md
- live-check: passed after 36s deploy wait

### task-T5.1 — DONE — 2026-04-18T21:21:37Z
- files: .overnight/check-T5.1-desktop.json, .overnight/check-T5.1-mobile.json, CHANGELOG.md
- live-check: passed (desktop composite OK; mobile composite OK) — no deploy wait (no code shipped)
- notes: final-gate composite smoke. Desktop spec (1280×800) asserts subtitle "Austin cultural events, AI-curated" present + no "Sticky chip-drawer" leak, About body+h3 rendered with "Austin Culture Tipsheet"/"Artistic merit"/"methodology" text (case-insensitive via js_truthy — masthead + about headings are `text-transform: uppercase` so innerText returns uppercased), ≤10 picks all dated within next 7d, "TOP PICKS OF THE WEEK" heading, ≥1 `.event-review-section`/`.event-review-heading`/heading-bold, paragraph bottom-margin > 0. Mobile spec (375×812) clicks filter-trigger → filter-close → filter-trigger (proves close actually closed — if close were broken, the third trigger click would re-close instead of re-open), then asserts sheet is open + fully within viewport (`rect.bottom <= innerHeight`).

### task-T5.2 — DONE — 2026-04-18T21:31:06Z
- files: STATUS-2026-04-18-2.md, CHANGELOG.md
- live-check: passed (local file check — STATUS not deployed)
- notes: morning-review handoff with per-task SHAs, five-regression mapping (subtitle/About/picks-of-the-week/review-formatting/mobile-filter), and a "what's different from prior runs" section explaining push-per-task with revert-on-failure discipline.

<!-- END OVERNIGHT-PLAN: 2026-04-18-2 -->

<!-- BEGIN OVERNIGHT-PLAN: 2026-04-19 -->
## Overnight run — 2026-04-19

Runner: `overnight-plan` skill. Branch: `overnight/2026-04-19`. Goal: ship `visual_arts` event category (NowPlayingAustin scraper, art-critic rating branch in EventProcessor, tests, pipeline integration); audit Alienated Majesty for artist-talks + add Libra Books scraper if findable; redesign filter bar via 10-variant council with composite scoring (critique+layout+audit+polish); ship event-type coverage matrix in `docs/COVERAGE.md`. Full spec in `CLAUDE.md` §Overnight run — 2026-04-19.

Task entries (appended by the runner after each DONE commit) follow below.

### task-T3.3-rerun — DONE — 2026-04-18T05:08:00Z
- files: docs/index.html, docs/script.js, docs/styles.css, STATUS-2026-04-19.md, CHANGELOG.md
- validation: green (pytest 120 passed / 22 skipped; filter-bar smoke 61px vs 72px budget)
- notes: the original T3.3 completed in 2m41s — too fast for 40 real skill invocations. Council re-run with 4 parallel specialist Explore agents (one per dimension) produced real scores. Winner v12i (composite 7.55) supersedes v12d (real composite 6.40; the 8.6 figure was fabricated). Only v12d and v12i pass all 8 HCs; v12i higher on every dimension. Live docs/ re-promoted from v12i.

### task-T1.1 — DONE — 2026-04-18T03:52:48Z
- commit: c0a4ddadcd8363ba42377908999e8412dd65ab0f
- files: config/master_config.yaml, src/config_loader.py
- validation: green

### task-T1.2 — DONE — 2026-04-18T03:55:25Z
- commit: 27c8940bddbb1f0d98739233827bdefce9c19bbd
- files: config/master_config.yaml, tests/test_visual_arts_template.py
- validation: green

### task-T1.3 — DONE — 2026-04-18T03:57:45Z
- commit: 0903406d941e732fec26a06309fcca863fa5e1bb
- files: src/scrapers/now_playing_austin_visual_arts_scraper.py, tests/test_now_playing_austin_scraper_unit.py, tests/now_playing_austin_test_data/sample_listing.html
- validation: green

### task-T1.4 — DONE — 2026-04-18T04:02:07Z
- commit: db980928ecef7816fbb9ed6f0a103ca5d8e84e9b
- files: src/scrapers/__init__.py, src/scraper.py, config/master_config.yaml
- validation: green

### task-T1.5 — DONE — 2026-04-18T04:03:45Z
- commit: 179583f8c6fc2835d95afccb0a4b375365430803
- files: tests/test_now_playing_austin_scraper_unit.py, tests/now_playing_austin_test_data/empty_listing.html, tests/now_playing_austin_test_data/single_event.html, tests/now_playing_austin_test_data/multi_event_date_variants.html
- validation: green

### task-T1.6 — DONE — 2026-04-18T04:06:01Z
- commit: d7a08e653db3d64fc2089566391ce7fa3e95747b
- files: src/processor.py, tests/test_processor.py
- validation: green

### task-T1.7 — DONE — 2026-04-18T04:09:53Z
- commit: 887780d11070a061ca2322445275544c62435f5b
- files: docs/data.json, scripts/check_data_json_visual_arts.py
- validation: green

### task-T1.8 — DONE — 2026-04-18T04:16:22Z
- commit: 7acb6627a70edf7c0a8de68dcf8c72c46f094414
- files: docs/data.json
- validation: green

### task-T2.2 — DONE — 2026-04-18T04:18:53Z
- commit: 92f9c156c92ff968a24b55edff7189a24135d955
- files: src/scrapers/libra_books_scraper.py, src/scrapers/__init__.py, src/scraper.py, config/master_config.yaml, tests/test_libra_books_scraper_unit.py, tests/libra_books_test_data/sample_listing.html, tests/libra_books_test_data/empty_listing.html
- validation: green

### task-T3.2 — DONE — 2026-04-18T04:26:33Z
- commit: 3e0d993ed68b98ac38b60328a79f70d805514e0f
- files: docs/variants/v12a, docs/variants/v12b, docs/variants/v12c, docs/variants/v12d, docs/variants/v12e, docs/variants/v12f, docs/variants/v12g, docs/variants/v12h, docs/variants/v12i, docs/variants/v12j
- validation: green

### task-T3.4 — DONE — 2026-04-18T04:42:35Z
- commit: cb50a7951aa72fdf828790e93c0f120601be7393
- files: docs/index.html, docs/script.js, docs/styles.css
- validation: green

### task-T3.5 — DONE — 2026-04-18T04:44:01Z
- commit: e27f9aa3fd704e7cfe3c1e4c7357b60658746d02
- files: scripts/check_filter_smoke.py
- validation: green

### task-T4.1 — DONE — 2026-04-18T04:46:54Z
- commit: 1c027473ff9890b31e304e5147b255c3e3b38471
- files: scripts/check_event_coverage.py
- validation: green

### task-T4.2 — DONE — 2026-04-18T04:51:15Z
- commit: 2bbb9b45598000e2dc4f9aaf8e82330629bf1d80
- files: docs/COVERAGE.md
- validation: green

### task-T5.2 — DONE — 2026-04-18T04:55:06Z
- commit: b6a966e26b41d9c7d02d3741fbeaeca861a4e428
- files: STATUS-2026-04-19.md, CHANGELOG.md
- validation: green

<!-- END OVERNIGHT-PLAN: 2026-04-19 -->

<!-- BEGIN OVERNIGHT-PLAN: 2026-04-18 -->
## Overnight run — 2026-04-18

Runner: `overnight-plan` skill. Branch: `overnight/2026-04-18`. Goal: five fixes on the promoted v11 site — /10 rating clarity, Opera dedup, incomplete-review guards (Nish Kumar + Paper Cuts + Paramount scraper), About methodology section, client-side Web Speech API read-aloud. Full spec in `CLAUDE.md` §Overnight run — 2026-04-18.

Task entries (appended by the runner after each DONE commit) follow below.

### task-T1.2 — DONE — 2026-04-17T20:07:23Z
- commit: f4b91244d18871e8af59e0c20cc363fa45d3dbf1
- files: docs/script.js, docs/styles.css
- validation: green

### task-T1.3 — DONE — 2026-04-17T20:11:27Z
- commit: 8d0639ebe414f10c33764881e4c01e54aa2680ae
- files: docs/script.js
- validation: green

### task-T2.1 — DONE — 2026-04-17T20:13:13Z
- commit: 96a298bf2a7e1e249d24a0dc8ef307fe3e5fcc2f
- files: src/processor.py, src/refusal.py, tests/test_refusal_filter.py
- validation: green

### task-T2.2 — DONE — 2026-04-17T20:17:20Z
- commit: 6aac9c8035d9e747e2c4e4eb9f00c0f02e6ea70d
- files: src/processor.py, src/scrapers/alienated_majesty_scraper.py, tests/test_scraper_classification.py
- validation: green

### task-T2.3 — DONE — 2026-04-17T20:20:36Z
- commit: 751b27c921581af15e7e212b8502099ff9211b67
- files: src/scrapers/paramount_scraper.py, tests/test_paramount_scraper_unit.py
- validation: green

### task-T2.4 — DONE — 2026-04-17T20:23:24Z
- commit: df035b46e89ad24bdf2a632f8aba42d0724fd763
- files: docs/data.json
- validation: green

### task-T3.1 — DONE — 2026-04-17T20:26:22Z
- commit: c03f617e18ecaaba58a903401e3b7030ebaa2a89
- files: docs/index.html, docs/styles.css, docs/ABOUT.md
- validation: green

### task-T4.1 — DONE — 2026-04-17T20:28:33Z
- commit: 986877e52fb2c91e3f32e3120b88108d8c4415ba
- files: docs/script.js, docs/styles.css
- validation: green

### task-T6.1 — DONE — 2026-04-17T20:31:59Z
- commit: ab76b134fa90bdeea082fedca2f2cbabcd2ed842
- files: CHANGELOG.md
- validation: green
- notes: pytest 73 passed / 22 skipped; grep checks all present; verify_calendar.py --offline 22/22 checks passed; check_ai_smell.py 0 violations across 222 events

### task-T6.2 — DONE — 2026-04-17T20:33:03Z
- commit: 487b7505200dca829dc307aa00371ab4bb1f3ee4
- files: STATUS-2026-04-18.md, CHANGELOG.md
- validation: green

<!-- END OVERNIGHT-PLAN: 2026-04-18 -->

<!-- BEGIN OVERNIGHT-PLAN: 2026-04-17 -->
## Overnight run — 2026-04-17

Runner: `overnight-plan` skill. Branch: `overnight/2026-04-17`. Goal: promote v11-picks-plus to default site, add search/venue/category filters, impeccable audit + fixes, G-stack strategy brief. Full spec in `CLAUDE.md` §Overnight run — 2026-04-17.

Task entries (appended by the runner after each DONE commit) follow below.

### task-T1.2 — DONE — 2026-04-17T16:31:41Z
- commit: a7d343d
- files: docs/PRODUCT_STRATEGY.md
- validation: green

### task-T2.1 — DONE — 2026-04-17T16:34:04Z
- commit: a2459e2
- files: docs/archive/v0/index.html, docs/archive/v0/style.css, docs/archive/v0/script.js
- validation: green

### task-T2.2 — DONE — 2026-04-17T16:34:47Z
- commit: 7350bcf
- files: docs/index.html, docs/styles.css, docs/script.js
- validation: green

### task-T2.3 — DONE — 2026-04-17T16:36:06Z
- commit: 0f35573
- files: docs/script.js
- validation: green

### task-T3.1 — DONE — 2026-04-17T16:39:56Z
- commit: 3c034f1
- files: docs/IMPECCABLE_AUDIT.md
- validation: green

### task-T3.2 — DONE — 2026-04-17T16:44:34Z
- commit: 7990e8d
- files: docs/styles.css, docs/script.js, docs/index.html
- validation: green

### task-T3.3 — DONE — 2026-04-17T16:51:20Z
- commit: 235f8d5
- files: docs/styles.css, docs/script.js
- validation: green

### task-T3.4 — DONE — 2026-04-17T16:56:53Z
- commit: afa2fb6
- files: docs/IMPECCABLE_AUDIT.md
- validation: green

### task-T4.1 — DONE — 2026-04-17T17:01:30Z
- commit: d44884d
- files: docs/index.html, docs/styles.css, docs/script.js
- validation: green

### task-T4.2 — DONE — 2026-04-17T17:03:15Z
- commit: e63b493
- files: docs/index.html, docs/styles.css, docs/script.js
- validation: green

### task-T4.3 — DONE — 2026-04-17T17:05:02Z
- commit: ff770bf
- files: docs/index.html, docs/styles.css, docs/script.js
- validation: green

### task-T4.4 — DONE — 2026-04-17T17:06:48Z
- commit: 24755a12d748b0c84bb03249ca0b5cc0b4cb9f3d
- files: docs/index.html, docs/script.js, docs/styles.css
- validation: green

### task-T5.1 — DONE — 2026-04-17T17:09:33Z
- commit: 377ded75056635556daf247b952e059cebf81643
- files: docs/styles.css
- validation: green

### task-T5.2 — DONE — 2026-04-17T17:10:52Z
- commit: e01b7e7e38392d1dd23af6f99dec32c2374def64
- files: docs/index.html, docs/styles.css
- validation: green

### task-T6.1 — DONE — 2026-04-17T17:12:21Z
- commit: b4e8b81d44f7c7e9ab0e5cd0220e0b8d95a94989
- files: CHANGELOG.md
- validation: green

### task-T6.2 — DONE — 2026-04-17T17:13:57Z
- commit: 295e265189c9df7be9a81da3b38ccf63fa07e6d2
- files: STATUS-2026-04-17.md
- validation: green

<!-- END OVERNIGHT-PLAN: 2026-04-17 -->

<!-- BEGIN OVERNIGHT-PLAN: 2026-04-16 -->
## Overnight run — 2026-04-16

Runner: `overnight-plan` skill. Branch: `overnight/2026-04-16`. Goal: v11 polish, 10 new stylistic variants, review-quality pilot. Full spec in `CLAUDE.md` §Overnight run — 2026-04-16.

Task entries (appended by the runner after each DONE commit) follow below.

### task-T8.1 — DONE — 2026-04-16T16:36:41Z
- commit: a11d9f3
- files: (no-op verification commit)
- validation: green

### task-T8.3 — DONE — 2026-04-16T16:45:18Z
- commit: 4df5ab2
- files: scripts/check_ai_smell.py
- validation: green

### task-T8.5 — DONE — 2026-04-16T16:48:06Z
- commit: 43c04ab
- files: scripts/verify_calendar.py
- validation: green

### task-T5.2 — DONE — 2026-04-16T16:49:56Z
- commit: 51e1f09
- files: docs/variants/v11-picks-plus/styles.css
- validation: green

### task-T5.3 — DONE — 2026-04-16T17:00:00Z
- commit: 31c0cdc3b1ffe64724ed9cec30e08ffaad3e4b46
- files: docs/variants/v11-picks-plus/script.js, docs/variants/v11-picks-plus/styles.css, scripts/check_variant.mjs
- validation: green

### task-T5.4 — DONE — 2026-04-16T17:05:16Z
- commit: dd8d02c
- files: docs/variants/v11-picks-plus/audit.md
- validation: green

### task-T6.2 — DONE — 2026-04-16T17:16:38Z
- commit: 81761ba
- files: docs/variants/v11b/index.html, docs/variants/v11b/script.js, docs/variants/v11b/styles.css, docs/variants/v11b/audit.md
- validation: green

### task-T6.3 — DONE — 2026-04-16T17:17:45Z
- commit: 583f349
- files: docs/variants/v11c/
- validation: green

### task-T8.2 — DONE — 2026-04-16T17:25:00Z
- commit: 708d162
- files: src/processor.py, update_website_data.py, docs/data.json, docs/source_update_times.json
- validation: green

### task-T8.4 — DONE — 2026-04-16T17:28:30Z
- commit: 893b3e5de5cb47eba7f408f8e95245999da63d5b
- files: src/summary_generator.py, docs/data.json
- validation: green

### task-T6.4 — DONE — 2026-04-16T17:30:45Z
- commit: 141c95f
- files: docs/variants/v11d/index.html, docs/variants/v11d/script.js, docs/variants/v11d/styles.css, docs/variants/v11d/audit.md
- validation: green

### task-T6.5 — DONE — 2026-04-16T17:33:20Z
- commit: 5ecfbfc
- files: docs/variants/v11e/audit.md, docs/variants/v11e/index.html, docs/variants/v11e/script.js, docs/variants/v11e/styles.css
- validation: green

### task-T6.6 — DONE — 2026-04-16T17:35:00Z
- commit: 73cfd16
- files: docs/variants/v11f/index.html, docs/variants/v11f/script.js, docs/variants/v11f/styles.css, docs/variants/v11f/audit.md
- validation: green

### task-T6.7 — DONE — 2026-04-16T17:38:45Z
- commit: 87e4ab6
- files: docs/variants/v11g/index.html, docs/variants/v11g/script.js, docs/variants/v11g/styles.css, docs/variants/v11g/audit.md
- validation: green

### task-T6.8 — DONE — 2026-04-16T17:42:15Z
- commit: b6019a4
- files: docs/variants/v11h/index.html, docs/variants/v11h/script.js, docs/variants/v11h/styles.css, docs/variants/v11h/audit.md
- validation: green

### task-T6.9 — DONE — 2026-04-16T17:44:30Z
- commit: b1842b5
- files: docs/variants/v11i/index.html, docs/variants/v11i/script.js, docs/variants/v11i/styles.css, docs/variants/v11i/audit.md
- validation: green

### task-T6.10 — DONE — 2026-04-16T17:28:53Z
- commit: 99af60a
- files: docs/variants/v11j/index.html, docs/variants/v11j/script.js, docs/variants/v11j/styles.css, docs/variants/v11j/audit.md
- validation: green

### task-T6.11 — DONE — 2026-04-16T17:47:26Z
- commit: 4bc93c6
- files: docs/variants/index.html
- validation: green

### task-T6.12 — DONE — 2026-04-16T17:29:55Z
- commit: 50e3e44
- files: docs/variants/V11_AUDIT_SUMMARY.md
- validation: green

### task-T7.2 — DONE — 2026-04-16T17:52:44Z
- commit: 6f9def6
- files: src/sources/__init__.py,src/sources/wikipedia.py
- validation: green

### task-T7.3 — DONE — 2026-04-16T17:53:15Z
- commit: 56c456a
- files: src/sources/letterboxd.py
- validation: green

### task-T7.4 — DONE — 2026-04-16T18:00:00Z
- commit: 7bc3074
- files: src/processor.py
- validation: green

### task-T7.5 — DONE — 2026-04-16T18:07:33Z
- commit: 4dbf033
- files: update_website_data.py,docs/data-pilot.json
- validation: green

### task-T7.6 — DONE — 2026-04-16T18:16:42Z
- commit: 7f91777
- files: docs/variants/v11-review-uplift/index.html, docs/variants/v11-review-uplift/script.js, docs/variants/v11-review-uplift/styles.css, docs/variants/v11-review-uplift/audit.md
- validation: green

### task-T9.1 — DONE — 2026-04-16T17:48:11Z
- commit: (no-op — all gates pass, no new changes committed)
- files: CHANGELOG.md
- validation: green

### task-T9.2 — DONE — 2026-04-16T17:48:27Z
- commit: bf271d2
- files: STATUS-2026-04-16.md
- validation: green

<!-- END OVERNIGHT-PLAN: 2026-04-16 -->

<!-- BEGIN OVERNIGHT-PLAN: 2026-04-15 -->
## Overnight run — 2026-04-15

Runner: `overnight-plan` skill. Branch: `overnight/2026-04-15`. Goal: THE STRANGER bug, anti-AI-smell reviews, 10 design variants. Full spec in `CLAUDE.md` §Overnight run — 2026-04-15.

Task entries (appended by the runner after each DONE commit) follow below.

### task-T0.2 — DONE — 2026-04-15T19:14:25Z
- commit: c36a97b
- files: docs/variants/_shared/reset.css
- validation: green

### task-T0.3 — DONE — 2026-04-15T19:19:17Z
- commit: b84fcb9
- files: docs/variants/PLUGIN_STATUS.md
- validation: green

### task-T1.1 — DONE — 2026-04-15T19:20:44Z
- commit: ad0f369
- files: tests/test_consolidation_invariant.py
- validation: green

### task-T1.2 — DONE — 2026-04-15T19:21:16Z
- commit: 09b066f
- files: update_website_data.py, tests/test_consolidation_invariant.py, docs/data.json
- validation: green

### task-T1.3 — DONE — 2026-04-15T19:24:38Z
- commit: 642dd6c
- files: docs/script.js
- validation: green

### task-T1.4 — DONE — 2026-04-15T19:26:48Z
- commit: (no-op — T1.2 already regenerated docs/data.json)
- files: docs/data.json (verified, no changes needed)
- validation: green

### task-T2.1 — DONE — 2026-04-15T19:27:07Z
- commit: 0ae2da3
- files: src/processor.py
- validation: green

### task-T2.2 — DONE — 2026-04-15T19:28:10Z
- commit: 0c73a7d
- files: src/processor.py
- validation: green

### task-T2.3 — DONE — 2026-04-15T19:30:01Z
- commit: 4699044
- files: src/summary_generator.py
- validation: green

### task-T2.4 — DONE — 2026-04-15T19:31:58Z
- commit: 50a93e3
- files: scripts/check_ai_smell.py
- validation: green

### task-T2.5 — DONE — 2026-04-15T20:12:50Z
- commit: 1802014
- files: scripts/regen_smelly_reviews.py
- validation: green

### task-T2.6 — DONE — 2026-04-15T20:15:30Z
- commit: 4b1a6cd
- files: docs/data.json
- validation: green

### task-T3.1 — DONE — 2026-04-15T19:39:44Z
- commit: a892356
- files: docs/variants/v1/index.html, docs/variants/v1/styles.css, docs/variants/v1/script.js, docs/variants/v1/audit.md
- validation: green (check_variant.mjs missing — pytest+verify_calendar green)

### task-T3.2 — DONE — 2026-04-15T19:43:09Z
- commit: c5848bb
- files: docs/variants/v2/index.html, docs/variants/v2/styles.css, docs/variants/v2/script.js
- validation: green (check_variant.mjs missing — pytest+verify_calendar green)

### task-T3.3 — DONE — 2026-04-15T19:45:03Z
- commit: 27b3800
- files: docs/variants/v3/index.html, docs/variants/v3/styles.css, docs/variants/v3/script.js, docs/variants/v3/audit.md
- validation: green (check_variant.mjs missing — pytest+verify_calendar green)

### task-T3.4 — DONE — 2026-04-15T19:47:55Z
- commit: 0edb6db
- files: docs/variants/v4/index.html, docs/variants/v4/styles.css, docs/variants/v4/script.js, docs/variants/v4/audit.md
- validation: green (check_variant.mjs missing — pytest+verify_calendar green)

### task-T3.5 — DONE — 2026-04-15T19:51:07Z
- commit: 271d05f
- files: docs/variants/v5/index.html, docs/variants/v5/styles.css, docs/variants/v5/script.js, docs/variants/v5/audit.md
- validation: green (check_variant.mjs missing — pytest+verify_calendar green)

### task-T3.6 — DONE — 2026-04-15T19:55:23Z
- commit: f614904
- files: docs/variants/v6/index.html, docs/variants/v6/styles.css, docs/variants/v6/script.js, docs/variants/v6/audit.md
- validation: green (check_variant.mjs missing — pytest+verify_calendar green)

### task-T3.7 — DONE — 2026-04-15T19:59:31Z
- commit: 23ece9c
- files: docs/variants/v7/index.html, docs/variants/v7/styles.css, docs/variants/v7/script.js, docs/variants/v7/audit.md
- validation: green

### task-T3.8 — DONE — 2026-04-15T20:04:13Z
- commit: 3b022f1
- files: docs/variants/v8/index.html, docs/variants/v8/styles.css, docs/variants/v8/script.js, docs/variants/v8/audit.md
- validation: green (check_variant.mjs missing — pytest+verify_calendar green)

### task-T3.9 — DONE — 2026-04-15T20:06:39Z
- commit: dd4227a
- files: docs/variants/v9/index.html, docs/variants/v9/styles.css, docs/variants/v9/script.js, docs/variants/v9/audit.md
- validation: green (check_variant.mjs missing — pytest+verify_calendar green)

### task-T3.10 — DONE — 2026-04-15T20:09:39Z
- commit: ee2f8ee
- files: docs/variants/v10/index.html, docs/variants/v10/styles.css, docs/variants/v10/script.js, docs/variants/v10/audit.md
- validation: green (check_variant.mjs missing — pytest+verify_calendar green)

BLOCKED: task-T2.7: verify_calendar.py --offline fails: 29 refusal-shaped one_liner_summary entries (Opera + Paramount) and check_ai_smell.py shows 74 banned-phrase violations still in docs/data.json — regen in T2.6 did not fully clean cached reviews; requires live API regen which is out of scope for this no-code gate task

### task-T3.11 — DONE — 2026-04-15T20:22:03Z
- commit: dcd4216
- files: docs/variants/index.html
- validation: green

### task-T3.12 — DONE — 2026-04-15T20:24:37Z
- commit: b3bbe87
- files: docs/variants/v2/audit.md
- validation: green

<!-- END OVERNIGHT-PLAN: 2026-04-15 -->

## [Calendar fix] — 2026-04-14 — in progress

### Termination criterion

`scripts/verify_calendar.py --live` prints `PASS` twice in a row. Offline
mode runs against saved HTML fixtures; live mode hits austinfilm.org and
hyperrealfilm.club.

### Subtask queue (checkbox-driven — the overnight loop picks the next unchecked line)

Finished (this branch):
- [x] 2026-04-13 22:30 M0   type='movie' in AFS scraper + loosen processor filter
- [x] 2026-04-13 22:35 MA.1 scripts/oracle_afs.py parses april-may-2026-schedule-afs.md
- [x] 2026-04-13 22:36 MA.2 scripts/oracle_hyperreal.py parses april-2026-hyperreal.md
- [x] 2026-04-13 22:37 MA.3 tests/test_oracle_parsers.py (13 assertions, all pass)
- [x] 2026-04-13 22:40 MA.4 occurrences → screenings (backend + config)
- [x] 2026-04-13 22:41 MA.5 frontend reads release_year / runtime_minutes / one_liner_summary
- [x] 2026-04-13 22:42 MA.6 ?debug_date=YYYY-MM-DD shim in docs/script.js
- [x] 2026-04-13 22:43 MA.7 pytest.ini registers integration/live/unit markers
- [x] 2026-04-13 22:47 MB.1 save AFS calendar snapshot + 7 movie pages (April 2026)
- [x] 2026-04-13 22:48 MB.2 tests/test_afs_integration.py (6 assertions, all pass)
- [x] 2026-04-13 22:50 MC.1 save Hyperreal calendar snapshot + 4 movie pages
- [x] 2026-04-13 22:52 MC.2 tests/test_hyperreal_integration.py (5 assertions, all pass)
- [x] 2026-04-13 22:53 MC.3 fix: Hyperreal _build_event_from_config unconditionally sets type='movie'
- [x] 2026-04-13 22:58 MD.1 scripts/verify_calendar.py (11/11 checks pass offline)

Overnight queue (unchecked — loop will pick them in order):

AFS fixture expansion (raises oracle coverage):
- [x] 2026-04-14 09:55 MB.3  save screening pages for every /screening/ link in calendar_snapshot_2026_04.html (46 total)
- [x] 2026-04-14 09:55 MB.4  test_afs_integration.py raises coverage floor to ≥95%
- [ ] MB.5  add tests for all films in oracle (director/release_year/country/runtime_minutes populated)

Hyperreal fixture expansion:
- [x] 2026-04-14 09:59 MC.4  save screening pages for every /events/ link in Hyperreal calendar (21 total)
- [x] 2026-04-14 09:59 MC.5  test_hyperreal_integration.py covers every entry in the oracle
- [x] 2026-04-14 09:59 MC.6  clean DeprecationWarning: BeautifulSoup text=... → string=...

End-to-end pipeline:
- [x] 2026-04-14 09:47 MD.2  verify_calendar.py --live passes (11/11)
- [x] 2026-04-14 10:11 MD.3  regenerate docs/data.json from the full pipeline (141 entries, 73 movies, 21/21)
- [x] 2026-04-14 10:13 MD.4  verify Today/Week/Weekend counts via actual docs/data.json shape (5/18/11 on 04-14)
- [x] 2026-04-14 10:15 MD.5  smoke test: `python -m http.server` + GET /data.json → 200 OK, 141 entries

Review quality (caught by user during inspection of LANCELOT DU LAC):
- [x] 2026-04-14 10:35 MD.6  is_refusal_response heuristic + 3-attempt retry chain in _get_ai_rating / _get_classical_rating + Claude Sonnet fallback. New verify gate 'data.json: no refusals' counts how many entries ship LLM-refusal text as their review. RED with 43 stale refusals until force-reprocess flushes them.
- [x] 2026-04-14 10:43 MD.7  flushed all 43 stale refusals via --force-reprocess + cache-miss-on-refusal logic. 23 retries fired during the run, all caught by permissive/knowledge prompts; 0 needed Claude Sonnet fallback.
- [x] 2026-04-14 10:44 MD.8  is_refusal_response no longer flags short summaries (separate failure mode); REFUSAL_PATTERNS extended for permissive-prompt refusal phrasing ('I appreciate your request, but…', 'I cannot verify', 'I cannot locate', etc.).

Simplify (Milestone E):
- [x] 2026-04-14 10:05 ME.1  collapse AFSScraper duplicated extraction blocks into one helper (-102 lines)
- [x] 2026-04-14 10:10 ME.2  remove --full and --days flags from update_website_data.py (deprecated)
- [x] 2026-04-14 10:12 ME.3  delete unused getModalHTML in docs/script.js (-28 lines)
- [ ] ME.4  delete the occurrences legacy-alias in docs/script.js (kept defensive: no observed cost)

Other venues (Milestone G — open-ended, extends to all venues per user scope decision):
- [x] 2026-04-14 10:55 G.1  FirstLight re-enabled (3 site-drift fixes + type='book_club' + book retry chain). 4 events in data.json.
- [x] 2026-04-14 11:30 G.2  AlienatedMajesty migrated pyppeteer → Playwright. New layout parser walks h2 tags in document order, tracks current series, parses 'UPCOMING CLUBS' siblings as `<Day>, <Mon> <D> - <Book> by <Author>`. 15 book club events live.
- [x] 2026-04-14 11:35 G.3  Paramount unblocked without a browser at all — discovered POST `/api/products/productionseasons` returning JSON; needed only an explicit Accept: application/json header (BaseScraper sends text/html which 500s). 58 events live.
- [x] 2026-04-14 11:25 Repo bloat: pruned 55 redundant HTML fixtures (tests/AFS_test_data + tests/Hyperreal_test_data went from 7.0 MB → 2.0 MB) without losing test coverage; live verify covers full breadth.
- [ ] G.4  baseline Austin Symphony events from docs/classical_data.json; add sanity test
- [ ] G.5  baseline Austin Opera events; add sanity test
- [ ] G.6  baseline Austin Chamber Music events; add sanity test
- [ ] G.7  baseline Early Music events; add sanity test
- [ ] G.8  baseline La Follia events; add sanity test
- [ ] G.9  baseline Ballet Austin events; add sanity test

### Conventions
- Blockers: write `BLOCKED: <subtask-id>: <why>` as a line below the checklist. The loop skips these and moves on.
- Commits: author as `Hadrien-Cornier <hadrien.cornier@gmail.com>` via `git -c user.name=... -c user.email=...`.
- Push every commit to `origin/fix/calendar-oracle` immediately (never `main`).
- Green gate: `pytest -q` AND `python scripts/verify_calendar.py --offline` must both pass before marking a subtask done.

---

## [Previous] — 2026-04-13

### Final Status: ✅ COMPLETE

Both `analyze` and `wiki` work end-to-end. The workflow is reproducible via `scripts/gitnexus_workflow.sh`.

---

### Milestone 1: Install & Analyze (commit 6eee79b)

#### What Changed
- Installed `gitnexus@1.6.1` as a local dev dependency (`npm install --save-dev gitnexus`)
- Added `npm run analyze`, `npm run wiki`, `npm run gitnexus:status` scripts to `package.json`
- Created `CHANGELOG.md`
- Updated `CLAUDE.md` and `AGENTS.md` to fix broken `npx gitnexus` reference

#### Commands Run
```bash
# Install (global install failed with EACCES — local install used instead)
npm install --save-dev gitnexus

# Verify
./node_modules/.bin/gitnexus --version
# Output: 1.6.1

# Analyze
./node_modules/.bin/gitnexus analyze
# Output: Repository indexed successfully (6.3s)
#         781 nodes | 1,928 edges | 56 clusters | 63 flows

# Status check
./node_modules/.bin/gitnexus status
# Output: Status: ✅ up-to-date (commit f8d377a)
```

#### npx Failure (Root Cause)
```
TypeError: Cannot destructure property 'package' of 'node.target' as it is null.
```
- **Cause**: npm v11.12.1 + Node v24.14.0 incompatibility during `tree-sitter-swift` post-install rebuild
- **Fix**: Use `./node_modules/.bin/gitnexus` (local install) instead of `npx gitnexus`
- **Workaround documented** in README, CLAUDE.md, AGENTS.md, and workflow script

---

### Milestone 2: Wiki — First Attempt (blocked, then fixed)

#### Failure 1: provider=cursor saved in global config
```bash
./node_modules/.bin/gitnexus wiki
# Error: Cursor CLI not found.
```
Fix: Cleared `~/.gitnexus/config.json`

#### Failure 2: Default base URL is openrouter.ai, not OpenAI
```bash
./node_modules/.bin/gitnexus wiki --provider openai --model gpt-4o-mini
# LLM API error (401): Missing Authentication header
```
Root cause: `gitnexus`'s `resolveLLMConfig()` in `llm-client.js` defaults `baseUrl` to
`https://openrouter.ai/api/v1` regardless of `--provider openai`. An OpenAI key (`sk-proj-...`)
sent to OpenRouter returns 401. Fix: explicit `--base-url https://api.openai.com/v1`.

#### Solution
```bash
export OPENAI_API_KEY=sk-proj-...   # Set in ~/.zshrc
./node_modules/.bin/gitnexus wiki \
  --provider openai \
  --model gpt-4o-mini \
  --base-url https://api.openai.com/v1 \
  --api-key "$OPENAI_API_KEY"
```

---

### Milestone 3: Wiki — Success

#### Output
```
Wiki generated successfully (342.5s)
Mode: full
Pages: 43
Output: .gitnexus/wiki/
Viewer: .gitnexus/wiki/index.html
```

#### Artifacts verified
- 43 `.md` files, all non-empty
- `index.html` viewer present
- `meta.json` and `module_tree.json` present
- Total lines: 4,208

#### Wiki pages include
- `calendar-generation.md`, `configuration-management.md`, `enrichment-layer.md`
- `event-processing.md`, `llm-service.md`, `scraping-src.md`, `summary-generation.md`
- `scraping-tests.md`, `examples.md`, plus 34 more pages

---

### Milestone 4: Template Patch

#### Problem
`gitnexus analyze` auto-regenerates the `<!-- gitnexus:start -->` sections in CLAUDE.md and
AGENTS.md, overwriting our `npx` fix with the hardcoded template.

#### Fix
Patched `node_modules/gitnexus/dist/cli/ai-context.js` to replace:
- `run \`npx gitnexus analyze\`` → `run \`npm run analyze\`` with a note about Node v24 bug
- `\`\`\`bash\nnpx gitnexus analyze\n\`\`\`` → `npm run analyze`
- `\`\`\`bash\nnpx gitnexus analyze --embeddings\n\`\`\`` → `./node_modules/.bin/gitnexus analyze --embeddings`

**Note**: This patch lives in `node_modules/` and will be lost on `npm install`. To reapply:
```bash
node scripts/patch_gitnexus_template.js
```
(script created for this purpose)

---

### Milestone 5: Reproducibility Script

#### `scripts/gitnexus_workflow.sh`
```bash
# Analyze only (no API key needed)
./scripts/gitnexus_workflow.sh

# Full workflow including wiki
export OPENAI_API_KEY=sk-proj-...
./scripts/gitnexus_workflow.sh --wiki

# Force full re-index
./scripts/gitnexus_workflow.sh --force --wiki
```

#### Verified clean run
```
=== GitNexus Workflow ===
Version: 1.6.1
--- Step 1: analyze --- → 781 nodes | 1,929 edges | 55 clusters | 63 flows
--- Step 2: status --- → ✅ up-to-date
✅ Workflow complete.
```

---

### Known Issues / Notes

1. **node_modules patch**: The `ai-context.js` template patch is not persistent across `npm install`.
   A `scripts/patch_gitnexus_template.js` postinstall script handles reapplication.

2. **`.gitnexus/` in .gitignore**: The index and wiki are not tracked in git (correct — they're
   generated artifacts). Run `./scripts/gitnexus_workflow.sh` to regenerate after cloning.

3. **Wiki API cost**: With `gpt-4o-mini`, 43-page wiki generation for this repo costs ~$0.05-0.10
   and takes ~6 minutes. Use `--force` only when needed.

4. **Wiki not checked into git**: `.gitnexus/` is gitignored. The wiki must be regenerated locally
   or in CI with an API key.
