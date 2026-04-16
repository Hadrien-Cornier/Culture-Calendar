# Audit — v5: NYT Events-style sticky date rail + 2-col body w/ genre chips

## Manual Review — 2026-04-15

### Accessibility
- Semantic HTML: `<header>`, `<nav>`, `<main>`, `<section>`, `<article>` used throughout
- ARIA labels on landmark regions (`date-rail`, `event-body`)
- Links have visible text; genre chips use sufficient contrast (white on dark bg)
- Keyboard navigable: all links focusable, scroll via rail links
- Color is not the only differentiator — chip text labels accompany color

### Responsive
- Mobile breakpoint at 768px converts rail to horizontal scrolling strip
- Event grid collapses to single column on mobile
- No horizontal overflow at 375px viewport

### Performance
- No external dependencies or libraries
- Single fetch to data.json
- DOM built via DocumentFragment for batch insert
- IntersectionObserver for active date highlight (no scroll listener)

### Typography
- Georgia serif for headings, system sans-serif for body
- Genre chips use uppercase small-caps treatment at 0.625rem
- Tabular nums for dates and times

### Issues Found
- None critical. Minor: IntersectionObserver fallback simply skips highlighting (graceful degradation).
