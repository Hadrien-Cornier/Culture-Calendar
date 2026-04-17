# Impeccable Audit — docs/ (v11-picks-plus promoted)

**Date:** 2026-04-17
**Scope:** `docs/index.html`, `docs/styles.css`, `docs/script.js`
**Method:** Manual review against the seven Impeccable reference dimensions (typography, color & contrast, spatial design, interaction design, responsive design, motion design, ux writing).
**Severity legend:** CRITICAL (block) · HIGH (should fix before merge) · MEDIUM (plan to fix) · LOW (polish).
**Status legend:** OPEN (not started) · IN PROGRESS · RESOLVED.

Counts: 4 CRITICAL · 9 HIGH · 12 MEDIUM · 7 LOW. All OPEN.

---

## 1. Typography

### [HIGH] T-01 — Body font sizes declared in px, not rem — OPEN
**Where:** `docs/styles.css:21` `font-size: 17px`; dozens of `px` sizes throughout (11–36 px).
**Problem:** Reference `typography.md:137` — "Use rem/em for font sizes: this respects user browser settings. Never `px` for body text." Users who enlarge default text in browser settings (accessibility need) get no scaling.
**Fix:** Introduce `:root { font-size: 100%; }` and convert body + component sizes to `rem`. Establish a 5-step modular scale (e.g. `--text-xs: 0.75rem`, `--text-sm: 0.875rem`, `--text-base: 1rem`, `--text-lg: 1.1875rem`, `--text-xl: 2.25rem`).

### [HIGH] T-02 — Too many font sizes, too close together — OPEN
**Where:** Inventory across `styles.css`: 11, 12, 13, 14, 15, 16, 17, 19, 28, 36 px. Ten distinct sizes.
**Problem:** `typography.md:12–14` — "too many font sizes that are too close together ... creates muddy hierarchy." 11/12/13/14 is four near-identical steps.
**Fix:** Collapse to 5 tokens and reassign every rule. Likely mapping: xs (12), sm (14), base (16–17), lg (19), xl (28–36).

### [MEDIUM] T-03 — No fluid headline type — OPEN
**Where:** `.masthead-title` is `36px` with a single hard step to `28px` at `<600px`.
**Problem:** `typography.md:98–100` recommends `clamp()` for display headings. One hard breakpoint produces a visible jump at 601 px.
**Fix:** `font-size: clamp(1.75rem, 4.5vw + 0.5rem, 2.5rem);` — scales smoothly between 28 and 40 px.

### [MEDIUM] T-04 — No fallback font metrics defined — OPEN
**Where:** `:root --serif` / `--sans` stacks.
**Problem:** `typography.md:77–89` — without `size-adjust`/`ascent-override`, fallback fonts produce layout shift (FOUT). The serif stack starts with "Iowan Old Style" (macOS only); Windows/Linux fall back to Palatino/Georgia which have different metrics.
**Fix:** Define a `@font-face` fallback block with `size-adjust` and `ascent-override` tuned to Iowan/Charter metrics, or standardize on Georgia as the canonical metric target and accept the compromise.

### [MEDIUM] T-05 — Vertical rhythm not anchored to a base unit — OPEN
**Where:** Margins/paddings use a mix of `em`, `px`, and odd decimals (`0.82em`, `1.07em`, `1.18em`, `2.35em`).
**Problem:** `typography.md:5–7` — spacing should be multiples of the line-height (17 × 1.55 ≈ 26 px). Current values are arbitrary.
**Fix:** Replace ad-hoc margins with spacing tokens on a 4 pt scale (see S-01).

### [LOW] T-06 — `font-variant: small-caps` instead of explicit OpenType feature — OPEN
**Where:** `.event-dateline` line 307.
**Problem:** `font-variant: small-caps` synthesizes fake small caps when the font lacks a real small-caps glyph set; Iowan Old Style on macOS has real small caps but Georgia does not, so the visual breaks across platforms.
**Fix:** `font-variant-caps: all-small-caps; font-feature-settings: "smcp", "c2sc";` and accept that the fallback font will not render true small caps — keep the letter-spacing override that already compensates.

### [LOW] T-07 — No explicit kerning / ligature tokens — OPEN
**Where:** Missing `font-kerning: normal;` and `text-rendering: optimizeLegibility;` on body.
**Problem:** `typography.md:119–124` — "enable kerning (usually on by default, but be explicit)."
**Fix:** Add to `body { font-kerning: normal; text-rendering: optimizeLegibility; }`.

