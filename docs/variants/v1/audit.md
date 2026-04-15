# Variant v1 — Audit

## Design: austintango-style scroll list with left date jump-nav

### Accessibility
- Semantic HTML: header, nav (aria-label), main, h2 date headers
- All links have visible text; decorative dots use aria-hidden
- External links use target="_blank" with rel="noopener"
- Keyboard navigable: tab through rail links and event links
- Color contrast: #1a1a1a on #faf9f7 (ratio ~15:1, AAA)
- Muted text #6b6b6b on #faf9f7 (ratio ~4.8:1, AA)

### Performance
- No external dependencies or frameworks
- Single fetch for data.json
- DOM built with document fragments (single reflow)
- Scroll spy uses requestAnimationFrame + passive listener
- No images or heavy assets

### Responsive
- Desktop: 960px max-width, 120px date rail
- Mobile (≤600px): 72px rail, wrapped venue line
- Narrow (≤374px): rail hidden, full-width list

### Features
- ?debug_date=YYYY-MM-DD query param filters to single date
- Sticky date rail with scroll spy highlighting
- Events sorted by date then time
- Screenings flattened from data.json screenings array
- Fallback to dates/times arrays if no screenings

### Known Limitations
- No offline/SW caching
- No search or filter beyond debug_date
- axe-core automated scan not run (no headless browser available in overnight context)
