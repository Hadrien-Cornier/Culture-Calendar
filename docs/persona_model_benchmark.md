# Persona-Critique Model Benchmark

Reference model: `claude-sonnet-4-6`. Agreement threshold: 5/N.
**Chosen model: `claude-sonnet-4-6`**

## Per-model summary

| Model | Agreement vs reference | Avg latency (s) | Total cost (USD) |
|---|---|---|---|
| `claude-haiku-4-5-20251001` | 1/6 | 6.39 | $0.0370 |
| `claude-sonnet-4-6` | 6/6 | 16.25 | $0.1419 |
| `claude-opus-4-7` | 3/6 | 10.96 | $0.7780 |

## Per-persona verdicts

| Persona | `claude-haiku-4-5-20251001` | `claude-sonnet-4-6` | `claude-opus-4-7` |
|---|---|---|---|
| comprehensiveness-user | PASS | PASS | PASS |
| continuity-user | PASS | FAIL | FAIL |
| logistics-user | PASS | FAIL | FAIL |
| mobile-user | PASS | FAIL | PASS |
| review-reader | PASS | FAIL | PASS |
| search-user | PASS | FAIL | PASS |

## Notes

- All models called via tool-use (`record_persona_critique`); verdicts are read from the structured payload, not prose.
- Re-run: `.venv/bin/python scripts/bench_personas.py`
