# Persona-Critique Model Benchmark

Reference model: `claude-sonnet-4-6`. Agreement threshold: 5/N.
**Chosen model: `claude-sonnet-4-6`**

## Per-model summary

| Model | Agreement vs reference | Avg latency (s) | Total cost (USD) |
|---|---|---|---|
| `claude-haiku-4-5-20251001` | 3/6 | 7.96 | $0.0326 |
| `claude-sonnet-4-6` | 6/6 | 11.92 | $0.0975 |
| `claude-opus-4-7` | 4/6 | 12.74 | $0.6229 |

## Per-persona verdicts

| Persona | `claude-haiku-4-5-20251001` | `claude-sonnet-4-6` | `claude-opus-4-7` |
|---|---|---|---|
| comprehensiveness-user | PASS | PASS | PASS |
| continuity-user | FAIL | FAIL | FAIL |
| logistics-user | UNKNOWN | PASS | PASS |
| mobile-user | UNKNOWN | FAIL | PASS |
| review-reader | UNKNOWN | FAIL | UNKNOWN |
| search-user | PASS | PASS | PASS |

## Notes

- Structured-output upgrade pending (see Port 2). Until then verdicts are parsed from the first token of each critique.
- Re-run: `.venv/bin/python scripts/bench_personas.py`
