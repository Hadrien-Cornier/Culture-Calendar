"""Build the venue-wishlist dashboard page at ``docs/wishlist.html``.

Aggregates candidate venues Culture Calendar does not yet scrape, so
visitors (and the maintainer) can see where the next integrations might
come from. Source of truth, in order of preference:

1. ``.overnight/venue-prospects/*.md`` — curated prospector output from
   ``scripts/prospect_venues.py``. Each markdown file contains bullet
   lines of the form ``- [ ] Name (category) — description — url``
   under ``## Prospecting run: ...`` section headers. When this
   directory is present and non-empty, it wins.
2. Otherwise, the ``## Venue Wishlist`` section of ``README.md`` between
   the ``<!-- venue-wishlist:begin -->`` and ``<!-- venue-wishlist:end -->``
   markers. Bullets there share the same shape but may omit the URL.

Duplicates are collapsed on ``(name, category)`` (case-insensitive);
within a duplicate group we keep the entry with the longer description
and prefer the first non-empty URL. Entries are grouped by category on
the rendered page.

Stdlib only. Mirrors the structure of ``scripts/build_venue_pages.py``.
"""

from __future__ import annotations

import argparse
import html
import logging
import re
import sys
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
PROSPECTS_DIR = REPO_ROOT / ".overnight" / "venue-prospects"
README_PATH = REPO_ROOT / "README.md"
OUT_PATH = REPO_ROOT / "docs" / "wishlist.html"

SITE_HOST = "hadrien-cornier.github.io"
SITE_PATH = "/Culture-Calendar/"
SITE_URL = f"https://{SITE_HOST}{SITE_PATH}"
RSS_URL = f"{SITE_URL}feed.xml"
TOP_PICKS_WEBCAL = f"webcal://{SITE_HOST}{SITE_PATH}top-picks.ics"

CATEGORY_LABELS: dict[str, str] = {
    "movie": "Film",
    "concert": "Concert",
    "opera": "Opera",
    "dance": "Dance",
    "book_club": "Books",
    "visual_arts": "Visual Arts",
    "theater": "Theater",
    "other": "Other",
}

README_BEGIN_MARKER = "<!-- venue-wishlist:begin -->"
README_END_MARKER = "<!-- venue-wishlist:end -->"

# Matches ``- [ ] Name (category) — desc`` and variants. ``desc`` may
# itself contain ``—`` separators; we split on the LAST ``—`` to peel
# off an optional trailing URL, then keep the remainder as description.
_BULLET_RE = re.compile(
    r"^\s*-\s*\[[ xX]\]\s*"
    r"(?P<name>.+?)\s*"
    r"\((?P<category>[a-zA-Z_][\w/\- ]*)\)\s*"
    r"(?:[—–-]+\s*(?P<rest>.+))?$"
)

# ``[1]``, ``[2][3]`` style source references dropped by Perplexity.
_SOURCE_REF_RE = re.compile(r"\[\d+\]")

# URL heuristic: only anchors like http(s)://...  stripped via last split.
_URL_RE = re.compile(r"https?://\S+")

LOG = logging.getLogger("build_wishlist")


@dataclass(frozen=True)
class Prospect:
    """One wishlist candidate row."""

    name: str
    category: str
    description: str
    url: str

    @property
    def key(self) -> tuple[str, str]:
        return (self.name.strip().lower(), self.category.strip().lower())


def _clean_text(text: str) -> str:
    """Strip bracketed source refs + collapse whitespace."""
    cleaned = _SOURCE_REF_RE.sub("", text or "")
    return " ".join(cleaned.split()).strip()


def _split_description_and_url(rest: str) -> tuple[str, str]:
    """Split the trailing ``— url`` segment off a bullet's rest-of-line.

    If ``rest`` ends with an embedded URL (possibly preceded by an em/en
    dash separator), pull it out as ``url`` and return the leading text
    as the description. Otherwise return ``(rest, "")``.
    """
    text = rest or ""
    urls = _URL_RE.findall(text)
    if not urls:
        return _clean_text(text), ""
    url = urls[-1].rstrip(").,;")
    idx = text.rfind(url)
    before = text[:idx]
    # Drop the trailing ``— `` / ``– ``/ ``- `` separator before the URL.
    before = re.sub(r"[\s—–-]+$", "", before)
    return _clean_text(before), url.strip()


