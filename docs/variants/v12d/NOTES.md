# v12d — Bottom-Sheet Compact

```
variant: v12d
row_count:          0row
chip_shape:         rect
multi_select:       multi-and
stickiness:         static
icon_text:          icon+text
breakpoints:        collapse-to-sheet
state_persistence:  url+local
notes:              Filters hidden behind "Filters" trigger; on mobile the panel rises as a bottom sheet with grab handle
```

## Behavior

- Closed state: single 44px-tall trigger with active-count badge. Under 72px total.
- Open state (desktop): inline popover below trigger.
- Open state (mobile): fixed bottom sheet with grab handle, `max-height: 70vh`.
- Multi-select within a group (OR), AND across groups.
- `<details>` element gives us native keyboard + a11y for open/close; Esc closes via browser default.
