# v11g Pitchfork — Audit Report

## Design Characteristics

- **Masthead**: Bold display serif title (Didot/Bodoni-inspired, 56px, 900 weight)
- **Color scheme**: Dark background (#0a0a0a) with vibrant accent (#ff6b35), high-contrast text
- **Rating chips**: Prominent focal point — 80px squares with bold sans-serif numbers (36px)
- **One-liner**: Large (22px), italic, accent-colored emphasis
- **Layout**: Information architecture preserved from v11-picks-plus

## Visual Hierarchy

1. **Primary**: Rating chip (huge, colored, centered in event header)
2. **Secondary**: Event title (Georgia serif, 21px bold)
3. **Tertiary**: One-liner expansion (italic, accent-colored, 22px)
4. **Supporting**: Metadata, times, review text

## Accessibility Notes

- High contrast (white/light gray text on dark background)
- Large rating chips (80px) with clear color differentiation
- Focus states maintained for keyboard navigation
- Reduced-motion respects prefers-reduced-motion

## Performance

- No layout-thrashing animations (max-height transition only)
- CSS Grid for efficient layout
- Minimal repaints on expand/collapse

## Known Limitations

- Display serif fonts (Didot, Bodoni) may fallback to Georgia on systems without them
- No web font loading (system fonts only)
- Rating chip color contrast: MID bucket (#ffb81c on #1a1a1a) near WCAG AA threshold

## Implementation Notes

- Event header grid: 80px rating badge, flexible title column, 20px expand indicator
- Pick item grid: 50px number, 50px rating badge, flexible title
- Fully responsive mobile breakpoint at 600px
- Dark theme reduces eyestrain for evening event browsing