def parse_bullet(line: str) -> Optional[Prospect]:
    """Parse a single ``- [ ] Name (cat) — desc — url`` bullet."""
    match = _BULLET_RE.match(line)
    if not match:
        return None
    name = _clean_text(match.group("name"))
    category = match.group("category").strip().lower().replace(" ", "_")
    rest = match.group("rest") or ""
    description, url = _split_description_and_url(rest)
    if not name:
        return None
    return Prospect(
        name=name, category=category, description=description, url=url
    )


def parse_prospects_markdown(text: str) -> list[Prospect]:
    """Parse all wishlist bullets from a single markdown blob."""
    out: list[Prospect] = []
    for raw_line in (text or "").splitlines():
        prospect = parse_bullet(raw_line)
        if prospect is not None:
            out.append(prospect)
    return out


def parse_readme_wishlist(text: str) -> list[Prospect]:
    """Extract wishlist bullets from the README section markers."""
    if not text:
        return []
    begin = text.find(README_BEGIN_MARKER)
    end = text.find(README_END_MARKER)
    if begin < 0 or end < 0 or end <= begin:
        return []
    slice_ = text[begin + len(README_BEGIN_MARKER) : end]
    return parse_prospects_markdown(slice_)


def load_prospects_from_dir(directory: Path) -> list[Prospect]:
    """Load + concatenate prospects from every ``*.md`` file under ``directory``."""
    if not directory.exists() or not directory.is_dir():
        return []
    all_prospects: list[Prospect] = []
    for md_path in sorted(directory.glob("*.md")):
        try:
            body = md_path.read_text(encoding="utf-8")
        except OSError as exc:
            LOG.warning("Skipping %s: %s", md_path, exc)
            continue
        all_prospects.extend(parse_prospects_markdown(body))
    return all_prospects


def dedupe_prospects(prospects: Iterable[Prospect]) -> list[Prospect]:
    """Collapse duplicates on ``(name, category)``.

    For each key we keep the entry with the longest non-empty
    description and the first non-empty URL seen, preserving insertion
    order of keys.
    """
    order: list[tuple[str, str]] = []
    by_key: dict[tuple[str, str], Prospect] = {}
    for prospect in prospects:
        key = prospect.key
        if key not in by_key:
            by_key[key] = prospect
            order.append(key)
            continue
        current = by_key[key]
        new_description = current.description
        if len(prospect.description) > len(current.description):
            new_description = prospect.description
        new_url = current.url or prospect.url
        by_key[key] = replace(
            current, description=new_description, url=new_url
        )
    return [by_key[k] for k in order]


def gather_prospects(
    prospects_dir: Path = PROSPECTS_DIR,
    readme_path: Path = README_PATH,
) -> tuple[list[Prospect], str]:
    """Return deduped prospects + the source label used to build them."""
    dir_prospects = load_prospects_from_dir(prospects_dir)
    if dir_prospects:
        return dedupe_prospects(dir_prospects), "prospects-dir"
    if readme_path.exists():
        body = readme_path.read_text(encoding="utf-8")
        readme_prospects = parse_readme_wishlist(body)
        return dedupe_prospects(readme_prospects), "readme"
    return [], "empty"


def group_by_category(prospects: Sequence[Prospect]) -> list[tuple[str, list[Prospect]]]:
    """Group prospects by category, sorted by (label, name)."""
    buckets: dict[str, list[Prospect]] = {}
    for prospect in prospects:
        buckets.setdefault(prospect.category, []).append(prospect)
    for bucket in buckets.values():
        bucket.sort(key=lambda p: p.name.lower())
    ordered_keys = sorted(
        buckets.keys(),
        key=lambda c: (CATEGORY_LABELS.get(c, c).lower(), c),
    )
    return [(c, buckets[c]) for c in ordered_keys]


def _category_label(category: str) -> str:
    if category in CATEGORY_LABELS:
        return CATEGORY_LABELS[category]
    return category.replace("_", " ").title()


def _esc(value: str) -> str:
    return html.escape(value or "", quote=True)


