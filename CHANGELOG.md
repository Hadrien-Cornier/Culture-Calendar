# CHANGELOG

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

Simplify (Milestone E):
- [x] 2026-04-14 10:05 ME.1  collapse AFSScraper duplicated extraction blocks into one helper (-102 lines)
- [x] 2026-04-14 10:10 ME.2  remove --full and --days flags from update_website_data.py (deprecated)
- [x] 2026-04-14 10:12 ME.3  delete unused getModalHTML in docs/script.js (-28 lines)
- [ ] ME.4  delete the occurrences legacy-alias in docs/script.js (kept defensive: no observed cost)

Other venues (Milestone G — open-ended, extends to all venues per user scope decision):
- [ ] G.1  re-enable FirstLight scraper in src/scraper.py and write integration test
- [ ] G.2  re-enable AlienatedMajesty scraper and write integration test (book-club schema)
- [ ] G.3  re-enable Paramount scraper (check pyppeteer threading issue)
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
