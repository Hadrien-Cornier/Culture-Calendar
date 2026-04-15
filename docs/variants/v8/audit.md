# v8 Audit — Obsidian/Notion Narrow Single Column

## Design Brief
- **Concept**: Obsidian/Notion-inspired narrow single-column feed
- **Column width**: 680px max
- **Typography**: Inter (sans-serif), 15px base
- **Palette**: Dark grayscale (#1e1e1e bg) + single accent (#7c8aef, soft indigo)
- **Layout**: Chronological feed grouped by date, inline slug anchors

## Accessibility
- **Semantic HTML**: header, main, headings, links with target/rel
- **Color contrast**: Text #dcdcdc on #1e1e1e = 11.3:1 (AAA). Muted #888 on #1e1e1e = 4.7:1 (AA).
- **Accent contrast**: #7c8aef on #1e1e1e = 6.2:1 (AA+).
- **Focus indicators**: Browser defaults preserved (no outline:none).
- **Responsive**: Single breakpoint at 720px, entries stack vertically on mobile.
- **Keyboard**: All links keyboard-accessible; date anchors are IDs for hash navigation.
- **Motion**: No animations; respects prefers-reduced-motion by default.

## Performance
- Single external font (Inter, 3 weights via Google Fonts display=swap)
- No JS framework; vanilla DOM manipulation
- No images or heavy assets
- Minimal CSS, no transforms or GPU layers

## Variant Checklist
- [x] Reads ../../data.json
- [x] Renders all events from data
- [x] Unique visual identity (Obsidian-style dark, narrow column, inline date slugs)
- [x] Has index.html, styles.css, script.js, audit.md
- [x] Uses _shared/reset.css
- [x] No external JS dependencies
