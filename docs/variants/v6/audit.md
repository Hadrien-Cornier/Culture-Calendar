# Audit — v6: horizontal timeline rail drag-scroll

## Manual Review — 2026-04-15

### Accessibility
- Semantic HTML: `<header>`, `<nav>`, `<main>`, `<section>`, `<article>` used throughout
- ARIA labels on landmark regions (timeline-rail, event-area)
- Day columns have `role="button"`, `tabindex="0"`, and descriptive `aria-label`
- Keyboard support: Enter/Space on day columns scrolls to that date section
- Type dots have `aria-label` text for screen readers
- Color-coded dots are supplemented by venue text — color is not sole differentiator

### Drag/Scroll Interaction
- Mouse: mousedown starts drag, mousemove pans, mouseup releases — cursor changes to grabbing
- Touch: touchstart/touchmove with passive listeners for smooth native scrolling
- Fallback: `overflow-x: auto` ensures rail scrolls even without JS drag logic
- Hint text ("Drag or swipe to scroll") fades after first interaction

### Responsive
- Mobile breakpoint at 640px: day columns shrink to 80px, cards go single-column
- Rail remains horizontally scrollable at all viewport widths
- No horizontal overflow on event content at 375px viewport

### Performance
- No external dependencies or libraries
- Single fetch to data.json
- DOM built via DocumentFragment for batch insert
- IntersectionObserver for active day highlight and auto-centering (no scroll listener)
- `will-change: transform` on track for compositor hints
- Scrollbar hidden via `scrollbar-width: none` for clean rail appearance

### Typography
- Georgia serif for headings and date labels, system sans-serif for body
- Tabular nums for dates and times
- Compact card layout with 0.8125rem title, 0.6875rem meta

### Issues Found
- None critical. Minor: scrollbar-width: none has no -webkit equivalent (Chrome/Safari show no scrollbar by default on macOS; may show thin scrollbar on Windows Chrome).
