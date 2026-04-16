
/Users/HCornier/Documents/Personal/Culture-Calendar/docs/variants/v11e/styles.css
  line 218: [layout-transition] transition: max-height, padding
    → Animating width, height, padding, or margin causes layout thrash and janky performance. Use transform and opacity instead, or grid-template-rows for height animations.

1 anti-pattern found.

## v11e — Monocle

Neutral palette with hairline borders and low-contrast typography.

- **Color scheme**: Ecru background (#f6f1e7), graphite text (#2b2b2b)
- **Borders**: 0.5px hairline rules throughout
- **Typography**: Serif body, sans labels (tracked uppercase)
- **IA preserved**: Picks section, event listings, expandable panels
- **Status**: Audit shows 1 known layout-transition anti-pattern (inherit from v11-picks-plus)
