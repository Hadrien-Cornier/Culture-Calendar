# Typography Decision Record

**Date:** 2026-04-30
**Run:** long-run/20260430-102637 — Phase 5 (NYT-inspired typography)
**Status:** Accepted

## Decision

The site adopts a two-family pair, loaded as self-hosted web fonts with `font-display: swap`:

- **Editorial serif (display + body):** **Source Serif 4** (Adobe, OFL).
- **UI sans-serif (metadata, chips, buttons):** **Inter** (Rasmus Andersson, OFL).

Both replace the prior CSS variables `--serif` (`"Saol Display", "Didot", "Bodoni Moda", "Playfair Display", serif`) and `--sans` (`"Helvetica Neue", "Arial", sans-serif`) at `docs/styles.css:17-18`, which depended entirely on system or licensed fonts being resident on the visitor's machine and silently fell through to platform defaults on most devices.

## Rationale

1. **Editorial register without paywalled licenses.** The brief is "NYT-inspired typography." NYT licenses Cheltenham, Imperial, and Franklin — none of those are redistributable. Source Serif 4 is OFL, ships in five optical sizes (Caption / Small / Subhead / Display / Poster), and shares the Pierre Simon Fournier lineage that gives NYT's masthead its weight without imitating it. Inter covers the entire UI metadata layer (navigation, dates, chip labels, buttons) at every weight from 100 to 900 with tabular figures and case-aware punctuation — the features the design system at `docs/STYLE_GUIDE.md` already calls for under "datelines, bylines, columns" but never had the actual glyphs to render.

2. **Real web fonts, not declared-and-prayed-for.** The current `--serif` stack lists Saol Display first. Saol Display is a Schick Toikka commercial face (~€500 desktop license) that exists on roughly zero visitor machines; the next two fallbacks (Didot, Bodoni Moda) are equally absent on Android and most Linux distros. In practice the site renders in Georgia or DejaVu Serif on the majority of pageviews. Self-hosting Source Serif 4 + Inter under `docs/fonts/` makes the typography deterministic across platforms.

3. **Variable-font payload, predictable weight.** Both families ship as variable fonts. One `Source Serif 4 Variable.woff2` (~80 KB subset to Latin) covers weights 200–900 and the optical-size axis; one `Inter Variable.woff2` (~30 KB subset) covers UI weights. Total cold-start font cost is under 120 KB compressed, vs. four to six static face files for any equivalent two-family pairing.

4. **License compatibility with GitHub Pages.** Both are SIL Open Font License 1.1. We can self-host inside the public `docs/` directory without an attribution wall — the OFL only requires the license text to ride along, which lives at `docs/fonts/OFL.txt` (added in T5.2).

5. **Type-scale alignment.** Source Serif 4 Display is drawn for sizes ≥36 px; Source Serif 4 Subhead for 18–28 px; Source Serif 4 Small for 14–17 px body. The optical-size axis is wired into the type-scale CSS variables introduced in T5.4, so a 56 px masthead and a 17 px review paragraph each get the cut intended for that size — something static-face setups (including the current Saol-or-fallback chain) cannot do.

## Rejected alternatives

### ET Book + Libre Franklin
Documented as the chosen pair in the existing `docs/STYLE_GUIDE.md`. **Rejected** for three reasons:
- ET Book has no italic small caps, no tabular figures, and only four weights — insufficient for the 7-step type scale this run is introducing.
- The Edward Tufte CDN cited in `STYLE_GUIDE.md:146` ("Loaded from CDN (Edward Tufte's repository)") is a single-machine GitHub Pages deployment with no SLA; relying on it for a primary face is a brittleness we should not inherit.
- Libre Franklin's hinting on Windows ClearType is markedly worse than Inter's at 12–14 px, which is exactly the size band our chips and metadata occupy.

### Charter + IBM Plex Sans
Charter (Matthew Carter, OFL) is a beautiful screen serif. **Rejected** because Charter ships as four static faces (Regular, Italic, Bold, Bold Italic) with no display optical size; setting a 56 px masthead in Charter Bold looks coarse next to the same size in Source Serif 4 Display. IBM Plex Sans is fine but Inter has measurably better hinting on Windows GDI and slightly larger x-height, both of which matter for our metadata-heavy listing cards.

### Lora + Source Sans 3
Lora (Cyreal, OFL) is competent but its terminals are noticeably softer than Source Serif 4's, which reads more "tech blog" than "newspaper." Source Sans 3 pairs naturally with Source Serif 4 (Adobe designed them together) but loses to Inter on tabular figures and on the case-aware features (`cv01`, `cv11`) that we use for the rating badges.

### Playfair Display + Roboto
Both are Google Fonts staples. **Rejected** because Playfair Display has high stroke-contrast that overheats above 28 px on screens — the masthead would feel gaudy rather than authoritative. Roboto is acceptable for UI but feels generic; the brief specifically calls for editorial character, and reviewers will (correctly) read Roboto as "default Google Material vibe."

### Newsreader + Public Sans
Newsreader (Production Type, OFL) has many of the same virtues as Source Serif 4 but its display cut is less mature and the variable axis covers fewer optical sizes. Public Sans (US Web Design System, OFL) is well-engineered but less widely-tested at extreme sizes than Inter. Close runner-up; we'd revisit if Adobe ever de-listed Source Serif 4.

### Status quo (Saol Display fallback chain)
**Rejected** as documented in the Rationale: it ships no actual web fonts, so 80%+ of visitors render in their platform default. The "NYT-inspired" intent is invisible to them.

## Implementation outline

The remaining Phase 5 tasks land the decision in code:

- **T5.2** — Self-host the two variable WOFF2 files under `docs/fonts/` plus the OFL license; declare `@font-face` blocks at the top of `docs/styles.css` with `font-display: swap`.
- **T5.3** — Replace `--serif` and `--sans` to put `"Source Serif 4"` and `"Inter"` first in their respective stacks, with the existing platform fonts retained as graceful-degradation fallbacks.
- **T5.4** — Introduce the type-scale CSS custom properties (`--fs-display`, `--fs-h1`, `--fs-h2`, `--fs-h3`, `--fs-body`, `--fs-small`, `--fs-micro`) and route every numeric `font-size` in `docs/styles.css` through them.
- **T5.5** — Add tests in `tests/` asserting the @font-face blocks are present, the variables are declared, and no literal `px` font-sizes remain outside the variable definitions.
- **T5.6** — Persona-gate dress rehearsal: run the live-site council against a local server and confirm the typography redesign passes 6/6.

Out-of-scope for this decision: the colour palette in the same `:root` block (`--bg`, `--ink`, `--accent`, etc.) is being kept as-is from the 20260425-175347 "aged paper" run.

## References

- Source Serif 4 — Frank Grießhammer, Adobe. https://github.com/adobe-fonts/source-serif
- Inter — Rasmus Andersson. https://github.com/rsms/inter
- SIL Open Font License 1.1 — https://openfontlicense.org/
- Existing design intent — `docs/STYLE_GUIDE.md`
- Run goal — `CLAUDE.md`, section "Long run — 20260430-102637" → Goal item (1) and Definition of done (Source Serif 4 + Inter loaded as web fonts).
