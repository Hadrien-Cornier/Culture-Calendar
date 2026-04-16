# Audit — v4: Terminal/Monospace High-Density Keyboard-Nav

## Accessibility

- **Keyboard navigation**: Full vim-style keyboard support — j/k to navigate rows, / to filter, ? for help overlay, Enter to open links, g/G to jump top/bottom.
- **ARIA**: Table uses `role="grid"`, rows use `role="row"` with `aria-selected` for current selection. Help overlay uses `role="dialog"` with `aria-label`.
- **Screen reader**: Filter input has `aria-label`. Help shortcuts use semantic `<kbd>` elements.
- **Color contrast**: Primary text (#c8c8c8 on #0c0c0c) ratio ~13:1, exceeds WCAG AAA. Accent (#00d4aa on #0c0c0c) ratio ~10:1, exceeds AA. Dim text (#666666 on #0c0c0c) ratio ~3.7:1, meets AA for large text; used only for secondary metadata.
- **Reduced motion**: `prefers-reduced-motion` disables row transition.

## Design Rationale

- Terminal aesthetic: JetBrains Mono / IBM Plex Mono fallback chain. 13px / 14px line-height for high density.
- Dark palette (#0c0c0c base) with teal accent (#00d4aa) — inspired by classic terminal themes.
- Grid layout: 5-column table (date, rating, title, venue+tag, spacer) fits ~30+ rows without scrolling on 1080p.
- Type tags use bordered outline style rather than filled chips — lower visual weight, better scannability.
- Filter bar mimics command-line input with `/` prompt character.

## Responsive Layout

- **Desktop (>768px)**: 5-column grid, 1400px max-width, full header hints.
- **Mobile (<768px)**: 4-column (venue hidden), header hints hidden, smaller font.

## Performance

- Zero external dependencies, no images, no web fonts loaded (relies on local monospace fonts with system fallbacks).
- Single fetch of data.json, DOM built with document fragment.
- Row selection uses CSS attribute selector — no class toggling, minimal reflow.

## Known Limitations

- Web fonts (JetBrains Mono) fall back to system monospace if not installed locally.
- Detail pane (via Enter on URL-less events) is minimal; could be enhanced with more event metadata.
- Mobile keyboard navigation less relevant but still functional.
