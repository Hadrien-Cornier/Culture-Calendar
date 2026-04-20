"""Unit tests for ``scripts/build_venue_pages.py``.

Covers slug generation, venue grouping, upcoming-only filtering,
HTML render contracts (deep-link anchor, rating aria-label, empty-state
fallback, XSS escaping), and ``main`` end-to-end writing.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_venue_pages.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("build_venue_pages", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["build_venue_pages"] = mod
    spec.loader.exec_module(mod)
    return mod


bvp = _load_module()


TODAY = date(2026, 4, 20)


def _events() -> list[dict]:
    return [
        {
            "id": "baroque-night",
            "title": "Baroque Night",
            "rating": 9,
            "one_liner_summary": "Crisp period programme of early-Baroque canzonas.",
            "type": "concert",
            "venue": "LaFollia",
            "url": "https://example.org/baroque",
            "screenings": [
                {"date": "2026-04-24", "time": "19:30", "venue": "LaFollia"},
                {"date": "2026-04-25", "time": "19:30", "venue": "LaFollia"},
            ],
        },
        {
            "id": "serious-man",
            "title": "A SERIOUS MAN",
            "rating": 8,
            "one_liner_summary": "Coen brothers' existential masterpiece.",
            "type": "movie",
            "venue": "AFS",
            "url": "https://example.org/serious",
            "screenings": [{"date": "2026-04-21", "time": "19:00", "venue": "AFS"}],
        },
        {
            "id": "already-over",
            "title": "Past Event",
            "rating": 7,
            "type": "movie",
            "venue": "AFS",
            "screenings": [{"date": "2026-04-01", "time": "19:00"}],
        },
        {
            "id": "blanton-tour",
            "title": "Collection Tour",
            "rating": 6,
            "one_liner_summary": "Guided tour of the permanent collection.",
            "type": "visual_arts",
            "venue": "Blanton Museum of Art, Austin",
            "url": "https://example.org/blanton",
            "screenings": [{"date": "2026-04-26", "time": "14:00"}],
        },
        {
            "id": "dougherty-show",
            "title": "Metamorphosis",
            "rating": 7,
            "type": "visual_arts",
            "venue": "Dougherty Arts Center, Austin",
            "url": "https://example.org/dougherty",
            "screenings": [{"date": "2026-04-22", "time": "10:00"}],
        },
        {
            "id": "no-venue",
            "title": "Floating Event",
            "rating": 5,
            "type": "other",
            "venue": "",
            "screenings": [{"date": "2026-04-25", "time": "18:00"}],
        },
        {
            "id": "past-only",
            "title": "Expired Only",
            "rating": 5,
            "type": "other",
            "venue": "The Cathedral, Austin",
            "screenings": [{"date": "2026-04-01", "time": "19:00"}],
        },
    ]


# ---------- slugify -----------------------------------------------------------


def test_slugify_simple_lowercase_hyphenates():
    assert bvp.slugify("Hyperreal") == "hyperreal"


def test_slugify_strips_commas_and_collapses_runs():
    assert bvp.slugify("Blanton Museum of Art, Austin") == (
        "blanton-museum-of-art-austin"
    )


def test_slugify_strips_leading_and_trailing_hyphens():
    assert bvp.slugify("  -- The Cathedral, Austin  --  ") == (
        "the-cathedral-austin"
    )


def test_slugify_handles_internal_symbols():
    assert bvp.slugify("First & Light!!") == "first-light"


def test_slugify_handles_camel_case_venues():
    # The scraper-side venue id "BalletAustin" must still produce a single run.
    assert bvp.slugify("BalletAustin") == "balletaustin"


def test_slugify_handles_empty_input():
    assert bvp.slugify("") == ""


# ---------- group_by_venue -----------------------------------------------------


def test_group_by_venue_produces_one_page_per_distinct_venue():
    pages = bvp.group_by_venue(_events(), today=TODAY)
    names = [p.venue_name for p in pages]
    assert "AFS" in names
    assert "LaFollia" in names
    assert "Blanton Museum of Art, Austin" in names
    assert "Dougherty Arts Center, Austin" in names
    # Blank venues are dropped.
    assert "" not in names


def test_group_by_venue_keeps_venue_with_no_upcoming_events():
    pages = bvp.group_by_venue(_events(), today=TODAY)
    cathedral = next(p for p in pages if p.venue_name == "The Cathedral, Austin")
    assert cathedral.events == ()
    # Total includes the past screening so the page reflects the venue's
    # tracked footprint, even when nothing is currently upcoming.
    assert cathedral.total_events == 1


def test_group_by_venue_filters_past_screenings_only():
    pages = bvp.group_by_venue(_events(), today=TODAY)
    afs = next(p for p in pages if p.venue_name == "AFS")
    ids = [e.event_id for e in afs.events]
    assert "serious-man" in ids
    assert "already-over" not in ids


def test_group_by_venue_sorts_events_by_first_screening():
    pages = bvp.group_by_venue(_events(), today=TODAY)
    lafollia = next(p for p in pages if p.venue_name == "LaFollia")
    assert lafollia.events[0].first_screening.date == "2026-04-24"


def test_group_by_venue_respects_per_venue_limit():
    pages = bvp.group_by_venue(_events(), today=TODAY, limit=1)
    for p in pages:
        assert len(p.events) <= 1


def test_group_by_venue_picks_curated_description_for_known_venue():
    pages = bvp.group_by_venue(_events(), today=TODAY)
    afs = next(p for p in pages if p.venue_name == "AFS")
    assert "Austin Film Society" in afs.description


def test_group_by_venue_falls_back_to_generic_description_for_unknown_venue():
    events = [
        {
            "id": "mystery-1",
            "title": "Mystery Show",
            "rating": 5,
            "type": "concert",
            "venue": "Unknown Venue XYZ",
            "screenings": [{"date": "2026-04-25", "time": "20:00"}],
        }
    ]
    pages = bvp.group_by_venue(events, today=TODAY)
    mystery = next(p for p in pages if p.venue_name == "Unknown Venue XYZ")
    assert "Unknown Venue XYZ" in mystery.description
    assert mystery.description  # non-empty


# ---------- render_page contracts ---------------------------------------------


def _page_for(venue: str, events=None) -> "bvp.VenuePage":
    pages = bvp.group_by_venue(events if events is not None else _events(), today=TODAY)
    return next(p for p in pages if p.venue_name == venue)


def test_render_page_embeds_deep_link_anchor():
    html_doc = bvp.render_page(_page_for("AFS"))
    assert "../#event=serious-man" in html_doc


def test_render_page_includes_rating_badge_with_aria_label():
    html_doc = bvp.render_page(_page_for("LaFollia"))
    assert "9 / 10" in html_doc
    assert 'aria-label="rated 9 out of 10"' in html_doc


def test_render_page_includes_venue_description_paragraph():
    html_doc = bvp.render_page(_page_for("AFS"))
    assert 'class="venue-description"' in html_doc
    assert "Austin Film Society" in html_doc


def test_render_page_shows_empty_state_when_no_upcoming_events():
    html_doc = bvp.render_page(_page_for("The Cathedral, Austin"))
    assert "No upcoming events" in html_doc


def test_render_page_escapes_title_html():
    evil_events = [
        {
            "id": "evil",
            "title": "Evil <script>alert(1)</script>",
            "rating": 7,
            "type": "other",
            "venue": "EvilVenue",
            "screenings": [{"date": "2026-04-25", "time": "18:00"}],
        }
    ]
    page = _page_for("EvilVenue", events=evil_events)
    html_doc = bvp.render_page(page)
    assert "<script>alert(1)</script>" not in html_doc
    assert "&lt;script&gt;" in html_doc


def test_render_page_links_back_to_index():
    html_doc = bvp.render_page(_page_for("AFS"))
    assert '<a href="../">' in html_doc


def test_render_page_sets_utf8_and_viewport_meta():
    html_doc = bvp.render_page(_page_for("AFS"))
    assert '<meta charset="utf-8">' in html_doc
    assert "viewport" in html_doc


def test_render_page_includes_webcal_subscription_link():
    html_doc = bvp.render_page(_page_for("AFS"))
    assert "webcal://" in html_doc


def test_render_page_renders_category_label_not_raw_type():
    html_doc = bvp.render_page(_page_for("AFS"))
    # "Film" label rather than the raw "movie" slug.
    assert "Film" in html_doc


# ---------- write_pages + main ------------------------------------------------


def test_write_pages_creates_one_file_per_distinct_venue(tmp_path):
    out_dir = tmp_path / "venues"
    written = bvp.write_pages(_events(), out_dir=out_dir, today=TODAY)
    paths = sorted(p.name for p, _ in written)
    # Every distinct non-empty venue should get a file.
    assert "afs.html" in paths
    assert "lafollia.html" in paths
    assert "blanton-museum-of-art-austin.html" in paths
    assert "dougherty-arts-center-austin.html" in paths
    # Empty-state venues are still rendered.
    assert "the-cathedral-austin.html" in paths


def test_write_pages_files_contain_venue_title(tmp_path):
    out_dir = tmp_path / "venues"
    bvp.write_pages(_events(), out_dir=out_dir, today=TODAY)
    body = (out_dir / "afs.html").read_text(encoding="utf-8")
    assert "A SERIOUS MAN" in body
    assert "<!DOCTYPE html>" in body


def test_main_writes_venue_pages_for_explicit_today(tmp_path):
    data_path = tmp_path / "data.json"
    data_path.write_text(json.dumps(_events()))
    out_dir = tmp_path / "venues"
    exit_code = bvp.main(
        [
            "--data",
            str(data_path),
            "--out-dir",
            str(out_dir),
            "--today",
            TODAY.isoformat(),
            "--quiet",
        ]
    )
    assert exit_code == 0
    files = sorted(out_dir.glob("*.html"))
    assert len(files) >= 5


def test_main_rejects_bad_today_format(tmp_path):
    data_path = tmp_path / "data.json"
    data_path.write_text(json.dumps(_events()))
    out_dir = tmp_path / "venues"
    with pytest.raises(SystemExit):
        bvp.main(
            [
                "--data",
                str(data_path),
                "--out-dir",
                str(out_dir),
                "--today",
                "not-a-date",
                "--quiet",
            ]
        )


def test_main_smoke_on_live_data_generates_at_least_10_pages(tmp_path):
    # Guards the per-task validation: `ls docs/venues/*.html | wc -l` ≥ 10.
    live_data = REPO_ROOT / "docs" / "data.json"
    if not live_data.exists():
        pytest.skip("docs/data.json not present in this checkout")
    out_dir = tmp_path / "venues"
    exit_code = bvp.main(
        [
            "--data",
            str(live_data),
            "--out-dir",
            str(out_dir),
            "--today",
            TODAY.isoformat(),
            "--quiet",
        ]
    )
    assert exit_code == 0
    files = list(out_dir.glob("*.html"))
    assert len(files) >= 10
