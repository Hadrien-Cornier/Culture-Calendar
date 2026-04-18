# v12a — Baseline Two-Row Pills

```
variant: v12a
row_count:          2row
chip_shape:         pill
multi_select:       single
stickiness:         static
icon_text:          text-only
breakpoints:        mobile-first-wrap
state_persistence:  url-only
notes:              Reference-point baseline — current live pattern cleaned up with /10 badge, 44px tap targets, and URL-param state
```

## Behavior

- Two rows (Venue, Category), each a wrap grid of pill chips.
- Single-select within each row (radio semantics, `role="radio"`, `aria-checked`).
- All chip = clears that row. Inline "Clear" chip appears when a selection is active.
- URL encodes `?venue=...&category=...` — backward-compat.
- Static — scrolls away with page.
- No icons; labels only.

## Hard-constraint compliance

- HC1/HC2: 2×~40px rows + ~10px padding keeps resting height under 96px mobile / 72px desktop.
- HC3: `min-height/min-width: 44px` on every chip.
- HC4: Tab traverses chips; Enter/Space toggles; native button semantics.
- HC5: `history.replaceState` on every toggle.
- HC6: Vanilla only.
- HC7: `#111` ink on `#fff` rest (16.6:1), `#fff` on `#111` active (16.6:1).
- HC8: `prefers-reduced-motion` kills transitions.
