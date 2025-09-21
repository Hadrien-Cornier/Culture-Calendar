### Phase Two Specification — Config‑driven Classification and Enrichment

#### Objective
Implement a self‑contained layer that, after scrapers output normalized events (Phase One), performs:
1) Classification (if enabled by venue policy) → set `event_category` from `ontology.labels` or leave null.
2) Enrichment (if enabled) → fill only missing `required_on_publish` fields for the resolved type using the event’s own text and optional cited web lookups.

Keep it minimal: deterministic LLM calls (e.g., Perplexity), strict JSON I/O, no numeric confidence, fail fast on ambiguity or malformed output.

#### Inputs
- Event dict produced in Phase One.
- Config: `config/master_config.yaml` (ontology, templates, venues, validation, date_time_spec).

#### Outputs (event augmented)
- `event_category` (string | null)
- Type fields populated only when accepted by evidence rules.
- `enrichment_meta` (minimal provenance):
  - `status`: "completed" | "skipped" | "failed"
  - `step`: "classification" | "enrichment"
  - `method`: "perplexity_v1" | "none"
  - `abstained`: boolean
  - `policy_reason`: string | null
  - `field_sources`: { field: "llm_substring" | "llm_citation" | "input" }
  - `citations`: { field: [url] }

#### Venue policy (from config)
- If `venues.<venue>.classification.enabled == false` and `assumed_event_category` is set → use assumed type; classification is skipped.
- If `classification.enabled == true` → run classifier.
- If `enrichment.enabled == false` → do not attempt enrichment.

#### Step 1 — Classification (deterministic)
- Provider: Perplexity (small model), or equivalent small LLM via `src/llm_service.py`.
- Input: `title`, `description`, `url`, `venue`, and any tags.
- Allowed labels: `ontology.labels` from config.
- Output JSON:
```json
{ "event_category": "Movie" | "BookClub" | "Concert" | "Opera" | "Dance" | "Other" | "Unknown", "abstained": true|false }
```
- Rules:
  - Temperature ≤ 0.2; strict schema; return "Unknown" and `abstained=true` if unclear.
  - No numeric confidences.

#### Step 2 — Enrichment (type‑aware, minimal)
- Target fields: the type’s `required_on_publish` from config that are currently missing.
- One LLM call asking ONLY for those missing fields.
- Acceptance rules (Fail Fast):
  - Accept value if:
    - evidence == "substring" and exact contiguous substring exists in provided input text, OR
    - evidence == "citation" and citations array is non‑empty (only if provider is allowed online by policy).
  - Otherwise discard; do not fabricate defaults.
- No overwriting of existing non‑empty fields.

Expected LLM response shape:
```json
{
  "fields": {
    "director": { "value": "John Berry", "evidence": "substring", "citations": [] },
    "runtime_minutes": { "value": "92", "evidence": "citation", "citations": ["https://..."] }
  }
}
```

#### Validation (post‑enrichment)
- Enforce `validation.fail_fast` from config.
- If `event_category` is set and any `required_on_publish` remain missing → raise an error listing missing fields.
- Enforce `date_time_spec` invariants (`dates`, `times`, formats, lengths) and snake_case.

#### Module responsibilities
- `src/enrichment_layer.py` (new):
  - `classify_event(event: dict, config: dict) -> tuple[event_category, meta]`
  - `enrich_for_type(event: dict, event_category: str, config: dict) -> tuple[updated_event, meta]`
  - `run_enrichment(event: dict, venue_key: str, config: dict) -> dict` orchestrates per venue.
- Use existing `src/llm_service.py` to invoke Perplexity with strict JSON prompt wrappers.

#### Prompts (sketch)
- System: "You classify events and extract only verifiable fields from provided text or web citations. If uncertain, abstain. Output JSON only."
- Classification user payload: includes allowed labels and event context; instruct to return one label or Unknown.
- Enrichment user payload: includes event_category, list of missing required fields, event text; instruct to return only fields that are substrings or have citations.

#### Telemetry (lightweight)
- Count classifications by label, abstentions, accepted/rejected fields, and missing required fields post‑enrichment.

#### Rollout
1) Enable only classification for `hyperreal` and `paramount`; Others remain assumed.
2) After classification is stable, enable enrichment for Movie and BookClub first; then optionally extend to Concert/Opera/Dance.
3) Keep `Other` enabled for all sources to surface expansion opportunities.

#### Acceptance criteria
- Per venue policy is respected (skip vs run).
- Events pass strict validation or fail visibly with actionable errors.
- Only verifiable enriched fields are added; no overwrites of non‑empty inputs.
- `Other` events include at minimum: `title`, `dates`, `times`, `venue`, `rating`, `one_liner_summary`, `description`, `url` (per templates).