def _render_prospect(prospect: Prospect) -> str:
    if prospect.url:
        name_html = (
            f'<a class="wishlist-name-link" href="{_esc(prospect.url)}" '
            f'rel="noopener" target="_blank">{_esc(prospect.name)}</a>'
        )
        hostname_match = re.match(r"^https?://([^/]+)", prospect.url)
        hostname = hostname_match.group(1) if hostname_match else prospect.url
        meta_html = (
            f'<p class="wishlist-meta">'
            f'<span class="wishlist-host">{_esc(hostname)}</span>'
            f"</p>"
        )
    else:
        name_html = _esc(prospect.name)
        meta_html = '<p class="wishlist-meta">No source URL on file</p>'
    description_html = ""
    if prospect.description:
        description_html = (
            f'<p class="wishlist-description">{_esc(prospect.description)}</p>'
        )
    return (
        '<li class="wishlist-item">'
        '<article class="wishlist-article">'
        f'<h3 class="wishlist-name">{name_html}</h3>'
        f"{description_html}"
        f"{meta_html}"
        "</article>"
        "</li>"
    )


def _render_group(category: str, prospects: Sequence[Prospect]) -> str:
    items_html = "\n".join(_render_prospect(p) for p in prospects)
    label = _category_label(category)
    count = len(prospects)
    count_noun = "candidate" if count == 1 else "candidates"
    return (
        '<section class="wishlist-group">'
        f'<header class="wishlist-group-header">'
        f'<h2 class="wishlist-group-title">{_esc(label)}</h2>'
        f'<p class="wishlist-group-meta">{count} {count_noun}</p>'
        "</header>"
        f'<ol class="wishlist-items">{items_html}</ol>'
        "</section>"
    )


