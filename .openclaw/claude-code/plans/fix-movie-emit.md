# Fix AFS/Hyperreal Movie Event Emission

## Context

**Problem:** `docs/data.json` contains 74 events but ZERO movies. AFS and Hyperreal venues are scraped successfully (timestamps in `source_update_times.json` confirm 2026-04-05 execution), but their events never reach the output.

**Root cause:** `processor.process_events()` at `src/processor.py:76-82` filters on `event.get("type")` and drops events where type is not in `["screening", "movie", "concert", "book_club"]`. AFS events have NO `type` field (the AFS scraper never sets it, and `base_scraper.format_event()` only sets `event_category`, not `type`). Hyperreal's type-setting code at `hyperreal_scraper.py:367-368` is dead — it iterates `template_fields` from config, but `type` is not listed in `config/master_config.yaml:31-45`. Both venues' events silently vanish.

The `determine_event_type()` function at `update_website_data.py:120-148` already handles this correctly (venue-based inference, alias normalization), but it's only called at line 325 inside `generate_website_data()` — AFTER `process_events()` has already discarded the events.

---

## Plan

### Step 1: Normalize event types before processor filtering

**File:** `update_website_data.py`
**Location:** After line 479 (`print(f"Processing {len(upcoming_events)} total events")`) and before line 483 (`enriched_events = processor.process_events(upcoming_events)`)

Insert:

```python
        # Normalize event types BEFORE processor filtering.
        # Some scrapers (AFS) do not set event["type"]; infer from venue/fields.
        for event in upcoming_events:
            if not event.get("type"):
                event["type"] = determine_event_type(event)
        movie_count = sum(1 for e in upcoming_events if e.get("type") == "movie")
        print(f"After type normalization: {movie_count} movie events")
```

**Why:** `determine_event_type()` already exists in this file and correctly infers `"movie"` from AFS/Hyperreal venue names and film metadata fields. Calling it before the processor ensures events aren't filtered out. Only events with no `type` are touched — existing typed events are unchanged.

### Step 2: Add `type` to movie template fields in config

**File:** `config/master_config.yaml`
**Location:** Line 31-45, the `templates.movie.fields` list

Add `- type` after `- title` (line 32):

```yaml
  movie:
    grouping: by_title
    fields:
      - title
      - type
      - dates
      ...
```

**Why:** This un-dead-codes `hyperreal_scraper.py:367-368` where `event["type"] = "movie"` is set inside a `for field in self.template_fields` loop. Currently `type` is not in `template_fields` so that branch never executes. Defense-in-depth: ensures Hyperreal sets its own type even without the Step 1 normalization.

### Step 3: Rebuild output files

Run:
```bash
python update_website_data.py
```

**Preconditions:** `.env` must have `PERPLEXITY_API_KEY` and `ANTHROPIC_API_KEY` set.

**Expected output:**
- Console: `"After type normalization: N movie events"` where N > 0
- Console: NO `"WARNING: 0 'movie' events after typing"` message
- `docs/data.json` — now contains movie events with AFS/Hyperreal venues
- `docs/source_update_times.json` — updated timestamps

### Step 4: Verify output

Check `docs/data.json`:
- Contains events with `"type": "movie"` or movie-specific fields (`director`, `runtime_minutes`)
- Contains events from venues `"AFS"` / `"Austin Film Society"` and `"Hyperreal"` / `"Hyperreal Movie Club"`
- Movie events are grouped by title (per `grouping: by_title` config)
- Each movie has `occurrences` array with date/time/venue/url

### Step 5: Commit and push

```bash
git add update_website_data.py config/master_config.yaml docs/data.json docs/source_update_times.json
git commit -m "fix: emit AFS/Hyperreal movies by normalizing type before processor filter

AFS events had no 'type' field set by the scraper, causing
processor.process_events() to silently drop them. Hyperreal's
type-setting code was dead because 'type' was missing from the
movie template fields list.

- Add type normalization pass before processor filtering
- Add 'type' to movie template fields in master_config.yaml
- Rebuild docs/data.json with movie events included"

git push origin cc/fix-movie-emit
```

Then merge to main:
```bash
git checkout main
git merge cc/fix-movie-emit
git push origin main
```

### Step 6: Verify GitHub Pages

After push, confirm `hadrien-cornier.github.io/Culture-Calendar` shows movie events from AFS and Hyperreal.

---

## Files Modified

| File | Change |
|------|--------|
| `update_website_data.py` | Add type normalization loop before `process_events()` call (~4 lines) |
| `config/master_config.yaml` | Add `- type` to `templates.movie.fields` list (1 line) |
| `docs/data.json` | Rebuilt by pipeline (now includes movies) |
| `docs/source_update_times.json` | Rebuilt by pipeline (updated timestamps) |

## Files NOT Modified (no changes needed)

| File | Reason |
|------|--------|
| `src/processor.py` | Step 1 ensures correct `type` before it reaches the filter |
| `src/scrapers/afs_scraper.py` | Centralized normalization is better than per-scraper fixes |
| `src/scrapers/hyperreal_scraper.py` | Step 2 un-dead-codes its existing type assignment |
| `src/base_scraper.py` | `event_category` vs `type` mismatch is addressed upstream |
