# v12c — Two-Row Multi-OR Tags

```
variant: v12c
row_count:          2row
chip_shape:         tag
multi_select:       multi-or
stickiness:         sticky-top
icon_text:          icon+text
breakpoints:        mobile-first-wrap
state_persistence:  url+local
notes:              Tag-shaped chips with icon slot; pick many venues OR many categories; localStorage survives fresh tab
```

## Behavior

- `?venues=afs,hyperreal&categories=movie,concert` — comma-separated URL params.
- Single-select URLs (`?venue=afs`) still resolve for backward compat.
- `aria-pressed` used (button role) since multi-select.
- Tag-shaped chip with ✓ checkmark when active.
