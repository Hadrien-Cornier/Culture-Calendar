# Agent guide — Culture-Calendar

This file is the **first read** for any agent touching this repo. Skim it end-to-end before making changes. Deeper context lives in `CLAUDE.md` (overnight run protocol + feature inventory + persona gate) and `CONTRIBUTING.md` (human-facing contributor workflow).

## One-paragraph overview

Culture-Calendar scrapes Austin cultural events from ~13 venues, enriches each event with AI ratings and critic-style reviews (Perplexity + Anthropic), generates one-liner summaries, and publishes to a static GitHub Pages site with ICS calendar export. Source in `src/`, entry pipeline in `update_website_data.py`, frontend in `docs/`, static outputs in `docs/data.json`.

## Pipeline map

```
venues (HTML / JSON)
    │
    ▼   src/scrapers/*.py                 ← per-venue scraping
    │   (extends src/base_scraper.py:BaseScraper)
    ▼   src/scraper.py:MultiVenueScraper  ← orchestrator + dedup
    │
    ▼   src/validation_service.py         ← optional fail-fast health check
    ▼   src/enrichment_layer.py           ← LLM classification + field extract
    │   (driven by config/master_config.yaml templates)
    ▼   src/processor.py:EventProcessor   ← AI rating + review prompt cascade
    │   (Perplexity via src/llm_service.py; refusal detection src/refusal.py)
    ▼   src/summary_generator.py          ← Claude one-liner hook
    │
    ▼   update_website_data.py            ← assemble docs/data.json
    ▼   docs/index.html + script.js       ← render in browser
    ▼   scripts/check_live_site.py        ← pyppeteer assertions on live URL
    ▼   scripts/persona_critique.py       ← LLM council judges the deployed UX
```

Every hop writes a normalized event shape defined in `config/master_config.yaml` (templates: `movie`, `concert`, `book_club`, `opera`, `dance`, `visual_arts`, `other`).

## Where to look for…

| Task | Start at |
|---|---|
| Add a new venue scraper | `CLAUDE.md §Adding a New Venue`; pattern file `src/scrapers/afs_scraper.py` |
| Change the rating rubric | `src/processor.py` — `_get_ai_rating`, `_get_movie_rating`, etc.; prompt literals live in the same functions |
| Fix a refusal mis-classification | `src/refusal.py` + `tests/test_refusal_filter.py` |
| Add a review-quality signal | `src/processor.py:_parse_ai_response` (`review_confidence` field); template in `config/master_config.yaml`; expose in `update_website_data.py:build_event_from_template` |
| Change event schema | `config/master_config.yaml` (templates), then `update_website_data.py:build_event_from_template`, then scraper(s) producing the field |
| Add a venue to the wishlist | `README.md §Venue Wishlist` — human-curated, not auto-loaded |
| Tweak frontend UX | `docs/index.html` (markup) + `docs/script.js` (render/filter) + `docs/styles.css` |
| Verify a frontend change against live | write a spec JSON; run `scripts/check_live_site.py --spec <path>` |
| Run persona LLM council | `.venv/bin/python scripts/persona_critique.py --out docs/PERSONAS.md` |
| Benchmark models for the council | `scripts/bench_personas.py` (18 Anthropic calls, ~$2) |
| Block push on significant changes | Tag commit subject with `[persona-gate]`; requires `.githooks/pre-push` activation |
| Prospect new venues via Perplexity | `scripts/prospect_venues.py --category <cat>` → append to `README.md §Venue Wishlist` |
| Generate an ICS calendar | `src/calendar_generator.py` (invoked from the website download button) |

## Invariants agents must preserve

- **Snake_case event fields**, enforced by `config/master_config.yaml`. Never introduce camelCase in `docs/data.json`.
- **Pairwise-equal `dates` / `times` arrays** — each event's `dates[i]` pairs with `times[i]`. Downstream occurrence rendering depends on this.
- **`rating` is `0-10` integer or `-1` for ungraded.** Frontend treats `-1` as "skip badge". Don't use `None`.
- **Never commit `cache/llm_cache.json`** — gitignored; contains API responses that drift. When in doubt, nuke the cache and re-run.
- **Git identity pinned** — every commit from an agent uses `git -c user.name=Hadrien-Cornier -c user.email=hadrien.cornier@gmail.com`. Never mutate `~/.gitconfig`.
- **`docs/variants/v12i/` is archival.** The live site is `docs/*` directly. Do not edit the variants copy.
- **Feature inventory append discipline** — every change that adds a user-visible selector must append an entry to `.overnight/feature-inventory.json` so the continuity persona catches future regressions. See `CLAUDE.md §Feature Inventory`.

## Common agentic pitfalls (historical regressions)

- **Wholesale v12i promotion** dropped TTS, About, search bar (`c45fdfd`, 2026-04-19). Fixed across 2026-04-18-2 and 2026-04-18-3 runs. **Never copy `docs/variants/*` wholesale**; cherry-pick features instead.
- **`@dataclass` + importlib under Python 3.13** requires `sys.modules` registration before `exec_module`, else `AttributeError: 'NoneType' object has no attribute '__dict__'` at decoration time. See `scripts/persona_critique.py:_load_check_live_site_module` for the fix pattern.
- **Opus 4.7 deprecated `temperature`** — `MODELS_WITHOUT_TEMPERATURE` guard in `scripts/persona_critique.py`. Add new models here when Anthropic makes similar changes.
- **pyppeteer async js_truthy** — `check_live_site.py:_wrap_expr` only adds an explicit return when the expression contains `;` or `return`. For async IIFEs, assign to `window.__foo = (async()=>{...})()` then `return window.__foo`, else the outer wrapper drops the Promise.

## Entry points — quick CLI reference

```bash
# Full pipeline (all venues, all events, slow)
python update_website_data.py

# Test mode (this week only)
python update_website_data.py --test-week

# Force re-rate cached events
python update_website_data.py --force-reprocess

# Run unit tests (no network)
.venv/bin/python -m pytest -q -m "not live and not integration"

# Verify live site
.venv/bin/python scripts/check_live_site.py --spec <path-to-spec.json>

# Persona LLM council against deployed site
.venv/bin/python scripts/persona_critique.py --out docs/PERSONAS.md

# Benchmark models for the council (~$2)
.venv/bin/python scripts/bench_personas.py
```

## Agent workflow discipline

Before you edit, in this order:

1. **Read the module docstring.** Every `src/*.py` has a short header — it's there to orient.
2. **Read related `CLAUDE.md` sections** — overnight runs, feature inventory, persona gate — for active-run context.
3. **Run `gitnexus_impact`** on the target symbol if it's in `src/processor.py`, `update_website_data.py`, `src/scrapers/__init__.py`, or `src/scraper.py`. Blast-radius required before editing (see GitNexus section below).
4. **Check `CHANGELOG.md`** for how similar changes landed historically — commit messages carry constraints you won't find in code.
5. **For user-visible changes**, plan to append a `.overnight/feature-inventory.json` entry in the same commit.

After you edit:

1. `.venv/bin/python -m pytest -q` — must exit 0.
2. If you touched `docs/`, run `scripts/check_live_site.py` locally before push; `scripts/require_persona_approval.py` is available if the change warrants the LLM council.
3. Commit with the pinned identity (see invariants).

---

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