---

## 2. Color & Contrast

### [HIGH] C-01 — Token format is hex, not OKLCH — OPEN
**Where:** `:root` tokens lines 2–10.
**Problem:** `color-and-contrast.md:3–7` — "Stop using HSL. Use OKLCH ... it's perceptually uniform." Hex is even further removed; adjusting lightness/chroma independently is impossible.
**Fix:** Migrate to OKLCH. Example: `--accent: oklch(48% 0.13 32);` `--ink: oklch(20% 0.005 80);` `--muted: oklch(40% 0.005 80);`. Preserve visual appearance; gain tunable axes.

### [HIGH] C-02 — Neutrals are pure gray — OPEN
**Where:** `--ink: #111`, `--muted: #5c5c5c`, `--rule: #e5e4de` (rule has slight warm cast, but ink/muted do not).
**Problem:** `color-and-contrast.md:13–19` — "Pure gray is dead. A neutral with zero chroma feels lifeless next to a colored brand." The accent `#b1432a` is warm terracotta; neutrals should be tinted the same hue.
**Fix:** Shift `--ink` and `--muted` to `oklch(L c 32)` with tiny chroma (0.004–0.008) matching accent hue 32.

### [MEDIUM] C-03 — `--muted` at 13 px passes AA but fails AAA — OPEN
**Where:** `.pick-meta` `.event-subtitle` `.event-review-label` use `--muted: #5c5c5c` on `#fafaf7`.
**Problem:** Computed contrast 6.4:1 — passes WCAG AA body text (4.5:1) but falls short of AAA (7:1). Task notes flagged this as a concern. Small UI metadata is exactly the place users with mild vision loss suffer.
**Fix:** Darken `--muted` to ~`oklch(36% 0.005 32)` (~#4c4c4c, ~8.5:1) or reserve the current value for 14 px+ and introduce `--muted-strong` for 11–13 px usage. WebAIM check required after change.

### [MEDIUM] C-04 — Review body color is off-token — OPEN
**Where:** `.event-review-body { color: #2a2a28; }` and `.event-review-text { color: #333; }`.
**Problem:** These bypass the `--ink` token and drift from the system. Also introduces two near-identical text darks without semantic reason.
**Fix:** Replace both with `var(--ink)` (or a new `--text-prose` token if genuinely a different role).

### [MEDIUM] C-05 — No dark mode — OPEN
**Where:** No `@media (prefers-color-scheme: dark)` block.
**Problem:** `color-and-contrast.md:81–93` — users who set dark OS preference get an aggressively light page at night. Editorial content especially benefits from dark mode.
**Fix:** Duplicate the `:root` token block under `@media (prefers-color-scheme: dark) { :root { ... } }` with inverted lightness, slightly desaturated accent, and surface scale built from lightness (not shadow). Non-trivial scope — call out as follow-up if deferred.

### [LOW] C-06 — Rating color semantics rely on color alone — OPEN
**Where:** `.rating-high` `.rating-mid` `.rating-low` — green/amber/red pills.
**Problem:** `color-and-contrast.md:105` — "Avoid relying on color alone to convey information. 8% of men affected by color vision deficiency." The numeric rating inside the pill is the real signal (good), but users scanning the list by color alone will misread red/green.
**Fix:** Already mitigated by the number itself — low. Optional: add a tiny pattern (dot, underline) or shape cue if audit re-prioritizes.

### [LOW] C-07 — `--accent-soft: #f3e4de` hover background only 1.1:1 vs body bg — OPEN
**Where:** `.event-header:hover { background: var(--accent-soft); }`
**Problem:** Hover signal is perceptible but faint against `--bg: #fafaf7`. Non-essential decoration so WCAG does not require contrast, but on bright displays the hover is barely visible.
**Fix:** Deepen `--accent-soft` by ~5 % lightness, or add a 1 px accent-tinted left border on hover.

---

## 3. Spatial Design

### [HIGH] S-01 — No spacing token system — OPEN
**Where:** Entire stylesheet.
**Problem:** `spatial-design.md:5–11` — "Use 4 pt for granularity: 4, 8, 12, 16, 24, 32, 48, 64, 96 px. Name by relationship (`--space-sm`), not value."
**Fix:** Add `--space-1: 4px` through `--space-8: 64px` as root tokens. Replace every `em`/`px` padding and margin with a token.

### [HIGH] S-02 — Hard-coded padding-left: 70px breaks alignment math — OPEN
**Where:** `.event-showings-list` `.event-panel` `.event-card.is-expanded .event-panel` — `padding: 0 16px 12px 70px` and `padding-left: 70px`.
**Problem:** 70 px is meant to match the 40 px badge + 14 px gap + 16 px header padding = 70 px, but those upstream values can drift. Already does: mobile query drops `.event-header` gap to 10 px and padding to 12 px (36+10+12=58), yet `.event-panel` still inherits 70 px until overridden to 12 px — visual hang changes.
**Fix:** Use CSS grid alignment (`subgrid` or matching grid-template-columns on the card) or a `--indent-content: calc(var(--badge-size) + var(--space-sm) + var(--space-md))` variable referenced everywhere.

### [MEDIUM] S-03 — Touch targets below 44 px on mobile — OPEN
**Where:** `.event-header` mobile padding `12px`, `.pick-item` mobile padding `10px 12px` → effective tap target height ~44 px for header, but pick item is closer to 36 px. `.pick-title a` link is even smaller.
**Problem:** `spatial-design.md:78` — "44 px minimum."
**Fix:** Verify computed heights with DevTools; expand `.pick-title a` tap target via `padding: 4px 0` + negative margin, and ensure `.pick-item` min-height: `44px`.

### [MEDIUM] S-04 — Hierarchy rests on size alone, not multiple dimensions — OPEN
**Where:** `.picks-heading` vs `.listings-heading` vs event titles.
**Problem:** `spatial-design.md:32–43` — combine size, weight, color, and space. Both section headings share identical styling (14 px uppercase accent) so "picks" and "all events" feel equivalent despite the picks being the editorial lead.
**Fix:** Give `.picks-heading` slightly more weight (700 vs 600), a rule above instead of below, or pair with an italic serif lead-in tagline.

### [MEDIUM] S-05 — No container queries for event-card — OPEN
**Where:** Event card is viewport-responsive only.
**Problem:** `spatial-design.md:49–71` — if the card ever appears in a narrower context (sidebar, print, embed), it cannot adapt. Current promotion embeds this site inside an iframe for potential future use.
**Fix:** Wrap `.event-card` in `container-type: inline-size;` on `.listings` and convert the `@media (max-width: 600px)` header rules into `@container (max-width: 520px)`.

### [LOW] S-06 — Optical alignment of numeric counter not offset — OPEN
**Where:** `.pick-item::before { content: counter(pick); }` — renders "1." style number in 36 px column.
**Problem:** `spatial-design.md:72–75` — "margin-left: 0 looks indented due to letterform whitespace." Numeric glyphs with tabular-nums already read centered, but an optical `-0.05em` nudge tightens rows.
**Fix:** Minor `margin-left: -0.02em` on the ::before, or rely on tabular-nums and skip.

### [LOW] S-07 — No elevation scale — OPEN
**Where:** Cards have only a 1 px border; no shadow hierarchy.
**Problem:** `spatial-design.md:94–96` — reasonable for this flat editorial aesthetic but means any future modal/toast will be ungrounded.
**Fix:** Add `--shadow-sm`, `--shadow-md` tokens ready for future use even if unused today.

---

## 4. Interaction Design

### [CRITICAL] I-01 — Event header accessibility: div with role="button" instead of real button — OPEN
**Where:** `script.js:430` — `header.setAttribute("role", "button")` on a `<div>`.
**Problem:** `interaction-design.md` — real `<button>` gives free keyboard, focus, screen-reader support. Current implementation wires keydown manually (line 433) but the button contains nested links (`<a class="event-title-link">`). Buttons inside buttons are invalid HTML and screen readers announce both, confusingly.
**Fix:** Convert to `<button type="button" class="event-header">` containing no interactive descendants, and move the external-site link to the title area *outside* the header, or use a disclosure pattern where the button is a dedicated "expand" affordance separate from the title link.

### [CRITICAL] I-02 — Focus-visible missing on most links — OPEN
**Where:** `.pick-title a`, `.event-title-link` — only `.event-header:focus-visible` exists.
**Problem:** `interaction-design.md:20–42` — "Never `outline: none` without replacement." Browser default outline is suppressed in `variants/_shared/reset.css` (unverified but conventional); keyboard users lose focus indicators on every external link in the picks list and title.
**Fix:** Add `.pick-title a:focus-visible, .event-title-link:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 2px; }`.

### [HIGH] I-03 — Active and disabled states undefined — OPEN
**Where:** All interactive elements.
**Problem:** `interaction-design.md:3–18` — "Every interactive element needs eight states." Only hover+focus+expanded are defined. No `:active` (pressed) feedback.
**Fix:** Add `.event-header:active { background: color-mix(in oklch, var(--accent-soft) 80%, var(--ink)); }` or similar slight darken, and `.pick-title a:active { color: var(--accent); }`.

### [HIGH] I-04 — No error recovery affordance — OPEN
**Where:** `script.js:62–66` sets `errorEl.textContent = "Error: " + err.message;`.
**Problem:** `ux-writing.md:20–32` + interaction design — error has no retry button, no guidance, and exposes raw "HTTP 404" or stack messages.
**Fix:** Render a "Try again" button that re-runs the fetch, and humanize the message (see U-01).

### [MEDIUM] I-05 — No loading skeleton — OPEN
**Where:** `#loading` text "Loading events…"
**Problem:** `interaction-design.md:48–49` — "Skeleton screens > spinners — they preview content shape and feel faster." Data file is small; loading is brief; still, for slow networks a skeleton row matching pick-item shape signals "work is happening."
**Fix:** Replace the text status with 3–5 placeholder list rows using CSS gradient shimmer; remove on first render.

### [MEDIUM] I-06 — Expanded panel content not announced — OPEN
**Where:** `script.js:425–427` toggles `aria-expanded`.
**Problem:** `aria-expanded` on the header announces state, but the panel itself lacks `aria-labelledby` linking to the header's title. Screen readers can land in the panel with no context for which event it describes.
**Fix:** Generate a stable `id` on the title element and set `panel.setAttribute("aria-labelledby", titleId)`.

### [LOW] I-07 — `user-select: none` on header blocks text selection — OPEN
**Where:** `.event-header { user-select: none; }` line 137.
**Problem:** Users who want to copy an event title can't. The header is click-to-expand; preventing selection is a heavy-handed fix for accidental selection on drag-expand.
**Fix:** Remove `user-select: none;`. Test that click-and-drag still toggles cleanly; if not, confine the rule to `.expand-indicator`.

---

## 5. Responsive Design

### [CRITICAL] R-01 — No `@media (pointer: coarse)` — OPEN
**Where:** Only `@media (max-width: 600px)` exists.
**Problem:** `responsive-design.md:12–37` — "Screen size doesn't tell you input method." Tablet users with fine displays but touch input get cramped targets; desktops with touchscreens same.
**Fix:** Add `@media (pointer: coarse) { .event-header { padding: 16px; } .pick-item { padding: 14px 16px; min-height: 48px; } .pick-title a { padding: 4px 0; } }` independent of viewport width.

### [CRITICAL] R-02 — No `viewport-fit=cover` + no safe-area insets — OPEN
**Where:** `index.html:5` `<meta name="viewport" content="width=device-width, initial-scale=1.0">`.
**Problem:** `responsive-design.md:40–60` — on notched iPhones in landscape the masthead and content flush to rounded edges and notch.
**Fix:** Update meta to `content="width=device-width, initial-scale=1, viewport-fit=cover"`. Add to body: `padding-left: max(1.18em, env(safe-area-inset-left)); padding-right: max(1.18em, env(safe-area-inset-right));`.

### [HIGH] R-03 — Not mobile-first — OPEN
**Where:** Base rules target desktop; `@media (max-width: 600px)` overrides them.
**Problem:** `responsive-design.md:3–6` — "Desktop-first means mobile loads unnecessary styles first."
**Fix:** Refactor to mobile base + `@media (min-width: 640px)` progressive enhancement. Flag as large scope; may be deferred.

### [HIGH] R-04 — `@media (hover: hover)` guard missing on hover styles — OPEN
**Where:** `.event-header:hover`, `.pick-title a:hover`, `.event-title-link:hover`.
**Problem:** `responsive-design.md:27–37` — on touch devices, `:hover` styles "stick" after tap and visually confuse users. The terracotta border-bottom on titles persists after a tap until another tap clears it.
**Fix:** Wrap hover rules in `@media (hover: hover) { ... }`.

### [MEDIUM] R-05 — Single 600 px breakpoint — OPEN
**Where:** Only one media query.
**Problem:** `responsive-design.md:8–10` — typical is three breakpoints (640/768/1024). Between 601 and 880 px the layout is identical to a 1440 px display but cramped.
**Fix:** Add a mid breakpoint at 768 px tuning `--max` and padding.

### [LOW] R-06 — No `print` stylesheet — OPEN
**Where:** No `@media print` block.
**Problem:** Editorial tipsheet is the kind of page users might print/save as PDF. Expanded panels, hover states, and the black masthead rule print poorly.
**Fix:** Add a print stylesheet that auto-expands all panels, removes hover-only decoration, and uses a serif-only black-ink palette.

---

## 6. Motion Design

### [CRITICAL] M-01 — `max-height` animation instead of `grid-template-rows 0fr → 1fr` — OPEN
**Where:** `styles.css:215–225`
```css
.event-panel { max-height: 0; transition: max-height 0.3s ease, padding 0.3s ease; }
.event-card.is-expanded .event-panel { max-height: 2000px; padding: 8px 16px 18px 70px; }
```
**Problem:** `motion-design.md:42–44` — "**transform** and **opacity** only — everything else causes layout recalculation. For height animations (accordions), use `grid-template-rows: 0fr → 1fr` instead of animating `height` directly." The 2000 px cap also produces a visible "delay" on short panels (animation runs the full 2000 px distance, so 100 px of content takes 15 ms to appear but the easing is scaled to 2000 px). Reference `transition: ... ease` (line 218) violates "Don't use `ease`."
**Fix:**
```css
.event-panel {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows 300ms cubic-bezier(0.25, 1, 0.5, 1);
}
.event-panel > * { overflow: hidden; }
.event-card.is-expanded .event-panel { grid-template-rows: 1fr; }
```
Animation distance adapts to actual content height; easing uses the ease-out-quart recommended default.

### [HIGH] M-02 — Transition easing uses plain `ease` — OPEN
**Where:** `.event-panel` line 218 and `.expand-indicator` line 184.
**Problem:** `motion-design.md:16–40` — "Don't use `ease`. It's a compromise that's rarely optimal." Arrow rotation is an entrance-style micro-interaction (element entering its rotated state) — should be ease-out exponential.
**Fix:** Define `--ease-out-quart: cubic-bezier(0.25, 1, 0.5, 1);` token; replace both occurrences. Shorten arrow duration from 180 ms to 150 ms (falls in the "instant feedback" band).

### [MEDIUM] M-03 — No motion tokens — OPEN
**Where:** Durations and easing are literal values.
**Problem:** `motion-design.md:95` — "Create motion tokens for consistency."
**Fix:** Add `--dur-fast: 150ms; --dur-base: 300ms; --dur-slow: 500ms; --ease-out: cubic-bezier(0.25, 1, 0.5, 1);` and rewrite transitions.

### [MEDIUM] M-04 — Reduced-motion rule does not cover all transitions — OPEN
**Where:** `styles.css:334–337` — only targets `.event-panel, .expand-indicator`.
**Problem:** `motion-design.md:50–73` — safer to use the universal reset (`*, *::before, *::after { transition-duration: 0.01ms !important; animation-duration: 0.01ms !important; }`). Any future transition added elsewhere will silently bypass reduced-motion.
**Fix:** Expand the reduced-motion block to universal.

### [LOW] M-05 — Exit animation same duration as entrance — OPEN
**Where:** Panel collapse uses same 300 ms as expand.
**Problem:** `motion-design.md:14` — "Exit animations are faster than entrances — use ~75 % of enter duration."
**Fix:** Optional; add `.event-panel { transition-duration: 225ms; } .event-card.is-expanded .event-panel { transition-duration: 300ms; }` — depends on collapse feeling too slow in practice.

---

## 7. UX Writing

### [HIGH] U-01 — Error message blames the system opaquely — OPEN
**Where:** `script.js:65` — `"Error: " + err.message` renders "Error: HTTP 404" or "Error: Failed to fetch".
**Problem:** `ux-writing.md:20–32` — "Every error message should answer: What happened? Why? How to fix?" Current message delivers none of the three.
**Fix:** Map to a humanized message: "We couldn't load this week's events. Check your connection and try again." plus a Retry button (see I-04). Keep raw technical detail inside a `<details>` for power users.

### [HIGH] U-02 — No empty state — OPEN
**Where:** `script.js` renders `picksList`/`listingsEl` with zero items when `events` is `[]` — no message.
**Problem:** `ux-writing.md:38–40` — "Empty states are opportunities. Acknowledge, explain value, provide action."
**Fix:** If `grouped.length === 0`, render: "No events in the next 14 days. [Show all events] to see everything we've indexed." The `?all=1` flag already exists.

### [MEDIUM] U-03 — Loading text is generic — OPEN
**Where:** `index.html:24` — "Loading events…".
**Problem:** `ux-writing.md:94–95` — "Be specific: 'Saving your draft…' not 'Loading…'."
**Fix:** "Fetching this week's picks…" or similar specific phrasing.

### [MEDIUM] U-04 — Heading "All Events — Sorted by Rating" mixes en-dash and em-dash conventions — OPEN
**Where:** `index.html:22` uses em-dash `—`; `script.js:150` builds heading with middle dot `·`; `script.js:153` uses em-dash again.
**Problem:** `ux-writing.md:76–87` — "Pick one term and stick with it." Punctuation consistency is the same principle.
**Fix:** Use a single separator (recommend middle dot `·`) throughout headings; reserve em-dash for parenthetical prose.

### [MEDIUM] U-05 — Link text "The Austin Culture Oracle" lacks context for screen readers — OPEN
**Where:** `script.js:376` — byline "By The Austin Culture Oracle".
**Problem:** Context-only editorial flourish; screen reader users encountering it outside the card won't know what the Oracle is.
**Fix:** Minor — add `<abbr title="The house critic">` or a footer note. Low impact.

### [MEDIUM] U-06 — Type labels use underscores — OPEN
**Where:** `script.js:263`, `script.js:315` — `ev.type.replace("_", " ")`.
**Problem:** Works for `book_club`, but `ev.type` values like `movie`, `opera`, `concert` render lowercase; a user sees "movie" mid-sentence next to a proper title. Editorial tone drops.
**Fix:** Titlecase: `.replace(/_/g, " ").replace(/\b\w/g, function(c){ return c.toUpperCase(); })`. Or map to human labels ("Film" not "Movie", "Opera", "Concert").

### [MEDIUM] U-07 — No `aria-label` on status region — OPEN
**Where:** `#loading` and `#error` lack `role="status"` / `aria-live="polite"`.
**Problem:** `ux-writing.md:56` — accessibility writing principles. Screen readers miss async load/error updates.
**Fix:** `<div class="status" id="loading" role="status" aria-live="polite">` and `<div class="status error" id="error" role="alert">`.

### [LOW] U-08 — Masthead subtitle mixes instruction with tagline — OPEN
**Where:** `index.html:14` — "Critic's picks, sorted by merit. Click any event for the hook."
**Problem:** `ux-writing.md:89–91` — "If the heading explains it, the intro is redundant." The second sentence is a how-to instruction competing with the editorial tagline.
**Fix:** Split: keep "Critic's picks, sorted by merit." as subtitle; move "Click any event for the hook" to a small aside near the first card, or drop entirely (the expand indicator is self-evident).

---

## Cross-cutting observations (not numbered)

- **Class naming inconsistency:** `.pick-rating--high` (BEM) vs `.rating-high` (flat). Pick one convention.
- **Script uses ES5 (var, function expressions):** Intentional for compatibility; fine.
- **No viewport tests documented:** No Playwright or Percy snapshots. Out of scope for this frontend-only run.
- **`how-it-works.html` at docs root:** Not audited; task scope limited to `index.html`/`styles.css`/`script.js`.

---

## Prioritized fix queue (for T3.2 / T3.3)

**Fix in T3.2 (CRITICAL + HIGH):**
I-01, I-02, R-01, R-02, M-01, T-01, T-02, C-01, C-02, S-01, S-02, I-03, I-04, R-03, R-04, U-01, U-02, M-02.

**Fix in T3.3 (MEDIUM):**
T-03, T-04, T-05, C-03, C-04, C-05, S-03, S-04, S-05, I-05, I-06, R-05, M-03, M-04, U-03, U-04, U-05, U-06, U-07.

**Defer (LOW):**
T-06, T-07, C-06, C-07, S-06, S-07, I-07, R-06, M-05, U-08.
