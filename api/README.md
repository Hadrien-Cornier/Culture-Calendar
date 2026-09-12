# Culture Calendar — Agent API

Static JSON endpoints served from GitHub Pages. All responses are plain JSON, cacheable, and require no authentication. Designed for LLM agents, calendar apps, and anyone building on top of Austin cultural programming.

- Base URL: `https://hadrien-cornier.github.io/Culture-Calendar/api/`
- Discovery manifest: [`/.well-known/ai-agent.json`](https://hadrien-cornier.github.io/Culture-Calendar/.well-known/ai-agent.json)
- llmstxt.org index: [`/llms.txt`](https://hadrien-cornier.github.io/Culture-Calendar/llms.txt)
- Sitemap: [`/sitemap.xml`](https://hadrien-cornier.github.io/Culture-Calendar/sitemap.xml)
- Source & license: [github.com/Hadrien-Cornier/Culture-Calendar](https://github.com/Hadrien-Cornier/Culture-Calendar) (MIT)

## Common envelope

Every aggregate endpoint returns the same wrapper:

```json
{
  "generated_at": "2026-04-22T05:58:28Z",
  "site_url": "https://hadrien-cornier.github.io/Culture-Calendar/",
  "count": 229,
  "data": [ ... ]
}
```

- `generated_at` — ISO 8601 UTC timestamp of the build run.
- `site_url` — Canonical site root. All relative links in `data` resolve against this.
- `count` — Length of `data`.
- `data` — Array whose shape is described per endpoint below.

## Endpoints

### `GET /api/events.json`

Every upcoming event in the calendar, one row per screening/showing.

Each item:

| Field | Type | Notes |
| --- | --- | --- |
| `id` | string | Stable slug. Used as `{slug}` in `/events/{slug}.json` and `/events/{slug}.html`. |
| `title` | string | Event title. |
| `type` | string | Category slug: `movie`, `concert`, `book_club`, `opera`, `visual_arts`, `other`. |
| `rating` | integer 0–10 | AI-generated merit score. |
| `one_liner_summary` | string | ≤ ~140 chars, headline-style. |
| `description_text` | string | Long-form AI critique, plain text (no HTML). |
| `venue` | string | Venue display name (e.g. `AFS`, `LaFollia`). |
| `date` | string | `YYYY-MM-DD`, the date of this specific showing. |
| `time` | string | `HH:mm` (24h), local Austin time. |
| `url` | string | Canonical venue URL (buy tickets / confirm schedule). |
| `shell_url` | string | `{site_url}events/{id}.html` — per-event landing page. |
| `screenings` | array | All showings for this event across dates/times. Each item has `{date, time, url, venue}`. |

### `GET /api/top-picks.json`

Subset of `events.json` filtered to `rating >= 7` and sorted by rating descending. Same item shape as `events.json`.

Use when you want the recommendation answer and don't need the full catalog.

### `GET /api/venues.json`

One row per venue we scrape.

| Field | Type | Notes |
| --- | --- | --- |
| `slug` | string | Stable venue id. |
| `name` | string | Display name. |
| `event_count` | integer | Upcoming events at this venue. |
| `categories` | array of string | Category slugs present at this venue. |
| `page_url` | string | `{site_url}venues/{slug}.html` — venue landing page. |

### `GET /api/people.json`

One row per notable person (composer, director, author) linked to at least one event.

| Field | Type | Notes |
| --- | --- | --- |
| `slug` | string | Stable person id. |
| `name` | string | Display name. |
| `role` | string | `composer`, `director`, or `author`. |
| `event_count` | integer | Upcoming events featuring this person. |
| `page_url` | string | `{site_url}people/{slug}.html` — person landing page. |
| `ics_url` | string | `{site_url}people/{slug}.ics` — per-person follow feed. |

### `GET /api/categories.json`

| Field | Type | Notes |
| --- | --- | --- |
| `slug` | string | Category slug (matches `type` in events.json). |
| `label` | string | Human-readable label. |
| `count` | integer | Number of upcoming events in this category. |

### `GET /events/{slug}.json`

Per-event schema.org [Event](https://schema.org/Event) JSON-LD mirror. Slugs come from `events.json → data[].id`.

```json
{
  "@context": "https://schema.org",
  "@type": "Event",
  "name": "8 1/2",
  "description": "...",
  "url": "https://hadrien-cornier.github.io/Culture-Calendar/events/8-1-2.html",
  "image": "https://hadrien-cornier.github.io/Culture-Calendar/og/8-1-2.svg",
  "startDate": "2026-04-27",
  "location": {
    "@type": "Place",
    "name": "AFS",
    "address": {"@type": "PostalAddress", "addressLocality": "Austin", "addressRegion": "TX"}
  }
}
```

## Subscribable feeds

- `GET /feed.xml` — RSS 2.0 of top picks.
- `GET /calendar.ics` — iCalendar of every event.
- `GET /top-picks.ics` — iCalendar of top-rated events only.
- `GET /people/{slug}.ics` — iCalendar of every event featuring one person.

## Usage notes

- **No auth, no rate limit.** Standard GitHub Pages caching applies.
- **Freshness.** Regenerated on each push to `main`; `generated_at` tells you exactly when.
- **Stability.** Event `id` slugs are stable across runs for the same showing. Titles may be revised; treat `id` as the primary key.
- **Time zone.** All `date`/`time` fields are America/Chicago (Austin) local time.
- **Encoding.** All endpoints are UTF-8.
- **Recommended fetch order for an agent.** Start with `/llms.txt` or `/.well-known/ai-agent.json` for discovery, then fetch `/api/top-picks.json` for recommendations or `/api/events.json` for the full catalog, then drill into `/events/{slug}.json` for structured details.

## Crawling policy

See [`/robots.txt`](https://hadrien-cornier.github.io/Culture-Calendar/robots.txt). GPTBot, ClaudeBot, PerplexityBot, CCBot, Google-Extended, Meta-ExternalAgent, and Amazonbot are explicitly allowed.

## Reporting issues

Open an issue at [github.com/Hadrien-Cornier/Culture-Calendar/issues](https://github.com/Hadrien-Cornier/Culture-Calendar/issues).
