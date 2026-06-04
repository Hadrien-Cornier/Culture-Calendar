# Personas

Quality is enforced by the reusable **llm-council** skill: a cross-family
judge panel with **enforced diversity** — the maker family (Anthropic) is
**excluded from judging**, and every juror comes from a distinct non-Anthropic
family (OpenAI, DeepSeek, Moonshot, z-ai, Google, Xiaomi). This replaced the old
bespoke, Anthropic-only persona-critique scripts.

Two artifact kinds live here, both JSON:

## `personas/council/` — judge personas (schema-conformant)

Nine JSON specs conforming to the **llm-council skill schema** (`name`,
`dimension`, `goal`, `verdict_contract`, `system_prompt`, `rubric_variants`,
`must_not_flag`, …). Each is consumed by `.council/llm-council/scripts/council-judge.sh`,
which fences the artifact under review as `<untrusted>…</untrusted>`, calls the
juror model via OpenRouter, and records one `record_review` tool call returning
`{verdict: PASS|FAIL|ABSTAIN, summary, findings[]}`.

**Code-review panel** (judges a diff — `.council/culture-calendar.json`):

| Persona | Lens |
|---|---|
| `review-quality` | Senior-engineer lens. Flags diffs that silently weaken AI review generation (dropped evidence requirements, lowered confidence thresholds, removed `review_confidence` propagation, generic prompts replacing category-specific dispatch). |
| `repo-minimalism` | Karpathy/nanochat lens. Flags ceremony, helper graveyards, premature abstraction, parallel near-duplicate files, config knobs with no readers, defensive scaffolding, doc bloat. |
| `synthesis-judge` | Synthesis layer that reconciles the panel into a final verdict. |

**Live-site UX panel** (judges the deployed site — `.council/live-site.json`):

| Persona | User story |
|---|---|
| `logistics-user` | Friday planner — needs `.event-when` + venue address visible without expanding. |
| `review-reader` | Skim AI reviews — wants formatted sections, readable contrast, and TTS. |
| `search-user` | Find a known title or venue fast via the masthead search. |
| `comprehensiveness-user` | Confirms the calendar covers all advertised categories + venues. |
| `continuity-user` | Asserts every feature-inventory entry still resolves on the live site. |
| `mobile-user` | iPhone-class viewport — search above the fold, tap targets, WCAG AA contrast. |

## `personas/live-site-specs/` — structural specs (no LLM)

Six JSON specs (one per live-site lens) consumed by `scripts/check_live_site.py`
and `scripts/capture_live_site_context.py`. These are the persona JSONs **minus**
any LLM block — just `persona`, `url`, optional `mobile` / `wait_*` /
`click_before_assert`, `asserts`, and `pre_screenshot_actions`. They encode the
deterministic ground truth: pyppeteer assertion lists (`selector_exists`,
`js_truthy`, …) that pass or fail without any model call.

`capture_live_site_context.py` serves `docs/` on localhost, runs each spec's
asserts, and writes one combined markdown context file. The council then judges
that context — so per-feature regressions are caught structurally, and the
cross-family panel adds holistic UX judgment on top.

## `.council/` — manifests + vendored runtime

| File | Role |
|---|---|
| `.council/culture-calendar.json` | Code-review panel manifest (panel + synthesis). Used by the PR-validation `council-review` job and the long-run task gate. |
| `.council/live-site.json` | Live-site panel manifest (six UX lenses, no synthesis). Used by the pre-push `[persona-gate]`. |
| `.council/llm-council/scripts/council-judge.sh` | Vendored council runtime. Reads a manifest + `--context-file`, calls OpenRouter, writes per-persona review JSONs, aggregates verdicts (any FAIL → exit 1 REJECT, all ABSTAIN → exit 2 ESCALATE, else 0 ACCEPT). |
| `.council/llm-council/references/review-tool-schema.json` | The `record_review` tool schema the jurors must emit against. |

Each manifest sets `maker.family = anthropic` and lists one juror per distinct
non-Anthropic family. `persona_spec_path` points at the matching
`personas/council/*.json` (relative to repo root — `council-judge.sh` is invoked
from there in every gate). Model slugs come from the skill's
`cache/model-pool.json`. Needs `OPENROUTER_API_KEY`; all three gates degrade
gracefully (skip, never hard-block) when it is absent.

## How the gates run

1. **Pre-push** (`.githooks/pre-push`) — on a `[persona-gate]`-tagged commit:
   `capture_live_site_context.py` builds the structural context, then
   `council-judge.sh --council .council/live-site.json` judges it. Activate
   per-clone: `git config core.hooksPath .githooks`.
2. **PR validation** (`.github/workflows/pr-validation.yml` → `council-review`):
   `council-judge.sh --council .council/culture-calendar.json --context-file <PR diff>`.
   Report-only; skips neutrally without the secret.
3. **Long-run tasks** — the autonomous-run harness judges each task with
   `.council/culture-calendar.json`; any FAIL re-queues the task.

## (Re)generating manifests

1. Refresh the model pool with the llm-council skill's
   `scripts/refresh-model-pool.py` (queries OpenRouter for the current frontier).
2. Re-pick slugs in `.council/*.json`: **one juror per distinct non-Anthropic
   family**, Anthropic excluded as the maker. Keep `family` accurate — the
   family-exclusion invariant is what the diversity guarantee rests on.
3. Runtime is `.council/llm-council/scripts/council-judge.sh`; no codegen step —
   editing the manifest is sufficient.

## Adding a persona

1. Drop a schema-conformant JSON spec under `personas/council/`.
2. For a live-site lens, also add the structural-only twin under
   `personas/live-site-specs/` (drop the LLM block, keep `asserts`).
3. Register it in the relevant `.council/*.json` manifest with a `model` from a
   not-yet-used non-Anthropic family and a `persona_spec_path`.
4. Document it in the table above.
