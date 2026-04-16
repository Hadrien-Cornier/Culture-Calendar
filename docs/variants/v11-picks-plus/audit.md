# v10 Audit — Critics Tipsheet

## Design
- Rating-sorted event listing with inline review expansion
- Top-10 picks of the week hero section
- Newspaper/tipsheet aesthetic with serif typography and dark masthead

## Accessibility
- Semantic HTML: header, section, main, ol for picks
- Keyboard-navigable expand/collapse with role="button", tabindex="0", aria-expanded
- Sufficient color contrast on all rating badges
- Responsive layout with mobile breakpoint at 600px

## Performance
- Vanilla JS, no dependencies
- Single data fetch from ../../data.json
- DocumentFragment for batch DOM insertion
- Deduped showings to avoid duplicates

## Features
- Events grouped by title (not flattened per-screening)
- Sorted by rating descending, then alphabetically
- Click/keyboard expand reveals full review text + showing chips
- Top-10 picks extracted from highest-rated events
- Category tags and venue/showing count in subtitle
