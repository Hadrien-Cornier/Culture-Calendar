"""Unit tests for scripts/build_og_cards.py.

Covers: event normalization, title wrapping, XML-escaping, rating badge
selection, filename safety, stale-card cleanup, and CLI entrypoint.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_og_cards.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("build_og_cards", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["build_og_cards"] = mod
    spec.loader.exec_module(mod)
    return mod


boc = _load_module()


def _sample_events() -> list[dict]:
    return [
        {
            "id": "hidden-gems-2025-01-09",
            "title": "Hidden Gems",
            "venue": "LaFollia",
            "rating": 6,
            "type": "concert",
            "screenings": [
                {"date": "2025-01-09", "time": "19:30", "venue": "LaFollia Hall"}
            ],
        },
        {
            "id": "low-budget-movie-2026-03-15",
            "title": "A Very Long Title That Should Definitely Be Wrapped Across Several Lines For Readability",
            "venue": "AFS Cinema",
            "rating": 9,
            "type": "movie",
            "dates": ["2026-03-15"],
            "times": ["19:00"],
        },
        {
            "id": "unrated-exhibit-2026-05-01",
            "title": "Garden & Grove <Exhibit>",
            "venue": "Contemporary Austin",
            "rating": None,
            "type": "visual_arts",
            "screenings": [{"date": "2026-05-01", "time": "10:00"}],
        },
        {
            "id": "no-venue-event",
            "title": "Mystery Event",
            "rating": 5,
            "type": "other",
            "screenings": [{"date": "2026-07-04", "time": "20:00"}],
        },
    ]


def test_safe_filename_strips_special_chars():
    assert boc._safe_filename("Hello World!") == "hello-world"
    assert boc._safe_filename("../etc/passwd") == "etc-passwd"
    assert boc._safe_filename("ok_name-2026.01") == "ok_name-2026.01"
    assert boc._safe_filename("") == "event"
    assert boc._safe_filename("!!!") == "event"


def test_xml_escape_handles_all_special_chars():
    assert boc._xml_escape("a & b < c > d \"e\" 'f'") == (
        "a &amp; b &lt; c &gt; d &quot;e&quot; &apos;f&apos;"
    )


def test_wrap_title_short_title_single_line():
    lines = boc._wrap_title("Hi there", max_chars=28, max_lines=3)
    assert lines == ["Hi there"]


def test_wrap_title_respects_max_lines_with_ellipsis():
    long = "word " * 40
    lines = boc._wrap_title(long.strip(), max_chars=20, max_lines=3)
    assert len(lines) == 3
    assert lines[-1].endswith("\u2026")


def test_wrap_title_handles_oversized_word():
    lines = boc._wrap_title("supercalifragilisticexpialidocious", max_chars=10, max_lines=2)
    assert lines[0].endswith("\u2026")
    assert len(lines[0]) == 10


def test_wrap_title_empty_returns_single_empty_line():
    assert boc._wrap_title("", max_chars=20, max_lines=3) == [""]


def test_rating_int_rejects_out_of_range():
    assert boc._rating_int(-1) is None
    assert boc._rating_int(11) is None
    assert boc._rating_int("not a number") is None
    assert boc._rating_int(None) is None
    assert boc._rating_int(5) == 5
    assert boc._rating_int("8") == 8


def test_normalize_event_requires_id_and_title_fallback():
    good = boc._normalize_event({"id": "x", "title": "Thing"})
    assert good is not None and good.event_id == "x" and good.title == "Thing"

    no_id = boc._normalize_event({"title": "Thing"})
    assert no_id is not None and no_id.event_id == "Thing"

    empty = boc._normalize_event({})
    assert empty is None

    assert boc._normalize_event("not a dict") is None  # type: ignore[arg-type]


def test_normalize_event_pulls_date_from_screenings_then_dates():
    with_screenings = boc._normalize_event(
        {"id": "a", "title": "A", "screenings": [{"date": "2026-05-01"}]}
    )
    assert with_screenings.date == "2026-05-01"

    with_dates = boc._normalize_event(
        {"id": "a", "title": "A", "dates": ["2026-06-01"]}
    )
    assert with_dates.date == "2026-06-01"


def test_render_svg_contains_required_elements():
    card = boc.CardData(
        event_id="id-1",
        title="Test Concert",
        venue="Test Hall",
        date="2026-05-01",
        rating=8,
        type_="concert",
    )
    svg = boc.render_svg(card)
    assert svg.startswith("<?xml")
    assert 'viewBox="0 0 1200 630"' in svg
    assert "Test Concert" in svg
    assert "Test Hall" in svg
    assert "8 / 10" in svg
    assert "CONCERT" in svg


def test_render_svg_unrated_shows_placeholder():
    card = boc.CardData(
        event_id="id-2",
        title="Unrated",
        venue="",
        date="2026-05-01",
        rating=None,
        type_="visual_arts",
    )
    svg = boc.render_svg(card)
    assert "Pending review" in svg
    assert "/10" not in svg


def test_render_svg_escapes_dangerous_title_chars():
    card = boc.CardData(
        event_id="id-3",
        title="<script>alert('x')</script>",
        venue="A & B",
        date="",
        rating=5,
        type_="movie",
    )
    svg = boc.render_svg(card)
    assert "<script>" not in svg
    assert "&lt;script&gt;" in svg
    assert "&amp;" in svg


def test_render_svg_is_well_formed_xml():
    card = boc.CardData(
        event_id="id-4",
        title="Some & <chars> like \"quotes\"",
        venue="Venue",
        date="2026-05-01",
        rating=7,
        type_="concert",
    )
    svg = boc.render_svg(card)
    # Must parse without error — catches stray unescaped characters.
    root = ET.fromstring(svg)
    assert root.tag.endswith("svg")
    assert root.attrib["viewBox"] == "0 0 1200 630"


def test_render_svg_all_category_themes_are_well_formed():
    for cat in boc._CATEGORY_THEME:
        card = boc.CardData(
            event_id=f"id-{cat}",
            title=f"Sample {cat}",
            venue="Venue",
            date="2026-05-01",
            rating=7,
            type_=cat,
        )
        ET.fromstring(boc.render_svg(card))


def test_write_cards_creates_one_svg_per_event(tmp_path):
    out_dir = tmp_path / "og"
    count = boc.write_cards(_sample_events(), out_dir=out_dir)
    assert count == 4
    svgs = sorted(p.name for p in out_dir.glob("*.svg"))
    assert len(svgs) == 4
    # Spot check a known file parses.
    first = next(out_dir.glob("*.svg"))
    ET.fromstring(first.read_text(encoding="utf-8"))


def test_write_cards_cleans_stale_files_by_default(tmp_path):
    out_dir = tmp_path / "og"
    out_dir.mkdir()
    stale = out_dir / "stale.svg"
    stale.write_text("<svg/>", encoding="utf-8")

    boc.write_cards(_sample_events(), out_dir=out_dir)
    assert not stale.exists()


def test_write_cards_no_clean_keeps_stale(tmp_path):
    out_dir = tmp_path / "og"
    out_dir.mkdir()
    stale = out_dir / "stale.svg"
    stale.write_text("<svg/>", encoding="utf-8")

    boc.write_cards(_sample_events(), out_dir=out_dir, clean=False)
    assert stale.exists()


def test_main_writes_cards_via_data_file(tmp_path, capsys):
    data_path = tmp_path / "data.json"
    out_dir = tmp_path / "og"
    data_path.write_text(json.dumps(_sample_events()))

    exit_code = boc.main(
        [
            "--data",
            str(data_path),
            "--out-dir",
            str(out_dir),
            "--quiet",
        ]
    )
    assert exit_code == 0
    assert sum(1 for _ in out_dir.glob("*.svg")) == 4


def test_main_prints_summary_when_not_quiet(tmp_path, capsys):
    data_path = tmp_path / "data.json"
    out_dir = tmp_path / "og"
    data_path.write_text(json.dumps(_sample_events()[:1]))

    boc.main(["--data", str(data_path), "--out-dir", str(out_dir)])
    out = capsys.readouterr().out
    assert "Wrote" in out and "1" in out


def test_load_events_rejects_non_list(tmp_path):
    bad = tmp_path / "data.json"
    bad.write_text(json.dumps({"not": "a list"}))
    with pytest.raises(ValueError):
        boc.load_events(bad)


def test_load_events_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        boc.load_events(tmp_path / "does-not-exist.json")


def test_render_svg_handles_missing_venue_and_date():
    card = boc.CardData(
        event_id="id-x",
        title="Solo",
        venue="",
        date="",
        rating=3,
        type_="other",
    )
    svg = boc.render_svg(card)
    # Still well-formed; meta line falls back to "Austin".
    ET.fromstring(svg)
    assert "Austin" in svg
