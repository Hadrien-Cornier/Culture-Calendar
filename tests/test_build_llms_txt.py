"""Unit tests for scripts/build_llms_txt.py.

Covers the llmstxt.org index format, HTML-to-text extraction used for
the full content dump, event ranking, page discovery, and the top-level
``main`` entrypoint.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_llms_txt.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("build_llms_txt", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["build_llms_txt"] = mod
    spec.loader.exec_module(mod)
    return mod


bll = _load_module()


NOW = datetime(2026, 4, 22, 5, 46, 31, tzinfo=timezone.utc)


def _sample_events() -> list[dict]:
    return [
        {
            "id": "bold-baroque",
            "title": "Bold Baroque Night",
            "rating": 9,
            "one_liner_summary": "A bracing early-Baroque programme.",
            "description": "<p>Full <strong>review</strong> body.</p><p>Second paragraph.</p>",
            "type": "concert",
            "venue": "La Follia Hall",
            "screenings": [{"date": "2026-05-01", "time": "19:30"}],
        },
        {
            "id": "modest-matinee",
            "title": "Modest Matinee",
            "rating": 5,
            "description": "<p>Midrange review.</p>",
            "type": "movie",
            "venue": "AFS",
            "dates": ["2026-06-01"],
            "times": ["14:00"],
        },
        {
            "id": "unrated",
            "title": "Unrated Curiosity",
            "description": "<p>TBD.</p>",
            "type": "other",
            "screenings": [{"date": "2026-07-01", "time": "18:00"}],
        },
        {
            "id": "dance-show",
            "title": "Dance Show",
            "rating": 7,
            "description": "<p>Dance review.</p>",
            "type": "dance",
            "venue": "Ballet Austin",
            "screenings": [{"date": "2026-06-15", "time": "20:00"}],
        },
    ]


@pytest.fixture
def events() -> list[dict]:
    return _sample_events()


@pytest.fixture
def fake_docs(tmp_path: Path) -> Path:
    """A minimal docs/ tree with subdirectory HTML pages for discovery tests."""
    root = tmp_path / "docs"
    (root / "venues").mkdir(parents=True)
    (root / "people").mkdir()
    (root / "weekly").mkdir()
    (root / "venues" / "afs.html").write_text("x", encoding="utf-8")
    (root / "venues" / "lafollia.html").write_text("x", encoding="utf-8")
    (root / "people" / "ludwig-van-beethoven.html").write_text("x", encoding="utf-8")
    (root / "weekly" / "2026-W17.html").write_text("x", encoding="utf-8")
    return root


def test_html_to_text_strips_tags_and_collapses_whitespace():
    html = "<p>Hello <strong>world</strong></p><p>Second.</p>"
    text = bll.html_to_text(html)
    assert "Hello world" in text
    assert "Second." in text
    assert "<" not in text and ">" not in text


def test_html_to_text_handles_empty():
    assert bll.html_to_text("") == ""


def test_absolute_url_joins_and_preserves_absolute():
    assert bll._absolute_url("") == bll.SITE_BASE_URL
    assert bll._absolute_url("feed.xml") == bll.SITE_BASE_URL + "feed.xml"
    assert bll._absolute_url("https://other.example/x") == "https://other.example/x"


def test_event_first_date_prefers_screenings():
    e = {
        "screenings": [
            {"date": "2026-05-02"},
            {"date": "2026-05-01"},
        ],
        "dates": ["2099-01-01"],
    }
    assert bll._event_first_date(e) == "2026-05-01"


def test_event_first_date_falls_back_to_dates():
    assert bll._event_first_date({"dates": ["2026-08-01"]}) == "2026-08-01"


def test_event_first_date_empty_when_missing():
    assert bll._event_first_date({}) == ""


def test_top_events_ranks_by_rating_desc(events):
    top = bll._top_events(events, limit=10)
    rated = [e["title"] for e in top]
    # Highest rating first; unrated sinks to the bottom.
    assert rated[0] == "Bold Baroque Night"
    assert rated[1] == "Dance Show"
    assert rated[2] == "Modest Matinee"
    assert rated[-1] == "Unrated Curiosity"


def test_top_events_respects_limit(events):
    assert len(bll._top_events(events, limit=2)) == 2


def test_top_events_skips_missing_title(events):
    dirty = events + [{"rating": 10}, "not a dict"]  # type: ignore[list-item]
    titles = [e["title"] for e in bll._top_events(dirty, limit=10)]
    assert "Bold Baroque Night" in titles
    assert len(titles) == len(events)  # malformed entries filtered


def test_render_llms_txt_has_required_spec_sections(events, fake_docs):
    body = bll.render_llms_txt(events, docs_root=fake_docs)
    # llmstxt.org format: H1 + quoted description
    assert body.startswith("# Culture Calendar\n")
    assert "\n> " in body
    # Mandatory sections
    assert "## Core pages" in body
    assert "## Subscribable feeds" in body
    assert "## Categories" in body
    assert "## Venues" in body
    assert "## People" in body
    assert "## Weekly digests" in body


def test_render_llms_txt_includes_category_counts(events, fake_docs):
    body = bll.render_llms_txt(events, docs_root=fake_docs)
    assert "Concert — 1 event" in body
    assert "Film — 1 event" in body
    assert "Dance — 1 event" in body
    assert "Other — 1 event" in body


def test_render_llms_txt_includes_discovered_pages(events, fake_docs):
    body = bll.render_llms_txt(events, docs_root=fake_docs)
    assert "venues/afs.html" in body
    assert "venues/lafollia.html" in body
    assert "people/ludwig-van-beethoven.html" in body
    assert "weekly/2026-W17.html" in body


def test_render_llms_txt_absolute_feed_links(events, fake_docs):
    body = bll.render_llms_txt(events, docs_root=fake_docs)
    assert f"{bll.SITE_BASE_URL}feed.xml" in body
    assert f"{bll.SITE_BASE_URL}calendar.ics" in body
    assert f"{bll.SITE_BASE_URL}top-picks.ics" in body


def test_render_llms_txt_omits_empty_subdirs(events, tmp_path):
    empty_docs = tmp_path / "docs"
    empty_docs.mkdir()
    body = bll.render_llms_txt(events, docs_root=empty_docs)
    assert "## Venues" not in body
    assert "## People" not in body
    assert "## Weekly digests" not in body
    # Core + feeds + categories still render even without discovered pages.
    assert "## Core pages" in body
    assert "## Categories" in body


def test_render_llms_full_txt_includes_header_stats_and_events(events):
    body = bll.render_llms_full_txt(events, about_text="About body.", now=NOW)
    assert "Culture Calendar — Full content dump for LLMs" in body
    assert "Generated: 2026-04-22T05:46:31Z" in body
    assert "About\n-----\nAbout body." in body
    assert "Statistics\n----------" in body
    assert f"Total events: {len(events)}" in body
    # Highest-rated event renders with a rating prefix and hook label.
    assert "[9/10] Bold Baroque Night" in body
    assert "Hook: A bracing early-Baroque programme." in body
    # HTML stripped from review.
    assert "Full review body." in body
    assert "<" not in body and ">" not in body


def test_render_llms_full_txt_truncates_long_reviews():
    long_review = "X" * (bll.MAX_REVIEW_CHARS + 500)
    event = {
        "id": "long",
        "title": "Long",
        "rating": 8,
        "description": f"<p>{long_review}</p>",
        "type": "other",
    }
    body = bll.render_llms_full_txt([event], now=NOW)
    review_line = next(line for line in body.splitlines() if line.startswith("Review:"))
    # -1 for the ellipsis, plus the "Review: " prefix length
    assert len(review_line) <= len("Review: ") + bll.MAX_REVIEW_CHARS
    assert review_line.endswith("…")


def test_write_outputs_produces_both_files(events, fake_docs, tmp_path):
    out_index = tmp_path / "llms.txt"
    out_full = tmp_path / "llms-full.txt"
    index_bytes, full_bytes = bll.write_outputs(
        events,
        docs_root=fake_docs,
        out_index=out_index,
        out_full=out_full,
        about_path=tmp_path / "missing-about.md",
        now=NOW,
    )
    assert index_bytes > 0
    assert full_bytes > 0
    assert "Culture Calendar" in out_index.read_text(encoding="utf-8")
    assert "Culture Calendar" in out_full.read_text(encoding="utf-8")


def test_write_outputs_reads_about_when_present(events, fake_docs, tmp_path):
    about = tmp_path / "ABOUT.md"
    about.write_text("# Custom about\n\nHello world.\n", encoding="utf-8")
    out_index = tmp_path / "llms.txt"
    out_full = tmp_path / "llms-full.txt"
    bll.write_outputs(
        events,
        docs_root=fake_docs,
        out_index=out_index,
        out_full=out_full,
        about_path=about,
        now=NOW,
    )
    assert "Hello world." in out_full.read_text(encoding="utf-8")


def test_main_writes_files_from_data(events, fake_docs, tmp_path):
    data_path = tmp_path / "data.json"
    data_path.write_text(json.dumps(events), encoding="utf-8")
    out_index = tmp_path / "llms.txt"
    out_full = tmp_path / "llms-full.txt"
    about = tmp_path / "ABOUT.md"
    about.write_text("Alpha.", encoding="utf-8")

    exit_code = bll.main(
        [
            "--data",
            str(data_path),
            "--docs",
            str(fake_docs),
            "--about",
            str(about),
            "--out-index",
            str(out_index),
            "--out-full",
            str(out_full),
            "--top-n",
            "2",
            "--quiet",
        ]
    )
    assert exit_code == 0
    assert out_index.exists() and out_full.exists()
    full_body = out_full.read_text(encoding="utf-8")
    assert "Alpha." in full_body
    # Only two events in the top section because of --top-n 2.
    heading = next(
        line
        for line in full_body.splitlines()
        if line.startswith("Top events (ranked by rating")
    )
    assert "up to 2" in heading


def test_load_events_rejects_non_list(tmp_path):
    bad = tmp_path / "data.json"
    bad.write_text(json.dumps({"not": "a list"}))
    with pytest.raises(ValueError):
        bll.load_events(bad)


def test_load_events_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        bll.load_events(tmp_path / "nope.json")


def test_discover_subdir_pages_sorted(fake_docs):
    pages = bll._discover_subdir_pages(fake_docs, "venues")
    urls = [p.url for p in pages]
    assert urls == sorted(urls)
    assert all(u.startswith(bll.SITE_BASE_URL) for u in urls)


def test_discover_subdir_pages_empty_when_missing(tmp_path):
    assert bll._discover_subdir_pages(tmp_path, "venues") == []
