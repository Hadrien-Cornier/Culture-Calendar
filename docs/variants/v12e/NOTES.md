# v12e — Sticky-Hide Pills

```
variant: v12e
row_count:          2row
chip_shape:         pill
multi_select:       multi-or
stickiness:         sticky-hide-on-scroll-down
icon_text:          icon-only-compact
breakpoints:        horizontal-scroll
state_persistence:  url+session
notes:              Pills hide on scroll-down, return on scroll-up; mobile shows icon-only, desktop adds labels
```

## Behavior

- Scroll listener (rAF throttled) adds `.is-hidden` when delta > 6px past 120px scrollY.
- Mobile (<=480px) collapses labels to icon-only (44px squares).
- Horizontal overflow scroll within each group.
- sessionStorage fallback — forgotten on tab close.
- Honors `prefers-reduced-motion` (instant hide/show).
