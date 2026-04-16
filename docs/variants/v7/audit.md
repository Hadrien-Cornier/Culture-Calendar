# Audit — v7: calendar heatmap first, click cell to reveal events

## Manual Review — 2026-04-15

### Accessibility
- Semantic HTML: `<header>`, `<section>`, `<main>` used for landmarks
- Heatmap grid has `role="grid"` and `aria-label`
- Each cell is a `<button>` with descriptive `aria-label` ("Apr 15: 3 events")
- Keyboard navigable: buttons are focusable, `focus-visible` outline provided
- `aria-live="polite"` on event panel announces content changes to screen readers
- Type dots supplemented by venue text — color is not sole differentiator
- Weekday labels marked `aria-hidden` since cells carry their own labels

### Interaction Design
- GitHub contributions-style grid: 60-day window, 7 rows (Sun–Sat), columns per week
- Intensity levels 0–4 based on event count quartiles relative to max
- Click cell to expand event list below the heatmap
- Selected cell highlighted with accent outline
- Hover tooltip shows full date and event count
- Empty padding cells are disabled and hidden from assistive tech

### Responsive
- Mobile breakpoint at 640px: smaller cells (11px), event items stack vertically
- Container allows horizontal scroll if grid overflows on very narrow screens
- Max-width 960px centers content on large screens

### Performance
- No external dependencies or libraries
- Single fetch to data.json
- DOM built via DocumentFragment for heatmap grid
- Tooltip created/destroyed on hover (no persistent DOM nodes)
- Event panel rendered on demand (click), not pre-rendered for all dates

### Typography
- System font stack for body text, monospace for times and ratings
- Date panel heading at 1.125rem, body at 0.875rem, meta at 0.75rem
- Dark theme (GitHub-dark inspired) with green intensity scale

### Issues Found
- Month labels use absolute positioning — may overlap if two months start in adjacent weeks on very narrow viewports. Functional but cosmetically imperfect.
- No animation on cell selection or panel transition — intentional to keep implementation minimal.
