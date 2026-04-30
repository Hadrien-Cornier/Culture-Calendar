# Personas

Two reviewer layers, both implemented as JSON specs that an LLM consumes.

## `personas/live-site/` — UX critique

Six personas critique the deployed site (https://hadrien-cornier.github.io/Culture-Calendar/) through scripted user-stories. Each spec wires a pyppeteer assertion list (`asserts`, `pre_screenshot_actions`) to an LLM `system_prompt` + `goals` block that a Claude model uses to read the screenshot + ground-truth JSON.

| Persona | User story |
|---|---|
| `logistics-user` | Friday planner — needs `.event-when` + venue address visible without expanding. |
| `review-reader` | Skim AI reviews — wants formatted sections, readable contrast, and TTS. |
| `search-user` | Find a known title or venue fast via the masthead search. |
| `comprehensiveness-user` | Confirms the calendar covers all advertised categories + venues. |
| `continuity-user` | Asserts every entry in `config/feature-inventory.json` resolves on the live site. |
| `mobile-user` | iPhone-class viewport — filter sheet, tap targets, no horizontal scroll. |

Driver: `scripts/persona_critique.py` (LLM mode) + `scripts/check_live_site.py` (structural-only). Pre-push hook runs the LLM council against a local `python -m http.server` rooted at `docs/` when an outgoing commit subject contains `[persona-gate]`.

## `personas/code-review/` — diff critique

Two permanent reviewers grade pending diffs (uncommitted, staged, or `HEAD~1..HEAD`). They never run against the website; they read the patch.

### `review-quality.json`
Senior-engineer lens. Watches for diffs that silently weaken the AI-generated event reviews this site exists to produce — dropped evidence requirements, lowered confidence thresholds, removed `review_confidence` propagation, generic prompts replacing category-specific dispatch (`_get_classical_rating`, `_get_dance_rating`, `_get_visual_arts_rating`). Also enforces surgical-change discipline and that new branches have tests.

### `repo-minimalism.json`
Karpathy/nanochat lens. Flags ceremony, helper graveyards, premature abstraction, parallel near-duplicate files, config knobs with no readers, defensive scaffolding around code paths that cannot fail, and bloat in `CLAUDE.md` / `CHANGELOG.md`. Every line in the diff has to earn its bytes.

Both speak the same wire format: a single `record_review` tool call returning `{verdict: PASS|FAIL|ABSTAIN, summary, findings[]}` with severities `critical`/`high`/`medium`/`low` (informational — gating is unanimous on `verdict`).

### How they run

| Mode | Command |
|---|---|
| Manual review-quality on staged + worktree | `.venv/bin/python scripts/review_quality_check.py` |
| Manual review-quality on the last commit | `.venv/bin/python scripts/review_quality_check.py --commit` |
| Pre-push (every push) | `.githooks/pre-push` validates `personas/code-review/repo-minimalism.json` parses and announces the gate. The actual LLM evaluation runs inside the long-run council harness. |
| Long-run council | `~/.claude/skills/long-run/scripts/task-judge.sh` invokes both reviewers per-task; any FAIL re-queues. |

Both personas accept a model override via env var (`LONG_RUN_MODEL_REVIEW_QUALITY`, `LONG_RUN_MODEL_REPO_MINIMALISM`); default is `claude-sonnet-4-6`.

## Adding a persona

1. Drop a JSON spec under the right subdirectory.
2. Match the schema of an existing peer (live-site personas have `asserts` + `llm`; code-review personas have `system_prompt` + `goals` + `must_not_flag`).
3. Wire it into the relevant driver (`scripts/persona_critique.py`, `scripts/review_quality_check.py`, `~/.claude/skills/long-run/...`).
4. Document it here.
