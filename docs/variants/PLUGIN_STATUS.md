# Plugin Status: pbakaus/impeccable

## Package Info

- **Name**: impeccable
- **Version**: 2.1.7
- **Description**: Design skills, commands, and anti-pattern detection for AI coding agents
- **License**: Apache-2.0
- **Repository**: https://github.com/pbakaus/impeccable
- **npm**: https://www.npmjs.com/package/impeccable

## Install Attempt — 2026-04-15

**Result**: INSTALLED (via npx, skills only — not added to package.json)

### What worked

`npx --yes impeccable skills install --yes` succeeded non-interactively.
17 skills installed to `.agents/skills/` and symlinked for Claude Code:

adapt, animate, audit, bolder, clarify, colorize, critique, delight,
distill, impeccable, layout, optimize, overdrive, polish, quieter,
shape, typeset

All skills rated Safe/Low Risk by Gen+Socket+Snyk (critique: Med Risk Socket).

### What did NOT work

- `npx --yes impeccable skills install` (without `--yes`) requires interactive
  TTY for skill selection — exits 13 in non-interactive sessions.
- `npm install impeccable` was not attempted per overnight hard constraint
  (no new dependencies in package.json).

### Filesystem impact

- Skills installed to `.agents/skills/` (untracked, not gitignored — do NOT
  `git add`).
- No changes to `package.json` or `node_modules/`.
- Claude Code symlinks created at user level, not in repo `.claude/`.

## Availability for variant audits (T3.12)

`npx --yes impeccable detect <file-or-url>` can be used for design audits
without any package.json dependency. Fallback to axe-core remains available
if impeccable detection is insufficient.
