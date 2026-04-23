# Persona-Critique Model Benchmark

Reference model: `us.anthropic.claude-sonnet-4-5-20250929-v1:0`. Agreement threshold: 5/N.
**Chosen model: `us.anthropic.claude-sonnet-4-5-20250929-v1:0`**

## Per-model summary

| Model | Agreement vs reference | Avg latency (s) | Total cost (USD) |
|---|---|---|---|
| `us.anthropic.claude-haiku-4-5-20251001-v1:0` | 4/6 | 54.25 | $0.0182 |
| `us.anthropic.claude-sonnet-4-5-20250929-v1:0` | 6/6 | 20.32 | $0.0445 |

## Per-persona verdicts

| Persona | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | `us.anthropic.claude-sonnet-4-5-20250929-v1:0` |
|---|---|---|
| comprehensiveness-user | PASS | PASS |
| continuity-user | FAIL | FAIL |
| logistics-user | FAIL | PASS |
| mobile-user | PASS | PASS |
| review-reader | PASS | FAIL |
| search-user | PASS | PASS |

## Notes

- All models called via tool-use (`record_persona_critique`); verdicts are read from the structured payload, not prose.
- Re-run: `.venv/bin/python scripts/bench_personas.py`
