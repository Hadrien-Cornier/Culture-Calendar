"""Unit tests for ``scripts/build_sitemap.py``.

Covers page discovery (allowlisted top-level files, globbed subdirs,
exclusion of ``variants/`` and ``og/``), URL canonicalisation for the
index, XML round-tripping, ``lastmod`` emission, and the
``robots.txt`` body.
"""
from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_sitemap.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("build_sitemap", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["build_sitemap"] = mod
    spec.loader.exec_module(mod)
    return mod


bsm = _load_module()


@pytest.fixture
def fake_docs(tmp_path: Path) -> Path:
    """Create a synthetic docs/ tree with every eligible + excluded form."""
    root = tmp_path / "docs"
    root.mkdir()

    (root / "index.html").write_text("<!doctype html><title>home</title>")
    (root / "how-it-works.html").write_text("<!doctype html><title>hiw</title>")
    (root / "ABOUT.md").write_text("# about")
    (root / "data.json").write_text("[]")
    (root / "feed.xml").write_text("<rss/>")
    (root / "calendar.ics").write_text("BEGIN:VCALENDAR\nEND:VCALENDAR\n")

    (root / "weekly").mkdir()
    (root / "weekly" / "2026-W17.html").write_text("<!doctype html><title>w17</title>")
    (root / "weekly" / "2026-W18.html").write_text("<!doctype html><title>w18</title>")

    (root / "venues").mkdir()
    (root / "venues" / "afs.html").write_text("<!doctype html><title>afs</title>")
    (root / "venues" / "hyperreal.html").write_text(
        "<!doctype html><title>hyperreal</title>"
    )

    (root / "people").mkdir()
    (root / "people" / "beethoven.html").write_text(
        "<!doctype html><title>beethoven</title>"
    )

    (root / "variants").mkdir()
    (root / "variants" / "v12i").mkdir()
    (root / "variants" / "v12i" / "index.html").write_text("<!doctype html>archive")

    (root / "og").mkdir()
    (root / "og" / "card.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    return root


def test_path_to_url_canonicalises_index(fake_docs: Path):
    url = bsm._path_to_url(
        fake_docs / "index.html", docs_root=fake_docs, base_url=bsm.SITE_BASE_URL
    )
    assert url == bsm.SITE_BASE_URL
    assert not url.endswith("index.html")


def test_path_to_url_preserves_nested_slug(fake_docs: Path):
    url = bsm._path_to_url(
        fake_docs / "venues" / "afs.html",
        docs_root=fake_docs,
        base_url=bsm.SITE_BASE_URL,
    )
    assert url.endswith("venues/afs.html")


def test_discover_pages_includes_expected_surfaces(fake_docs: Path):
    entries = bsm.discover_pages(fake_docs)
    urls = [e.loc for e in entries]

    assert bsm.SITE_BASE_URL in urls
    assert any(u.endswith("how-it-works.html") for u in urls)
    assert any(u.endswith("weekly/2026-W17.html") for u in urls)
    assert any(u.endswith("weekly/2026-W18.html") for u in urls)
    assert any(u.endswith("venues/afs.html") for u in urls)
    assert any(u.endswith("venues/hyperreal.html") for u in urls)
    assert any(u.endswith("people/beethoven.html") for u in urls)


def test_discover_pages_excludes_variants_and_og(fake_docs: Path):
    entries = bsm.discover_pages(fake_docs)
    urls = [e.loc for e in entries]
    assert not any("variants/" in u for u in urls)
    assert not any("og/" in u for u in urls)
    assert not any(u.endswith(".json") for u in urls)
    assert not any(u.endswith(".md") for u in urls)
    assert not any(u.endswith(".xml") for u in urls)
    assert not any(u.endswith(".ics") for u in urls)


def test_discover_pages_skips_missing_top_level(tmp_path: Path):
    """Missing wishlist.html (or any allowlisted page) is silently skipped."""
    root = tmp_path / "docs"
    root.mkdir()
    (root / "index.html").write_text("<!doctype html>")
    entries = bsm.discover_pages(root)
    urls = [e.loc for e in entries]
    assert urls == [bsm.SITE_BASE_URL]


def test_discover_pages_handles_missing_features_dir(fake_docs: Path):
    """features/ subdir absent — glob must return [] without crashing."""
    assert not (fake_docs / "features").exists()
    entries = bsm.discover_pages(fake_docs)
    assert entries, "discover should still return other pages"


def test_discover_pages_picks_up_features_when_present(fake_docs: Path):
    (fake_docs / "features").mkdir()
    (fake_docs / "features" / "composer-2026-W17.html").write_text(
        "<!doctype html><title>feature</title>"
    )
    entries = bsm.discover_pages(fake_docs)
    urls = [e.loc for e in entries]
    assert any(u.endswith("features/composer-2026-W17.html") for u in urls)


def test_discover_pages_returns_sorted_urls(fake_docs: Path):
    entries = bsm.discover_pages(fake_docs)
    urls = [e.loc for e in entries]
    assert urls == sorted(urls)


def test_discover_pages_sets_lastmod_date(fake_docs: Path):
    entries = bsm.discover_pages(fake_docs)
    # Every entry in the fake tree has a real mtime → lastmod populated.
    assert all(e.lastmod is not None for e in entries)
    for entry in entries:
        assert isinstance(entry.lastmod, date)


def test_build_sitemap_emits_valid_xml(fake_docs: Path, tmp_path: Path):
    entries = bsm.discover_pages(fake_docs)
    out = tmp_path / "sitemap.xml"
    count = bsm.write_sitemap(entries, out_path=out)
    assert count == len(entries)

    tree = ET.parse(out)
    root = tree.getroot()
    assert root.tag == f"{{{bsm.SITEMAP_NS}}}urlset"
    url_elements = root.findall(f"{{{bsm.SITEMAP_NS}}}url")
    assert len(url_elements) == count

    first_loc = url_elements[0].find(f"{{{bsm.SITEMAP_NS}}}loc")
    assert first_loc is not None and first_loc.text
    assert first_loc.text.startswith("https://hadrien-cornier.github.io/Culture-Calendar/")


def test_build_sitemap_includes_lastmod_when_present(tmp_path: Path):
    entries = [
        bsm.SitemapEntry(
            loc="https://hadrien-cornier.github.io/Culture-Calendar/",
            lastmod=date(2026, 4, 20),
        )
    ]
    out = tmp_path / "sitemap.xml"
    bsm.write_sitemap(entries, out_path=out)
    root = ET.parse(out).getroot()
    lastmod = root.find(
        f"{{{bsm.SITEMAP_NS}}}url/{{{bsm.SITEMAP_NS}}}lastmod"
    )
    assert lastmod is not None
    assert lastmod.text == "2026-04-20"


def test_build_sitemap_omits_lastmod_when_none(tmp_path: Path):
    entries = [
        bsm.SitemapEntry(
            loc="https://hadrien-cornier.github.io/Culture-Calendar/", lastmod=None
        )
    ]
    out = tmp_path / "sitemap.xml"
    bsm.write_sitemap(entries, out_path=out)
    root = ET.parse(out).getroot()
    assert root.find(f"{{{bsm.SITEMAP_NS}}}url/{{{bsm.SITEMAP_NS}}}lastmod") is None


def test_render_robots_references_sitemap():
    body = bsm.render_robots()
    assert "User-agent: *" in body
    assert "Allow: /" in body
    assert "Sitemap: https://hadrien-cornier.github.io/Culture-Calendar/sitemap.xml" in body


def test_write_robots_creates_file(tmp_path: Path):
    out = tmp_path / "robots.txt"
    bsm.write_robots(out_path=out)
    content = out.read_text()
    assert content.startswith("User-agent:")
    assert "Sitemap:" in content


def test_main_writes_sitemap_and_robots(fake_docs: Path, tmp_path: Path):
    sitemap_out = tmp_path / "sitemap.xml"
    robots_out = tmp_path / "robots.txt"
    exit_code = bsm.main(
        [
            "--docs",
            str(fake_docs),
            "--out",
            str(sitemap_out),
            "--robots",
            str(robots_out),
            "--quiet",
        ]
    )
    assert exit_code == 0
    assert sitemap_out.exists()
    assert robots_out.exists()
    root = ET.parse(sitemap_out).getroot()
    url_elements = root.findall(f"{{{bsm.SITEMAP_NS}}}url")
    assert len(url_elements) > 0