def render_page(
    prospects: Sequence[Prospect],
    *,
    source: str,
    generated_at: Optional[datetime] = None,
) -> str:
    """Render the full HTML page body."""
    generated_at = generated_at or datetime.now(tz=timezone.utc)
    stamp = generated_at.strftime("%Y-%m-%d %H:%M UTC")
    total = len(prospects)
    groups = group_by_category(prospects)
    source_blurb = {
        "prospects-dir": (
            "Sourced from <code>.overnight/venue-prospects/</code> — "
            "Perplexity-discovered candidates from recent prospecting runs."
        ),
        "readme": (
            "Sourced from the <code>README.md</code> Venue Wishlist section — "
            "roadmap candidates maintained by hand."
        ),
        "empty": (
            "No wishlist sources were available when this page was built."
        ),
    }.get(source, "Sourced from the repository wishlist.")

    if groups:
        body_html = "\n".join(_render_group(c, p) for c, p in groups)
    else:
        body_html = (
            '<p class="wishlist-empty">'
            "No venue candidates yet. Run "
            "<code>scripts/prospect_venues.py</code> or add entries under the "
            "README <em>Venue Wishlist</em> section."
            "</p>"
        )

    description_meta = (
        f"Culture Calendar's wishlist of Austin cultural venues we don't yet "
        f"scrape. {total} candidate{'s' if total != 1 else ''} across "
        f"{len(groups)} categor{'ies' if len(groups) != 1 else 'y'}."
    )

    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>Venue Wishlist — Culture Calendar</title>\n"
        f'<meta name="description" content="{_esc(description_meta)}">\n'
        '<link rel="stylesheet" href="styles.css">\n'
        '<link rel="alternate" type="application/rss+xml" title="Culture Calendar" '
        f'href="{_esc(RSS_URL)}">\n'
        "<style>\n"
        ".wishlist-page { max-width: 880px; margin: 0 auto; padding: 2rem 1.25rem 4rem; "
        "font-family: 'Libre Franklin', system-ui, sans-serif; color: #1f1f1f; }\n"
        ".wishlist-masthead { border-bottom: 1px solid #d4a574; padding-bottom: 1.25rem; "
        "margin-bottom: 2rem; }\n"
        ".wishlist-eyebrow { font-size: 0.75rem; letter-spacing: 0.08em; text-transform: uppercase; "
        "color: #8a6f4a; margin: 0; }\n"
        ".wishlist-page h1 { font-family: 'et-book', Georgia, serif; font-size: 2.25rem; "
        "margin: 0.25rem 0 0.75rem; }\n"
        ".wishlist-lead { font-size: 1rem; line-height: 1.55; color: #3a3a3a; margin: 0 0 0.75rem; }\n"
        ".wishlist-stamp { font-size: 0.8rem; color: #6b6b6b; margin: 0; }\n"
        ".wishlist-actions { margin-top: 1rem; display: flex; gap: 1rem; flex-wrap: wrap; "
        "font-size: 0.9rem; }\n"
        ".wishlist-actions a { color: #8a3b2a; text-decoration: none; border-bottom: 1px solid #d4a574; }\n"
        ".wishlist-group { margin-top: 2rem; }\n"
        ".wishlist-group-header { display: flex; align-items: baseline; justify-content: space-between; "
        "gap: 1rem; border-bottom: 1px solid #e6d7bf; padding-bottom: 0.4rem; margin-bottom: 0.85rem; }\n"
        ".wishlist-group-title { font-family: 'et-book', Georgia, serif; font-size: 1.4rem; margin: 0; }\n"
        ".wishlist-group-meta { font-size: 0.8rem; color: #6b6b6b; margin: 0; }\n"
        ".wishlist-items { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.85rem; }\n"
        ".wishlist-item { border-left: 2px solid #d4a574; padding: 0.4rem 0 0.4rem 0.85rem; }\n"
        ".wishlist-name { margin: 0; font-size: 1.05rem; font-weight: 500; }\n"
        ".wishlist-name-link { color: #1f1f1f; text-decoration: none; border-bottom: 1px solid #d4a574; }\n"
        ".wishlist-description { margin: 0.2rem 0 0.25rem; font-size: 0.9rem; line-height: 1.45; "
        "color: #3a3a3a; }\n"
        ".wishlist-meta { margin: 0; font-size: 0.75rem; color: #6b6b6b; }\n"
        ".wishlist-host { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }\n"
        ".wishlist-empty { padding: 1.5rem; border: 1px dashed #d4a574; text-align: center; "
        "color: #6b6b6b; }\n"
        "</style>\n"
        "</head>\n"
        '<body class="wishlist-page">\n'
        '<header class="wishlist-masthead">\n'
        '<p class="wishlist-eyebrow">Culture Calendar · Venue Wishlist</p>\n'
        "<h1>Austin venues we don&rsquo;t yet scrape</h1>\n"
        f'<p class="wishlist-lead">{source_blurb}</p>\n'
        f'<p class="wishlist-stamp">{total} candidate{"s" if total != 1 else ""} · '
        f"generated {_esc(stamp)}</p>\n"
        '<nav class="wishlist-actions" aria-label="Wishlist actions">\n'
        '<a href="./">&larr; Back to Calendar</a>\n'
        f'<a href="{_esc(RSS_URL)}">RSS</a>\n'
        f'<a href="{_esc(TOP_PICKS_WEBCAL)}">Top Picks (webcal)</a>\n'
        "</nav>\n"
        "</header>\n"
        '<main class="wishlist-main">\n'
        f"{body_html}\n"
        "</main>\n"
        '<footer class="wishlist-footer">\n'
        '<p><a href="./">Culture Calendar</a> &middot; AI-curated Austin cultural events</p>\n'
        "</footer>\n"
        "</body>\n"
        "</html>\n"
    )


def write_page(
    prospects: Sequence[Prospect],
    *,
    source: str,
    out_path: Path = OUT_PATH,
    generated_at: Optional[datetime] = None,
) -> Path:
    """Render and persist the wishlist HTML. Returns the output path."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rendered = render_page(
        prospects, source=source, generated_at=generated_at
    )
    out_path.write_text(rendered, encoding="utf-8")
    return out_path


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--prospects-dir",
        type=Path,
        default=PROSPECTS_DIR,
        help="Directory of prospect markdown files (default: %(default)s).",
    )
    parser.add_argument(
        "--readme",
        type=Path,
        default=README_PATH,
        help="Fallback README path (default: %(default)s).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=OUT_PATH,
        help="Output HTML file (default: %(default)s).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress stdout summary.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    prospects, source = gather_prospects(
        prospects_dir=args.prospects_dir, readme_path=args.readme
    )
    out_path = write_page(prospects, source=source, out_path=args.out)
    if not args.quiet:
        print(
            f"Wrote {out_path} ({len(prospects)} prospects, source={source})"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
