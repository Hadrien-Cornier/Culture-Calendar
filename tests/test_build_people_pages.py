"""Unit tests for ``scripts/build_people_pages.py``.

Covers the per-role extraction (composer / director / author),
2-event minimum, slugging, upcoming-only filtering, HTML render
contracts (deep-link anchor, rating aria-label, empty-state fallback,
XSS escaping), and ``main`` end-to-end writing.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_people_pages.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("build_people_pages", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["build_people_pages"] = mod
    spec.loader.exec_module(mod)
    return mod


bpp = _load_module()


TODAY = date(2026, 4, 20)


def _events() -> list[dict]:
    return [
        # Director with two upcoming movies → should produce a page.
        {
            "id": "corman-1",
            "title": "Bucket of Blood",
            "rating": 7,
            "one_liner_summary": "Beatnik horror romp.",
            "type": "movie",
            "venue": "AFS",
            "director": "Roger Corman",
            "url": "https://example.org/bucket",
            "screenings": [{"date": "2026-04-22", "time": "19:00"}],
        },
        {
            "id": "corman-2",
            "title": "Little Shop of Horrors",
            "rating": 8,
            "type": "movie",
            "venue": "AFS",
            "director": "Roger Corman",
            "screenings": [{"date": "2026-04-25", "time": "21:00"}],
        },
        # Director with only one event → no page.
        {
            "id": "anderson-1",
            "title": "There Will Be Blood",
            "rating": 9,
            "type": "movie",
            "venue": "AFS",
            "director": "Paul Thomas Anderson",
            "screenings": [{"date": "2026-04-23", "time": "19:30"}],
        },
        # Composer appearing in two concerts.
        {
            "id": "puccini-1",
            "title": "La Bohème",
            "rating": 8,
            "type": "opera",
            "venue": "Opera",
            "composers": ["Giacomo Puccini"],
            "screenings": [{"date": "2026-04-24", "time": "19:30"}],
        },
        {
            "id": "puccini-2",
            "title": "Tosca",
            "rating": 9,
            "type": "opera",
            "venue": "Opera",
            "composers": ["Giacomo Puccini", "Various"],
            "screenings": [{"date": "2026-05-01", "time": "19:30"}],
        },
        # Composer with only one event → no page.
        {
            "id": "ravel-1",
            "title": "Boléro",
            "rating": 7,
            "type": "concert",
            "venue": "Symphony",
            "composers": ["Maurice Ravel"],
            "screenings": [{"date": "2026-04-26", "time": "20:00"}],
        },
        # Author with two book-club events.
        {
            "id": "volodine-1",
            "title": "Minor Angels",
            "rating": 7,
            "type": "book_club",
            "venue": "AlienatedMajesty",
            "author": "Antoine Volodine",
            "screenings": [{"date": "2026-04-29", "time": "18:30"}],
        },
        {
            "id": "volodine-2",
            "title": "Bardo or Not Bardo",
            "rating": 7,
            "type": "book_club",
            "venue": "AlienatedMajesty",
            "author": "Antoine Volodine",
            "screenings": [{"date": "2026-05-06", "time": "18:30"}],
        },
        # Past-only events shouldn't render screenings, but they DO
        # count towards the min-events bucket so the role page still
        # appears (with empty-state).
        {
            "id": "past-only-director",
            "title": "Old Hat",
            "rating": 6,
            "type": "movie",
            "venue": "AFS",
            "director": "Past Master",
            "screenings": [{"date": "2026-04-01", "time": "19:00"}],
        },
        {
            "id": "past-only-director-2",
            "title": "Older Hat",
            "rating": 6,
            "type": "movie",
            "venue": "AFS",
            "director": "Past Master",
            "screenings": [{"date": "2026-03-30", "time": "19:00"}],
        },
        # Placeholder names should never produce pages.
        {
            "id": "various-1",
            "title": "Mixed Bag",
            "rating": 5,
            "type": "concert",
            "venue": "Symphony",
            "composers": ["Various"],
            "screenings": [{"date": "2026-04-28", "time": "20:00"}],
        },
        {
            "id": "various-2",
            "title": "Mixed Bag II",
            "rating": 5,
            "type": "concert",
            "venue": "Symphony",
            "composers": ["various artists"],
            "screenings": [{"date": "2026-05-02", "time": "20:00"}],
        },
    ]


# ---------- slugify -----------------------------------------------------------


def test_slugify_simple_lowercase_hyphenates():
    assert bpp.slugify("Roger Corman") == "roger-corman"


def test_slugify_strips_internal_punctuation():
    assert bpp.slugify("Antoine Volodine, Jr.") == "antoine-volodine-jr"


def test_slugify_collapses_runs_to_single_hyphen():
    assert bpp.slugify("  ---  Giacomo  Puccini  ---  ") == "giacomo-puccini"


def test_slugify_handles_empty_input():
    assert bpp.slugify("") == ""


# ---------- name extraction ---------------------------------------------------


def test_extract_directors_handles_string_and_list():
    assert bpp._extract_directors({"director": "Roger Corman"}) == ["Roger Corman"]
    assert bpp._extract_directors(
        {"directors": ["Roger Corman", "Joe Dante"]}
    ) == ["Roger Corman", "Joe Dante"]


def test_extract_composers_filters_placeholders():
    assert bpp._extract_composers(
        {"composers": ["Giacomo Puccini", "Various", "Others"]}
    ) == ["Giacomo Puccini"]


def test_extract_composers_dedupes_case_insensitively():
    assert bpp._extract_composers(
        {"composers": ["Beethoven", "beethoven"]}
    ) == ["Beethoven"]


def test_extract_authors_handles_blank_and_unknown():
    assert bpp._extract_authors({"author": ""}) == []
    assert bpp._extract_authors({"author": "Unknown"}) == []
    assert bpp._extract_authors({"author": "Antoine Volodine"}) == [
        "Antoine Volodine"
    ]


# ---------- group_by_person ---------------------------------------------------


def test_group_by_person_excludes_singletons():
    pages = bpp.group_by_person(_events(), today=TODAY)
    names = [p.person_name for p in pages]
    assert "Roger Corman" in names  # 2 movies
    assert "Giacomo Puccini" in names  # 2 operas
    assert "Antoine Volodine" in names  # 2 book clubs
    assert "Paul Thomas Anderson" not in names  # only 1 movie
    assert "Maurice Ravel" not in names  # only 1 concert


def test_group_by_person_excludes_placeholder_names():
    pages = bpp.group_by_person(_events(), today=TODAY)
    names = {p.person_name.lower() for p in pages}
    assert "various" not in names
    assert "various artists" not in names
    assert "others" not in names


def test_group_by_person_assigns_correct_role():
    pages = bpp.group_by_person(_events(), today=TODAY)
    by_name = {p.person_name: p for p in pages}
    assert by_name["Roger Corman"].role == bpp.ROLE_DIRECTOR
    assert by_name["Giacomo Puccini"].role == bpp.ROLE_COMPOSER
    assert by_name["Antoine Volodine"].role == bpp.ROLE_AUTHOR


def test_group_by_person_sorts_events_by_first_screening():
    pages = bpp.group_by_person(_events(), today=TODAY)
    corman = next(p for p in pages if p.person_name == "Roger Corman")
    assert corman.events[0].first_screening.date == "2026-04-22"
    assert corman.events[1].first_screening.date == "2026-04-25"


def test_group_by_person_keeps_total_events_count():
    pages = bpp.group_by_person(_events(), today=TODAY)
    corman = next(p for p in pages if p.person_name == "Roger Corman")
    assert corman.total_events == 2


def test_group_by_person_includes_person_with_only_past_events_when_qualifying():
    pages = bpp.group_by_person(_events(), today=TODAY)
    past = next(p for p in pages if p.person_name == "Past Master")
    assert past.events == ()
    assert past.total_events == 2


def test_group_by_person_respects_min_events_override():
    pages = bpp.group_by_person(_events(), today=TODAY, min_events=1)
    names = {p.person_name for p in pages}
    assert "Paul Thomas Anderson" in names
    assert "Maurice Ravel" in names


def test_group_by_person_respects_per_person_limit():
    pages = bpp.group_by_person(_events(), today=TODAY, limit=1)
    for p in pages:
        assert len(p.events) <= 1


# ---------- render_page contracts ---------------------------------------------


def _page_for(name: str, events=None) -> "bpp.PersonPage":
    pages = bpp.group_by_person(
        events if events is not None else _events(), today=TODAY
    )
    return next(p for p in pages if p.person_name == name)


def test_render_page_embeds_deep_link_anchor():
    html_doc = bpp.render_page(_page_for("Roger Corman"))
    assert "../#event=corman-1" in html_doc
    assert "../#event=corman-2" in html_doc


def test_render_page_includes_rating_badge_with_aria_label():
    html_doc = bpp.render_page(_page_for("Giacomo Puccini"))
    assert "8 / 10" in html_doc
    assert 'aria-label="rated 8 out of 10"' in html_doc


def test_render_page_includes_role_label_in_eyebrow():
    html_doc = bpp.render_page(_page_for("Roger Corman"))
    assert "Director" in html_doc


def test_render_page_includes_role_specific_description():
    html_doc = bpp.render_page(_page_for("Antoine Volodine"))
    assert "author" in html_doc.lower()


def test_render_page_shows_empty_state_when_no_upcoming_events():
    html_doc = bpp.render_page(_page_for("Past Master"))
    assert "No upcoming events" in html_doc


def test_render_page_escapes_title_html():
    evil_events = [
        {
            "id": "evil-1",
            "title": "Evil <script>alert(1)</script>",
            "rating": 7,
            "type": "movie",
            "venue": "AFS",
            "director": "Mister Evil",
            "screenings": [{"date": "2026-04-25", "time": "18:00"}],
        },
        {
            "id": "evil-2",
            "title": "Tame Sequel",
            "rating": 7,
            "type": "movie",
            "venue": "AFS",
            "director": "Mister Evil",
            "screenings": [{"date": "2026-04-28", "time": "18:00"}],
        },
    ]
    page = _page_for("Mister Evil", events=evil_events)
    html_doc = bpp.render_page(page)
    assert "<script>alert(1)</script>" not in html_doc
    assert "&lt;script&gt;" in html_doc


def test_render_page_links_back_to_index():
    html_doc = bpp.render_page(_page_for("Roger Corman"))
    assert '<a href="../">' in html_doc


def test_render_page_sets_utf8_and_viewport_meta():
    html_doc = bpp.render_page(_page_for("Roger Corman"))
    assert '<meta charset="utf-8">' in html_doc
    assert "viewport" in html_doc


def test_render_page_includes_webcal_subscription_link():
    html_doc = bpp.render_page(_page_for("Roger Corman"))
    assert "webcal://" in html_doc


def test_render_page_renders_category_label_not_raw_type():
    html_doc = bpp.render_page(_page_for("Roger Corman"))
    assert "Film" in html_doc


# ---------- write_pages + main ------------------------------------------------


def test_write_pages_creates_one_file_per_qualifying_person(tmp_path):
    out_dir = tmp_path / "people"
    written = bpp.write_pages(_events(), out_dir=out_dir, today=TODAY)
    paths = sorted(p.name for p, _ in written)
    assert "roger-corman.html" in paths
    assert "giacomo-puccini.html" in paths
    assert "antoine-volodine.html" in paths
    # Singletons are not written.
    assert "paul-thomas-anderson.html" not in paths
    assert "maurice-ravel.html" not in paths


def test_write_pages_files_contain_person_title(tmp_path):
    out_dir = tmp_path / "people"
    bpp.write_pages(_events(), out_dir=out_dir, today=TODAY)
    body = (out_dir / "roger-corman.html").read_text(encoding="utf-8")
    assert "Roger Corman" in body
    assert "Bucket of Blood" in body
    assert "<!DOCTYPE html>" in body


def test_main_writes_people_pages_for_explicit_today(tmp_path):
    data_path = tmp_path / "data.json"
    data_path.write_text(json.dumps(_events()))
    out_dir = tmp_path / "people"
    exit_code = bpp.main(
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
    # At least the three qualifying people + Past Master (qualifies on
    # total but not on upcoming).
    assert len(files) >= 3


def test_main_rejects_bad_today_format(tmp_path):
    data_path = tmp_path / "data.json"
    data_path.write_text(json.dumps(_events()))
    out_dir = tmp_path / "people"
    with pytest.raises(SystemExit):
        bpp.main(
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


def test_main_smoke_on_live_data_generates_at_least_one_page(tmp_path):
    """Guards the per-task validation: ``ls docs/people/*.html`` non-empty."""
    live_data = REPO_ROOT / "docs" / "data.json"
    if not live_data.exists():
        pytest.skip("docs/data.json not present in this checkout")
    out_dir = tmp_path / "people"
    exit_code = bpp.main(
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
    assert len(files) >= 1
