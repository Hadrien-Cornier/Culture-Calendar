# Variant v2 — Audit

## Design: dark serif editorial single-column feed

### Accessibility
- Semantic HTML: header with h1, main element, h2 date headers
- Decorative dots use aria-hidden="true"
- External links use target="_blank" with rel="noopener"
- Keyboard navigable: tab through event links in document order
- Color contrast: #f0ebe0 on #0f0f0f (ratio ~17:1, AAA)
- Muted text #9a9488 on #0f0f0f (ratio ~5.6:1, AA)
- Accent hover #c8a96e on #0f0f0f (ratio ~7.5:1, AAA)

### Performance
- No external dependencies or frameworks
- Single fetch for data.json
- DOM built with document fragments (single reflow)
- No images or heavy assets
- CSS transitions limited to border-color (compositable)

### Responsive
- Desktop: 680px max-width centered column
- Mobile (≤600px): reduced padding, smaller font sizes
- Font sizes scale down proportionally on small screens

### Features
- ?debug_date=YYYY-MM-DD query param filters to single date
- Events sorted by date then time
- Screenings flattened from data.json screenings array
- Fallback to dates/times arrays if no screenings
- Error state shown on fetch failure

### Known Limitations
- No offline/SW caching
- No search or filter beyond debug_date
- No skip-to-content link
- axe-core automated scan not run (no headless browser available in overnight context)
