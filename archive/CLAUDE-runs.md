# CLAUDE.md run log archive

Historical autonomous-run summaries previously kept inline in `CLAUDE.md`. Moved here in task-6.2 (long-run/20260430-102637) to keep the active CLAUDE.md under 250 lines per the karpathy/nanochat-style cleanup goal. Each entry below preserves the original wording and ordering — append only, never rewrite.

All runs inherit the **Autonomous Run Baseline** in `CLAUDE.md` unless explicitly noted in the entry.

---

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
