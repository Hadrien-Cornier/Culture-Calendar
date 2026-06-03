# Overnight run — 2026-04-15 — handoff

**Disposition**: `RUN_HALTED: no eligible TODO tasks` (T4.1/T4.2 unreachable because T2.7 blocked).
**Branch**: `overnight/2026-04-15` (not pushed — user merges manually).
**Runner**: `~/.claude/skills/overnight-plan/scripts/overnight-runner.sh`, PIDs 47555 → 54570 (both exited cleanly).
**Duration**: ~1h15m wall clock (started 19:13Z, halted 20:27Z).

## What shipped

### 1. THE STRANGER bug fixed (Task group T1)

All 6 screenings of THE STRANGER (L'ETRANGER) now appear in `docs/data.json` via both `dates[]` and `screenings[]`. Generalized invariant: `set(event.dates) == set(s.date for s in event.screenings)` enforced for every event.

| Task | Commit | What |
|---|---|---|
| T1.1 | (see `git log --grep task-T1.1`) | Regression test pinning THE STRANGER 6-date coverage |
| T1.2 | (see log) | `update_website_data.py` hoists `dates` from `screenings` |
| T1.3 | (see log) | Frontend migrated remaining `.date`/`.dates[0]` readers to `screenings[]` |
| T1.4 | (see log) | `docs/data.json` regenerated; verify_calendar.py offline PASS |

Verify:
```bash
.venv/bin/python -c "
import json
d = json.load(open('docs/data.json'))
e = [x for x in d['events'] if 'STRANGER' in x['title']][0]
assert set(e['dates']) == {'2026-04-17','2026-04-18','2026-04-19','2026-04-24','2026-04-26','2026-04-27'}
print('OK', e['dates'])
"
```

### 2. Anti-AI-smell infrastructure (Task group T2 — **partially blocked**)

| Task | Status | What |
|---|---|---|
| T2.1 | DONE | `_style_rubric()` added to `src/processor.py` |
| T2.2 | DONE | Rubric wired into all 9 prompts in `processor.py` |
| T2.3 | DONE | Summary-generator examples replaced (Bergman/Ligeti instead of "Haunting X"); rubric wired in |
| T2.4 | DONE | `scripts/check_ai_smell.py` linter |
| T2.5 | DONE (on retry after transient API timeout) | `scripts/regen_smelly_reviews.py` cache invalidator |
| T2.6 | DONE (passed its own validate) | Regen run completed |
| **T2.7** | **BLOCKED** | `verify_calendar.py --offline` fails: 29 refusal-shaped one-liners (Opera+Paramount) and 74 banned-phrase matches still present after regen |

**Why T2.7 blocked**: the strict rubric (forbidding em-dashes + 17 banned phrases) pushed the LLM into refusal mode on Opera and Paramount entries whose source material is thin. The infrastructure works; the prompt needs softening.

**Morning fix options** (pick one):
- **Soften the rubric** in `src/processor.py:_style_rubric()` to "prefer X over Y" phrasing; keep the banned list but allow substitutions instead of forbidding.
- **Extend the refusal retry chain** in `src/processor.py:_get_ai_rating` to detect the new refusal shapes ("I cannot ensure the review meets all style constraints", etc.) and fall back to general-knowledge prompt.
- **Raise the linter threshold** in `scripts/check_ai_smell.py` to tolerate banned phrases that appear inside event titles (e.g. `HAUNTING` as a movie title).
- Or some combination. Starting point: run `.venv/bin/python scripts/check_ai_smell.py docs/data.json --verbose` to see the 74 offending entries.

### 3. Ten design variants + gallery (Task group T3)

All 10 variants live, each self-contained and reading `../../data.json`:

| ID | Variant | Commit |
|---|---|---|
| T3.1 | v1 austintango-style scroll list w/ left date rail | (see log) |
| T3.2 | v2 editorial dark mode, warm serif | (see log) |
| T3.3 | v3 grid of cards w/ hover flip synopsis | (see log) |
| T3.4 | v4 terminal/monospace keyboard-nav | (see log) |
| T3.5 | v5 NYT-style sticky date rail, 2-col body | 271d05f |
| T3.6 | v6 horizontal timeline drag-scroll | f614904 |
| T3.7 | v7 calendar heatmap first | 23ece9c |
| T3.8 | v8 Obsidian/Notion narrow column | 3b022f1 |
| T3.9 | v9 Swiss poster aesthetic | dd4227a |
| T3.10 | v10 critic's tipsheet, rating-sorted | ee2f8ee |
| T3.11 | Gallery `docs/variants/index.html` | dcd4216 |
| T3.12 | Impeccable/axe-core audit per variant (`audit.md`) | b3bbe87 |

Impeccable plugin install: see `docs/variants/PLUGIN_STATUS.md` for outcome. Audits fell back to `npx @axe-core/cli` if plugin unavailable.

## What did not ship

| Task | Why |
|---|---|
| T2.7 | Verify gate failed after T2.6 regen — see fix options above |
| T4.1 | Depends on T2.7; unreachable |
| T4.2 | Depends on T4.1; this file was written manually instead |

## Morning checklist

```bash
# 1. Preview all 10 variants side-by-side
(cd docs && python -m http.server 8765) &
open "http://localhost:8765/variants/index.html?debug_date=2026-04-19"
# Inspect v1..v10; check each audit.md for a11y findings.

# 2. Confirm THE STRANGER fix rendered on the current site
open "http://localhost:8765/?debug_date=2026-04-19"
# Assert THE STRANGER 3:15 PM appears alongside A SERIOUS MAN, PALESTINE '36, etc.

# 3. Read the 74 anti-smell offenders before deciding how to soften the rubric
.venv/bin/python scripts/check_ai_smell.py docs/data.json --verbose 2>&1 | less

# 4. Tests (baseline — same suite that merged at 2026-04-14)
.venv/bin/python -m pytest -q
.venv/bin/python scripts/verify_calendar.py --offline

# 5. Pick a variant winner (e.g. v1) and promote it in a follow-up session:
#    - Copy v1/{index.html,script.js,styles.css} into docs/ root
#    - Delete docs/variants/v{2..10}/
#    - Run verify_calendar.py + pytest
#    - Merge overnight/2026-04-15 → main

# 6. Fix T2.7 (pick one of the three options in §2 above)
```

## Work-in-tree (uncommitted at halt)

```
 M cache/summary_cache.json   # regen side effect; gitignored via .gitignore cache/
 M docs/data.json              # regenerated during T2.6; contains the 74 smelly entries and 29 refusals
 M docs/source_update_times.json  # timestamp bump
```

All three are either gitignored or will be rewritten when T2.7 is fixed. Do not commit them as-is — the data.json is in a known-bad state.

## Constraints honored throughout

- Every commit: `Hadrien-Cornier <hadrien.cornier@gmail.com>` via `-c` flags; no `~/.gitconfig` mutation.
- Zero force-pushes, zero `--no-verify`, zero `git reset --hard`.
- `main` untouched. Branch still local.
- No new dependencies installed.
- `.overnight/`, `cache/`, `.env` kept out of commits.
