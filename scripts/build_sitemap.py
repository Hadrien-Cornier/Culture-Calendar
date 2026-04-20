"""Build ``docs/sitemap.xml`` and ``docs/robots.txt`` for search engines.

The sitemap enumerates every user-facing HTML page under ``docs/``:
the index, ``how-it-works.html``, per-week digests under ``weekly/``,
per-venue pages under ``venues/``, per-person pages under ``people/``,
and per-feature pages under ``features/`` (when present).

The archival ``variants/`` subtree, image ``og/`` cards, markdown
docs, feed files, and calendar files are deliberately excluded — the
sitemap is an HTML-surface index, not a full asset listing.

``robots.txt`` is a three-line companion pointing crawlers at the
sitemap and allowing the whole site.

Stdlib only — uses ``xml.etree.ElementTree``.
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable, Optional, Sequence
from xml.etree import ElementTree as ET

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
OUT_SITEMAP = DOCS_DIR / "sitemap.xml"
OUT_ROBOTS = DOCS_DIR / "robots.txt"

SITE_BASE_URL = "https://hadrien-cornier.github.io/Culture-Calendar/"
SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"

# Top-level HTML files at ``docs/`` that should appear in the sitemap.
# Kept as an allowlist — variants/, og/, and other assets are implicitly
# excluded, and new surfaces must be opted in here explicitly so the
# sitemap never accidentally advertises a half-built page.
TOP_LEVEL_PAGES: tuple[str, ...] = (
    "index.html",
    "how-it-works.html",
    "wishlist.html",
)

# Subdirectories of ``docs/`` whose ``*.html`` files are sitemap-eligible.
# ``features/`` is included preemptively; the glob is permissive and
# silently yields nothing if the directory does not exist yet.
INDEXED_SUBDIRS: tuple[str, ...] = (
    "weekly",
    "venues",
    "people",
    "features",
)

LOG = logging.getLogger("build_sitemap")


@dataclass(frozen=True)
class SitemapEntry:
    """One entry in the sitemap: absolute URL plus optional lastmod."""

    loc: str
    lastmod: Optional[date] = None


def _path_to_url(path: Path, *, docs_root: Path, base_url: str = SITE_BASE_URL) -> str:
    """Return the absolute URL for ``path`` relative to ``docs_root``.

    The index page canonicalises to the directory URL (trailing slash,
    no ``index.html``) so crawlers treat it as the site root.
    """
    rel = path.relative_to(docs_root).as_posix()
    base = base_url if base_url.endswith("/") else base_url + "/"
    if rel == "index.html":
        return base
    return base + rel


def _file_lastmod(path: Path) -> Optional[date]:
    """Return the file's mtime as a UTC date, or ``None`` on error."""
    try:
        ts = path.stat().st_mtime
    except OSError:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).date()


def discover_pages(
    docs_root: Path = DOCS_DIR,
    *,
    top_level: Sequence[str] = TOP_LEVEL_PAGES,
    subdirs: Sequence[str] = INDEXED_SUBDIRS,
    base_url: str = SITE_BASE_URL,
) -> list[SitemapEntry]:
    """Walk ``docs_root`` and return one entry per sitemap-eligible page.

    Results are sorted by URL for deterministic output — easier to
    diff across runs and to inspect in tests.
    """
    entries: list[SitemapEntry] = []
    seen: set[str] = set()

    for name in top_level:
        candidate = docs_root / name
        if not candidate.is_file():
            continue
        url = _path_to_url(candidate, docs_root=docs_root, base_url=base_url)
        if url in seen:
            continue
        seen.add(url)
        entries.append(SitemapEntry(loc=url, lastmod=_file_lastmod(candidate)))

    for sub in subdirs:
        directory = docs_root / sub
        if not directory.is_dir():
            continue
        for html_path in sorted(directory.glob("*.html")):
            url = _path_to_url(html_path, docs_root=docs_root, base_url=base_url)
            if url in seen:
                continue
            seen.add(url)
            entries.append(SitemapEntry(loc=url, lastmod=_file_lastmod(html_path)))

    entries.sort(key=lambda e: e.loc)
    return entries


def build_sitemap(entries: Iterable[SitemapEntry]) -> ET.ElementTree:
    """Assemble the sitemap 0.9 XML tree from ``entries``."""
    urlset = ET.Element("urlset", {"xmlns": SITEMAP_NS})
    for entry in entries:
        url_el = ET.SubElement(urlset, "url")
        ET.SubElement(url_el, "loc").text = entry.loc
        if entry.lastmod is not None:
            ET.SubElement(url_el, "lastmod").text = entry.lastmod.isoformat()
    return ET.ElementTree(urlset)


def write_sitemap(
    entries: Sequence[SitemapEntry],
    *,
    out_path: Path = OUT_SITEMAP,
) -> int:
    """Write the sitemap XML and return the entry count."""
    tree = build_sitemap(entries)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(out_path, encoding="utf-8", xml_declaration=True)
    return len(entries)


def render_robots(
    *,
    base_url: str = SITE_BASE_URL,
    sitemap_filename: str = "sitemap.xml",
) -> str:
    """Return the robots.txt body pointing crawlers at the sitemap."""
    base = base_url if base_url.endswith("/") else base_url + "/"
    sitemap_url = base + sitemap_filename
    return (
        "User-agent: *\n"
        "Allow: /\n"
        "\n"
        f"Sitemap: {sitemap_url}\n"
    )


def write_robots(
    *,
    out_path: Path = OUT_ROBOTS,
    base_url: str = SITE_BASE_URL,
    sitemap_filename: str = "sitemap.xml",
) -> None:
    """Write ``robots.txt`` alongside the sitemap."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    body = render_robots(base_url=base_url, sitemap_filename=sitemap_filename)
    out_path.write_text(body, encoding="utf-8")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--docs",
        type=Path,
        default=DOCS_DIR,
        help="Root of the published docs tree (default: %(default)s).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=OUT_SITEMAP,
        help="Output path for sitemap.xml (default: %(default)s).",
    )
    parser.add_argument(
        "--robots",
        type=Path,
        default=OUT_ROBOTS,
        help="Output path for robots.txt (default: %(default)s).",
    )
    parser.add_argument(
        "--base-url",
        default=SITE_BASE_URL,
        help="Site base URL used for absolute <loc> values.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress the summary line on stdout.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    entries = discover_pages(args.docs, base_url=args.base_url)
    count = write_sitemap(entries, out_path=args.out)
    write_robots(out_path=args.robots, base_url=args.base_url)

    if not args.quiet:
        print(f"Wrote {args.out} ({count} urls) and {args.robots}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
