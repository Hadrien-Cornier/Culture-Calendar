# v12b — Fused Single-Row Scroll

```
variant: v12b
row_count:          1row
chip_shape:         pill
multi_select:       single
stickiness:         sticky-top
icon_text:          icon+text
breakpoints:        horizontal-scroll
state_persistence:  url-only
notes:              Venue and category fused into one horizontal scroll track; sticks to top with translucent backdrop
```

## Behavior

- Single scrollable track: `[All] [🎬 Film] [🎵 Concert] … | [📍 AFS] [📍 Hyperreal] …`
- Sticky with `backdrop-filter` blur for iOS/Safari affordance.
- Fade mask at edges via `mask-image` signals overflow.
- Single-select across both groups (All resets both).
