# CHANGELOG

## [Unreleased] — 2026-04-13

### Milestone: GitNexus Install & Analyze

#### What Changed
- Installed `gitnexus@1.6.1` as a local dev dependency (not global, to keep it reproducible per-project)
- Added `npm run analyze` and `npm run wiki` scripts to `package.json`

#### Commands Run
```bash
# Install (global install failed with EACCES, local install succeeded)
npm install --save-dev gitnexus

# Verify install
./node_modules/.bin/gitnexus --version
# Output: 1.6.1

# Run analyze
./node_modules/.bin/gitnexus analyze
# Output: Repository indexed successfully (6.3s)
#         781 nodes | 1,928 edges | 56 clusters | 63 flows

# Check status
./node_modules/.bin/gitnexus status
# Output: Status: ✅ up-to-date (commit f8d377a)
```

#### npx Failure (documented)
`npx gitnexus` failed with:
```
TypeError: Cannot destructure property 'package' of 'node.target' as it is null.
```
Root cause: npm v11.12.1 + node v24.14.0 incompatibility with `tree-sitter-swift` optional dep during npx install.
Fix: Use `./node_modules/.bin/gitnexus` (local install) instead of `npx gitnexus`.

#### Analyze Output
Index stored at `.gitnexus/` with:
- 92 files indexed
- 781 nodes, 1,928 edges
- 56 functional clusters
- 63 execution flows
- No embeddings (run `analyze --embeddings` to add)

---

### Blocker: `gitnexus wiki` Requires LLM API Key

#### Status: BLOCKED — wiki command needs an API key

```bash
./node_modules/.bin/gitnexus wiki
# Error: No LLM API key found.
# Set OPENAI_API_KEY or GITNEXUS_API_KEY environment variable,
# or pass --api-key <key>, or use --provider cursor.
```

`--provider cursor` also fails (Cursor CLI not installed).

#### Next 2 Best Options

**Option A — Set API key in environment (recommended)**
```bash
# Using OpenAI key:
export OPENAI_API_KEY=sk-...
./node_modules/.bin/gitnexus wiki

# OR using Anthropic key via OpenAI-compatible endpoint:
export OPENAI_API_KEY=$ANTHROPIC_API_KEY
./node_modules/.bin/gitnexus wiki \
  --base-url https://api.anthropic.com/v1 \
  --model claude-sonnet-4-6

# OR set GITNEXUS_API_KEY (saves to ~/.gitnexus/config.json):
GITNEXUS_API_KEY=sk-... ./node_modules/.bin/gitnexus wiki
```

**Option B — Add key to shell profile for persistent use**
```bash
echo 'export OPENAI_API_KEY=sk-...' >> ~/.zshrc
source ~/.zshrc
npm run wiki
```

#### Unblocked Work Completed
- analyze: ✅ fully working
- index status: ✅ up-to-date
- MCP server: ✅ gitnexus mcp ready (add to Claude Code settings)
- Documentation: ✅ CLAUDE.md updated, package.json scripts added

---

### Next Actions
1. User provides OPENAI_API_KEY or GITNEXUS_API_KEY
2. Run `npm run wiki` — expect wiki pages in `.gitnexus/wiki/`
3. Verify wiki artifacts are non-empty
4. Commit wiki output + final status
