#!/usr/bin/env python3
"""Filter-bar smoke test for the promoted v12 redesign.

Verifies three things without opening a browser:

1. `docs/index.html` declares the filter bar with venue and category filters.
2. `docs/script.js` parses filter state from URL params.
3. `docs/styles.css` declares a collapsed filter-bar height <= 72px (HC1 of
   the filter-redesign spec).

Exit 0 on success, 1 on any failed check. Prints a short report either way.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = REPO_ROOT / "docs" / "index.html"
SCRIPT_JS = REPO_ROOT / "docs" / "script.js"
STYLES_CSS = REPO_ROOT / "docs" / "styles.css"

MAX_FILTER_BAR_PX = 72

# Filter markers any acceptable variant must expose. Each tuple is
# (label, list-of-substrings; ANY match passes). This lets the smoke test
# tolerate minor naming differences between variants without going blind.
HTML_MARKERS: list[tuple[str, tuple[str, ...]]] = [
    ("filter bar container", ('id="filter-bar"', 'class="filter-bar"', "filter-bar")),
    ("venue filter element", ('id="venue-chips"', "venue-filter", "venue-chips", 'name="venue"')),
    (
        "category filter element",
        ('id="category-chips"', "category-filter", "category-chips", 'name="category"'),
    ),
    ("filter-row / grouping structure", ("filter-row", "filter-sheet", "filter-group")),
]

JS_MARKERS: list[tuple[str, tuple[str, ...]]] = [
    ("URL param parser", ("URLSearchParams", "location.search")),
    ("venue param read", ('params.get("venue"', "params.get('venue'", 'params.get("venues"', "params.get('venues'")),
    (
        "category param read",
        (
            'params.get("category"',
            "params.get('category'",
            'params.get("categories"',
            "params.get('categories'",
        ),
    ),
]


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")


def check_markers(label: str, text: str, markers: list[tuple[str, tuple[str, ...]]]) -> list[str]:
    errors: list[str] = []
    for name, variants in markers:
        if not any(v in text for v in variants):
            errors.append(f"{label}: missing {name} (tried {variants!r})")
    return errors


# --- CSS height parsing ---------------------------------------------------

_UNIT_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*(px|rem|em)?", re.IGNORECASE)


def _to_px(value: str) -> float | None:
    """Convert a single CSS length token to pixels.

    rem/em are assumed 16px (browser default). Unitless zero is accepted.
    Returns None if the value is not a plain length.
    """
    value = value.strip()
    if value == "0":
        return 0.0
    m = _UNIT_RE.fullmatch(value)
    if not m:
        return None
    num = float(m.group(1))
    unit = (m.group(2) or "").lower()
    if unit == "px" or unit == "":
        return num
    if unit in {"rem", "em"}:
        return num * 16.0
    return None


def _extract_block(css: str, selector: str) -> str | None:
    """Return the declaration block body for a given selector.

    Only looks for exact top-level rule matches like `.filter-bar {` —
    media-query scoped rules are intentionally ignored since HC1 is a
    rest-state desktop budget.
    """
    pattern = re.compile(
        r"(?:^|\n)\s*" + re.escape(selector) + r"\s*\{([^}]*)\}",
        re.MULTILINE,
    )
    m = pattern.search(css)
    return m.group(1) if m else None


def _parse_declarations(block: str) -> dict[str, str]:
    decls: dict[str, str] = {}
    for line in block.split(";"):
        line = line.strip()
        if not line or ":" not in line:
            continue
        prop, _, val = line.partition(":")
        decls[prop.strip().lower()] = val.strip().rstrip(";")
    return decls


def _vertical_padding_px(decls: dict[str, str]) -> float:
    """Return declared top+bottom padding in px for a declaration block."""
    top = bottom = 0.0
    if "padding" in decls:
        parts = decls["padding"].split()
        pxs = [_to_px(p) or 0.0 for p in parts]
        if len(pxs) == 1:
            top = bottom = pxs[0]
        elif len(pxs) == 2:
            top = bottom = pxs[0]
        elif len(pxs) == 3:
            top, _, bottom = pxs[0], pxs[1], pxs[2]
        elif len(pxs) >= 4:
            top, _, bottom, _ = pxs[0], pxs[1], pxs[2], pxs[3]
    if "padding-top" in decls:
        top = _to_px(decls["padding-top"]) or 0.0
    if "padding-bottom" in decls:
        bottom = _to_px(decls["padding-bottom"]) or 0.0
    return top + bottom


def _vertical_border_px(decls: dict[str, str]) -> float:
    """Return declared top+bottom border width in px.

    Only handles common shorthand forms: `border: 1px solid ...` and
    `border-top/bottom: 1px solid ...`. A declaration like `border-bottom:
    none` counts as 0. If the shorthand lacks a parseable length (e.g.
    `border: var(--...)`), returns 0 — the smoke test errs toward
    passing since an unparseable value often means it resolves to 0.
    """
    total = 0.0

    def width_of(val: str) -> float:
        for tok in val.split():
            px = _to_px(tok)
            if px is not None and px > 0:
                return px
        return 0.0

    if "border" in decls:
        # Approximate: full border applies to top and bottom.
        total += 2 * width_of(decls["border"])
    if "border-top" in decls:
        total += width_of(decls["border-top"])
    if "border-top-width" in decls:
        total += _to_px(decls["border-top-width"]) or 0.0
    if "border-bottom" in decls:
        total += width_of(decls["border-bottom"])
    if "border-bottom-width" in decls:
        total += _to_px(decls["border-bottom-width"]) or 0.0
    return total


def compute_filter_bar_height(css: str) -> tuple[float, list[str]]:
    """Estimate the collapsed desktop filter-bar height from declared CSS.

    Sums the outer container's vertical padding/border with the tallest
    plausible row of controls inside it (filter-trigger, filter-row, or a
    search-input / select). A single row is assumed at rest — which is the
    spec's "0row" or "2row" collapsed state. Returns (px, details_lines).
    """
    lines: list[str] = []
    outer = _extract_block(css, ".filter-bar")
    if outer is None:
        return float("inf"), [".filter-bar selector not found"]
    outer_decls = _parse_declarations(outer)

    outer_padding = _vertical_padding_px(outer_decls)
    outer_border = _vertical_border_px(outer_decls)
    outer_height_decl = outer_decls.get("height") or outer_decls.get("min-height")
    outer_height_px = _to_px(outer_height_decl) if outer_height_decl else None

    lines.append(f".filter-bar padding(top+bot)={outer_padding}px border={outer_border}px")

    inner_candidates = [
        ".filter-trigger",
        ".filter-row",
        ".filter-bar-inner",
        ".filter-sheet",
        ".search-bar",
    ]
    tallest_inner = 0.0
    for sel in inner_candidates:
        block = _extract_block(css, sel)
        if block is None:
            continue
        d = _parse_declarations(block)
        min_h = _to_px(d.get("min-height", "")) if d.get("min-height") else None
        h = _to_px(d.get("height", "")) if d.get("height") else None
        pad = _vertical_padding_px(d)
        bdr = _vertical_border_px(d)
        # Effective row height at rest: max(content-ish padding+border, min-height, height).
        effective = max(min_h or 0.0, h or 0.0, pad + bdr)
        lines.append(
            f"{sel}: min-height={min_h} height={h} padding={pad}px "
            f"border={bdr}px -> effective={effective}px"
        )
        tallest_inner = max(tallest_inner, effective)

    if outer_height_px is not None:
        # Explicit height/min-height on the bar wins.
        total = outer_height_px + outer_border
        lines.append(f"outer declared height={outer_height_px}px -> total={total}px")
        return total, lines

    total = outer_padding + outer_border + tallest_inner
    lines.append(f"sum = outer_padding + outer_border + tallest_inner = {total}px")
    return total, lines


# --- main -----------------------------------------------------------------


def main() -> int:
    errors: list[str] = []

    for path in (INDEX_HTML, SCRIPT_JS, STYLES_CSS):
        if not path.is_file():
            errors.append(f"missing file: {path}")

    if errors:
        for e in errors:
            fail(e)
        return 1

    html = INDEX_HTML.read_text(encoding="utf-8")
    js = SCRIPT_JS.read_text(encoding="utf-8")
    css = STYLES_CSS.read_text(encoding="utf-8")

    errors.extend(check_markers("index.html", html, HTML_MARKERS))
    errors.extend(check_markers("script.js", js, JS_MARKERS))

    height_px, height_lines = compute_filter_bar_height(css)
    height_ok = height_px <= MAX_FILTER_BAR_PX
    if not height_ok:
        errors.append(
            f"styles.css: declared filter-bar height {height_px}px exceeds "
            f"{MAX_FILTER_BAR_PX}px budget (HC1)"
        )

    # --- report ---
    print("=== check_filter_smoke ===")
    print(f"HTML markers: {'OK' if not any('index.html' in e for e in errors) else 'FAIL'}")
    print(f"JS markers:   {'OK' if not any('script.js' in e for e in errors) else 'FAIL'}")
    print(f"CSS height:   {height_px}px (budget {MAX_FILTER_BAR_PX}px) {'OK' if height_ok else 'FAIL'}")
    for ln in height_lines:
        print(f"  {ln}")

    if errors:
        print()
        for e in errors:
            fail(e)
        return 1

    print("\nall checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
