# CHANGELOG

## [Unreleased] — 2026-04-13

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
