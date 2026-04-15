# Variant 9 — Swiss Poster Aesthetic — Audit

## Design Review

### Typography
- **Primary font**: Inter Tight (fallback: Helvetica Neue, Helvetica, Arial)
- **Weight range**: 400–900, using 900 for headlines and date numerals
- **Hierarchy**: 4rem title → 3rem date numbers → 0.9375rem event titles → 0.75rem metadata
- **Letter-spacing**: Tight (-0.03em) for display, wide (0.15em) for labels
- **Text-transform**: Uppercase throughout for Swiss poster fidelity

### Grid System
- 12-column CSS grid layout via `grid-template-columns: repeat(12, 1fr)`
- Time: cols 1–2, Title: cols 3–7, Meta: cols 8–10, Rating: cols 11–12
- Date headers span full 12 columns with 3-zone layout
- Responsive: collapses to flexbox at 768px

### Color Palette
- **Black** (#000000): primary text, rules, borders
- **Red** (#e50000): ratings, weekday labels, movie/opera tags
- **Blue** (#0044ff): hover state, concert/dance tags
- **White** (#ffffff): background
- **Gray scale**: #f5f5f5, #e0e0e0, #777777, #333333 for hierarchy

### Accessibility
- Sufficient contrast: black on white (21:1), red on white (4.6:1 — passes AA large text)
- Semantic HTML: header, main, aria-label on feed
- Keyboard accessible: all links focusable
- Responsive: mobile breakpoint at 768px, no horizontal overflow

### Performance
- Single external font request (Inter Tight)
- No images or heavy assets
- Vanilla JS, no framework overhead
- Minimal DOM: one pass render via DocumentFragment

### Issues
- Red (#e50000) on white achieves 4.6:1 contrast — passes AA for large/bold text but not AA for body text. Used only for labels and ratings (bold/large), so acceptable.
- No skip-to-content link (minor, single-page app with minimal header)
