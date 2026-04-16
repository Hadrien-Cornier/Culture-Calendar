# Audit — v3: Grid of Cards with Poster Thumbnails + Hover Flip

## Manual Accessibility Review

- **Keyboard navigation**: Cards are focusable via `tabIndex=0` and `role="group"` with `aria-label`. Focus triggers flip via `:focus-within`.
- **Screen reader**: `aria-hidden="true"` on decorative poster text. Card container has descriptive `aria-label`.
- **Color contrast**: Dark back-face (#1a1a1a bg, #e8e8e8 text) meets WCAG AA (contrast ratio ~12:1). Front face (#1a1a1a on #fff) exceeds AA.
- **Motion**: `prefers-reduced-motion` not handled — flip animation plays regardless. Recommendation: add `@media (prefers-reduced-motion: reduce)` to disable flip transition.
- **Touch**: Hover flip may not activate on touch devices. Mobile layout (1-col) mitigates by making cards larger, but a tap-to-flip fallback would improve UX.

## Responsive Layout

- **Desktop (>1024px)**: 3-column grid, 1200px max-width.
- **Tablet (769–1024px)**: 2-column grid.
- **Mobile (<768px)**: 1-column grid, reduced padding and card height.

## Performance

- No external dependencies or images loaded.
- Poster thumbnails are CSS gradients (zero network requests).
- DOM built from single fetch of data.json.
- Card flip uses `transform: rotateY()` (GPU-composited, no layout thrashing).

## Known Limitations

- `check_variant.mjs` validation script does not exist; manual review performed.
- Hover-flip interaction not ideal for touch-only devices.
- `prefers-reduced-motion` media query not implemented.
