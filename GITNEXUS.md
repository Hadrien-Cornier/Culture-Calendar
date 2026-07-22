# GitNexus in Culture-Calendar

What it is
- GitNexus indexes the repo into a local knowledge graph and exposes tools to AI editors (Claude Code via MCP) for impact analysis, coordinated renames, and graph-aware refactors.
- Runs locally; indexes are stored under `.gitnexus/` (gitignored). No server required.

How we use it
- Planning: before a Claude Code plan, we refresh the index so the graph is current.
- Impact check: plans include a short blast-radius summary using GitNexus (detect_impact) to highlight risk.
- After edits: we reindex so subsequent runs see fresh structure.

Quick commands
- Index (or refresh):
  ```bash
  npx -y gitnexus@latest analyze
  ```
- Generate a Code Wiki (optional):
  ```bash
  npx -y gitnexus@latest wiki
  ```
- List indexed repos (global):
  ```bash
  npx -y gitnexus@latest list
  ```

Claude Code MCP setup (one-time on this machine)
```bash
claude mcp add gitnexus -- npx -y gitnexus@latest mcp
```

cc_flow integration
- Our `scripts/cc_flow.sh` wrapper (in hadrien-ai-assistant) automatically:
  - Runs `analyze` before planning
  - Encourages `detect_impact` in the plan
  - Re-runs `analyze` after apply

Notes
- If you see stale results, run `npx -y gitnexus@latest analyze --force`.
- Large binary/vendor files are ignored by default.
