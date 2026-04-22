"""Unit tests for ``scripts/build_archive.py``.

Covers filename parsing, pick-count extraction, entry ordering (newest
first), HTML rendering contracts (weekly/ hrefs, rating-agnostic count
fallback, empty-dir placeholder), and end-to-end ``write_archive``
round-tripping through a temp directory.
"""
from __future__ import annotations

import importlib.util
import sys
from datetime import date, datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_archive.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("build_archive", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["build_archive"] = mod
    spec.loader.exec_module(mod)
    return mod


ba = _load_module()


SAMPLE_HTML_WITH_META = (
    "<!DOCTYPE html>\n"
    '<html lang="en"><head><meta charset="utf-8">'
    '<title>Top Picks · Week of Apr 20, 2026 — Culture Calendar</title>'
    '<meta name="description" content="AI-curated Austin cultural events for '
    'April 20–26, 2026. 20 top picks with reviews."></head>'
    '<body class="weekly-digest"><ol class="weekly-picks">'
    '<li class="weekly-pick" id="pick-a"><article>a</article></li>'
    '<li class="weekly-pick" id="pick-b"><article>b</article></li>'
    "</ol></body></html>\n"
)

SAMPLE_HTML_NO_META = (
    "<!DOCTYPE html>\n"
    "<html><head><title>Top Picks</title></head>"
    '<body class="weekly-digest"><ol class="weekly-picks">'
    '<li class="weekly-pick"><article>a</article></li>'
    '<li class="weekly-pick"><article>b</article></li>'
    '<li class="weekly-pick"><article>c</article></li>'
    "</ol></body></html>\n"
)

SAMPLE_HTML_EMPTY_WEEK = (
    "<!DOCTYPE html>\n"
    '<html><head><meta name="description" content="No top picks scheduled.">'
    "</head><body></body></html>\n"
)


# ---------- Filename parsing ---------------------------------------------------


def test_parse_iso_week_filename_accepts_standard_format():
    assert ba.parse_iso_week_filename("2026-W17.html") == (2026, 17)


def test_parse_iso_week_filename_zero_padding():
    assert ba.parse_iso_week_filename("2026-W04.html") == (2026, 4)


def test_parse_iso_week_filename_rejects_bad_extension():
    assert ba.parse_iso_week_filename("2026-W17.txt") is None


def test_parse_iso_week_filename_rejects_missing_week_prefix():
    assert ba.parse_iso_week_filename("2026-17.html") is None


def test_parse_iso_week_filename_rejects_invalid_week():
    # ISO week 60 does not exist in any year.
    assert ba.parse_iso_week_filename("2026-W60.html") is None


# ---------- Pick-count extraction ----------------------------------------------


def test_extract_pick_count_prefers_meta_description_count():
    count, desc = ba.extract_pick_count(SAMPLE_HTML_WITH_META)
    assert count == 20
    assert "April 20–26, 2026" in desc


def test_extract_pick_count_falls_back_to_li_count():
    count, desc = ba.extract_pick_count(SAMPLE_HTML_NO_META)
    assert count == 3
    assert desc == ""


def test_extract_pick_count_handles_empty_digest():
    count, desc = ba.extract_pick_count(SAMPLE_HTML_EMPTY_WEEK)
    assert count is None
    assert desc == "No top picks scheduled."


def test_extract_pick_count_handles_empty_string():
    count, desc = ba.extract_pick_count("")
    assert count is None
    assert desc == ""


# ---------- Entry loading ------------------------------------------------------


def _seed_weekly(dir_: Path, name: str, body: str) -> None:
    dir_.mkdir(parents=True, exist_ok=True)
    (dir_ / name).write_text(body, encoding="utf-8")


def test_load_archive_entries_returns_newest_first(tmp_path):
    weekly = tmp_path / "weekly"
    _seed_weekly(weekly, "2026-W15.html", SAMPLE_HTML_NO_META)
    _seed_weekly(weekly, "2026-W17.html", SAMPLE_HTML_WITH_META)
    _seed_weekly(weekly, "2025-W52.html", SAMPLE_HTML_EMPTY_WEEK)
    entries = ba.load_archive_entries(weekly)
    assert [(e.year, e.week) for e in entries] == [
        (2026, 17),
        (2026, 15),
        (2025, 52),
    ]


def test_load_archive_entries_skips_unrecognized_files(tmp_path):
    weekly = tmp_path / "weekly"
    _seed_weekly(weekly, "2026-W17.html", SAMPLE_HTML_WITH_META)
    _seed_weekly(weekly, "draft.html", "<html></html>")
    _seed_weekly(weekly, "notes.txt", "not html")
    entries = ba.load_archive_entries(weekly)
    assert len(entries) == 1
    assert entries[0].filename == "2026-W17.html"


def test_load_archive_entries_handles_missing_directory(tmp_path):
    assert ba.load_archive_entries(tmp_path / "does-not-exist") == []


def test_load_archive_entries_computes_correct_week_range(tmp_path):
    weekly = tmp_path / "weekly"
    _seed_weekly(weekly, "2026-W17.html", SAMPLE_HTML_WITH_META)
    entries = ba.load_archive_entries(weekly)
    assert entries[0].monday == date(2026, 4, 20)
    assert entries[0].sunday == date(2026, 4, 26)
    assert entries[0].label == "2026-W17"
    assert entries[0].href == "weekly/2026-W17.html"
    assert entries[0].pick_count == 20


# ---------- Rendering contracts ------------------------------------------------


def test_render_page_links_entries_under_weekly_prefix(tmp_path):
    weekly = tmp_path / "weekly"
    _seed_weekly(weekly, "2026-W17.html", SAMPLE_HTML_WITH_META)
    entries = ba.load_archive_entries(weekly)
    html_doc = ba.render_page(entries)
    assert 'href="weekly/2026-W17.html"' in html_doc
    assert "2026-W17" in html_doc


def test_render_page_shows_picks_count_when_known(tmp_path):
    weekly = tmp_path / "weekly"
    _seed_weekly(weekly, "2026-W17.html", SAMPLE_HTML_WITH_META)
    entries = ba.load_archive_entries(weekly)
    html_doc = ba.render_page(entries)
    assert "20 picks" in html_doc


def test_render_page_emits_empty_placeholder_when_no_entries():
    html_doc = ba.render_page([])
    assert "No weekly digests yet" in html_doc
    assert "weekly/" not in html_doc  # no list items when empty


def test_render_page_escapes_summary_text():
    entry = ba.ArchiveEntry(
        year=2026,
        week=17,
        filename="2026-W17.html",
        monday=date(2026, 4, 20),
        sunday=date(2026, 4, 26),
        pick_count=3,
        description='Evil <script>alert("x")</script> text',
    )
    html_doc = ba.render_page([entry])
    assert "<script>alert" not in html_doc
    assert "&lt;script&gt;" in html_doc


def test_render_page_includes_canonical_and_rss_link():
    html_doc = ba.render_page([])
    assert 'rel="canonical"' in html_doc
    assert 'type="application/rss+xml"' in html_doc


def test_render_page_uses_deterministic_timestamp():
    fixed = datetime(2026, 4, 22, 5, 30, tzinfo=timezone.utc)
    html_doc = ba.render_page([], generated_at=fixed)
    assert "2026-04-22 05:30 UTC" in html_doc


# ---------- End-to-end write ---------------------------------------------------


def test_write_archive_creates_output_file(tmp_path):
    weekly = tmp_path / "weekly"
    _seed_weekly(weekly, "2026-W17.html", SAMPLE_HTML_WITH_META)
    out = tmp_path / "out" / "archive.html"
    path, count = ba.write_archive(weekly_dir=weekly, out_path=out)
    assert path == out
    assert count == 1
    body = out.read_text(encoding="utf-8")
    assert "weekly/2026-W17.html" in body


def test_write_archive_handles_empty_weekly_dir(tmp_path):
    weekly = tmp_path / "weekly"
    weekly.mkdir()
    out = tmp_path / "archive.html"
    path, count = ba.write_archive(weekly_dir=weekly, out_path=out)
    assert count == 0
    assert out.exists()
    assert "No weekly digests yet" in out.read_text(encoding="utf-8")


def test_main_accepts_custom_weekly_and_out_dirs(tmp_path):
    weekly = tmp_path / "weekly"
    _seed_weekly(weekly, "2026-W17.html", SAMPLE_HTML_WITH_META)
    out = tmp_path / "archive.html"
    rc = ba.main(
        [
            "--weekly-dir",
            str(weekly),
            "--out",
            str(out),
            "--quiet",
        ]
    )
    assert rc == 0
    assert out.exists()
    assert "weekly/2026-W17.html" in out.read_text(encoding="utf-8")
