"""Unit tests for ``scripts/build_weekly_digest.py``.

Covers ISO-week selection, pick ranking, review-section porting from
``parseReview`` (docs/script.js:561-587), and HTML rendering contracts
(webcal link, deep-link anchors, rating badge, empty-week fallback).
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from datetime import date
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_weekly_digest.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("build_weekly_digest", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["build_weekly_digest"] = mod
    spec.loader.exec_module(mod)
    return mod


bwd = _load_module()


WEEK_YEAR = 2026
WEEK_NO = 17
MONDAY = date(2026, 4, 20)
SUNDAY = date(2026, 4, 26)

SAMPLE_DESC = (
    "<p>\u2605 <strong>Rating: 8/10</strong></p>"
    "<p>\U0001F3AD <strong>Artistic Merit</strong> \u2013 "
    "Crisp period performance of Castello canzonas with keen articulation.</p>"
    "<p>\u2728 <strong>Originality</strong> \u2013 Pulls from obscure figures "
    "beyond the Monteverdi canon.</p>"
)


def _events() -> list[dict]:
    return [
        {
            "id": "in-week-top",
            "title": "Bold Baroque Night",
            "rating": 9,
            "one_liner_summary": "A bracing early-Baroque programme.",
            "description": SAMPLE_DESC,
            "type": "concert",
            "venue": "La Follia Hall",
            "url": "https://example.org/baroque",
            "screenings": [
                {"date": "2026-04-22", "time": "19:30", "venue": "La Follia Hall"},
                {"date": "2026-04-24", "time": "19:30", "venue": "La Follia Hall"},
            ],
        },
        {
            "id": "in-week-mid",
            "title": "Modest Matinee",
            "rating": 5,
            "description": "<p>\u2605 <strong>Rating: 5/10</strong></p><p>Body text only.</p>",
            "type": "movie",
            "venue": "AFS",
            "url": "https://example.org/mid",
            "screenings": [{"date": "2026-04-20", "time": "14:00", "venue": "AFS"}],
        },
        {
            "id": "past-top",
            "title": "Past Masterpiece",
            "rating": 10,
            "description": "<p>Already over.</p>",
            "type": "movie",
            "screenings": [{"date": "2025-01-15", "time": "19:00"}],
        },
        {
            "id": "future-top",
            "title": "Next Month Banger",
            "rating": 10,
            "description": "<p>Too far.</p>",
            "type": "movie",
            "screenings": [{"date": "2026-06-01", "time": "19:00"}],
        },
        {
            "id": "no-screenings",
            "title": "Unscheduled",
            "rating": 9,
            "description": "<p>Nope.</p>",
            "type": "other",
        },
        {
            "id": "no-rating",
            "title": "Rating TBD",
            "description": "<p>Body.</p>",
            "type": "other",
            "screenings": [{"date": "2026-04-21", "time": "18:00"}],
        },
    ]


# ---------- ISO week helpers ---------------------------------------------------


def test_iso_week_from_date_returns_year_and_week():
    assert bwd.iso_week_from_date(MONDAY) == (WEEK_YEAR, WEEK_NO)


def test_iso_week_range_returns_monday_to_sunday():
    mon, sun = bwd.iso_week_range(WEEK_YEAR, WEEK_NO)
    assert mon == MONDAY
    assert sun == SUNDAY
    assert (sun - mon).days == 6


def test_iso_week_label_zero_pads_week():
    assert bwd.iso_week_label(2026, 4) == "2026-W04"
    assert bwd.iso_week_label(2026, 17) == "2026-W17"


def test_parse_iso_week_arg_roundtrips():
    assert bwd.parse_iso_week_arg("2026-W17") == (2026, 17)


def test_parse_iso_week_arg_rejects_bad_format():
    with pytest.raises(ValueError):
        bwd.parse_iso_week_arg("not-a-week")


# ---------- Review parsing -----------------------------------------------------


def test_parse_review_extracts_rating_line():
    review = bwd.parse_review(SAMPLE_DESC)
    assert review.rating == "8"


def test_parse_review_strips_rating_line_from_sections():
    review = bwd.parse_review(SAMPLE_DESC)
    # Rating paragraph should not appear as its own section.
    assert not any("Rating:" in s.body for s in review.sections)


def test_parse_review_collects_labelled_sections():
    review = bwd.parse_review(SAMPLE_DESC)
    labels = [s.label for s in review.sections]
    assert labels == ["Artistic Merit", "Originality"]
    assert all(s.body for s in review.sections)
    # Body should not contain the label or the leading em dash.
    first_body = review.sections[0].body
    assert "Artistic Merit" not in first_body
    assert not first_body.startswith("–")


def test_parse_review_captures_leading_emoji():
    review = bwd.parse_review(SAMPLE_DESC)
    emojis = [s.emoji for s in review.sections]
    assert emojis[0] == "\U0001F3AD"  # 🎭
    assert emojis[1] == "\u2728"  # ✨


def test_parse_review_handles_empty_input():
    review = bwd.parse_review("")
    assert review.rating is None
    assert review.sections == ()


# ---------- Pick selection -----------------------------------------------------


def test_select_picks_keeps_only_in_week_events():
    picks = bwd.select_picks(_events(), monday=MONDAY, sunday=SUNDAY)
    ids = [p.event_id for p in picks]
    assert "in-week-top" in ids
    assert "in-week-mid" in ids
    assert "no-rating" in ids
    assert "past-top" not in ids
    assert "future-top" not in ids
    assert "no-screenings" not in ids


def test_select_picks_sorts_by_rating_desc_then_date_asc():
    picks = bwd.select_picks(_events(), monday=MONDAY, sunday=SUNDAY)
    ordered = [p.event_id for p in picks]
    # 9 > 5 > (no rating → -1 placeholder)
    assert ordered[0] == "in-week-top"
    assert ordered[1] == "in-week-mid"
    assert ordered[-1] == "no-rating"


def test_select_picks_respects_limit():
    picks = bwd.select_picks(_events(), monday=MONDAY, sunday=SUNDAY, limit=1)
    assert len(picks) == 1
    assert picks[0].event_id == "in-week-top"


def test_select_picks_restricts_in_week_screenings_to_the_range():
    picks = bwd.select_picks(_events(), monday=MONDAY, sunday=SUNDAY)
    top = next(p for p in picks if p.event_id == "in-week-top")
    dates = [s.date for s in top.in_week]
    assert dates == ["2026-04-22", "2026-04-24"]


# ---------- Render contracts ---------------------------------------------------


def test_render_digest_embeds_webcal_subscription_link():
    picks = bwd.select_picks(_events(), monday=MONDAY, sunday=SUNDAY)
    html_doc = bwd.render_digest(
        picks, year=WEEK_YEAR, week=WEEK_NO, monday=MONDAY, sunday=SUNDAY
    )
    assert bwd.TOP_PICKS_WEBCAL in html_doc
    assert "webcal://" in html_doc


def test_render_digest_includes_rating_badge_with_aria_label():
    picks = bwd.select_picks(_events(), monday=MONDAY, sunday=SUNDAY)
    html_doc = bwd.render_digest(
        picks, year=WEEK_YEAR, week=WEEK_NO, monday=MONDAY, sunday=SUNDAY
    )
    assert "9 / 10" in html_doc
    assert 'aria-label="rated 9 out of 10"' in html_doc


def test_render_digest_includes_deep_link_anchor_back_to_index():
    picks = bwd.select_picks(_events(), monday=MONDAY, sunday=SUNDAY)
    html_doc = bwd.render_digest(
        picks, year=WEEK_YEAR, week=WEEK_NO, monday=MONDAY, sunday=SUNDAY
    )
    assert "../#event=in-week-top" in html_doc


def test_render_digest_renders_review_sections():
    picks = bwd.select_picks(_events(), monday=MONDAY, sunday=SUNDAY)
    html_doc = bwd.render_digest(
        picks, year=WEEK_YEAR, week=WEEK_NO, monday=MONDAY, sunday=SUNDAY
    )
    assert "weekly-review-section" in html_doc
    assert "Artistic Merit" in html_doc
    assert "Originality" in html_doc


def test_render_digest_escapes_title_html():
    evil = [
        {
            "id": "evil",
            "title": "Evil <script>alert(1)</script>",
            "rating": 7,
            "type": "other",
            "description": "<p>Body.</p>",
            "screenings": [{"date": "2026-04-21", "time": "18:00"}],
        }
    ]
    picks = bwd.select_picks(evil, monday=MONDAY, sunday=SUNDAY)
    html_doc = bwd.render_digest(
        picks, year=WEEK_YEAR, week=WEEK_NO, monday=MONDAY, sunday=SUNDAY
    )
    assert "<script>alert(1)</script>" not in html_doc
    assert "&lt;script&gt;" in html_doc


def test_render_digest_shows_empty_message_when_no_picks():
    html_doc = bwd.render_digest(
        [], year=WEEK_YEAR, week=WEEK_NO, monday=MONDAY, sunday=SUNDAY
    )
    assert "No scheduled picks" in html_doc
    # The webcal link stays visible even on an empty week.
    assert bwd.TOP_PICKS_WEBCAL in html_doc


def test_render_digest_uses_iso_week_label_in_header():
    html_doc = bwd.render_digest(
        [], year=WEEK_YEAR, week=WEEK_NO, monday=MONDAY, sunday=SUNDAY
    )
    assert "2026-W17" in html_doc


def test_render_digest_sets_utf8_and_viewport_meta():
    html_doc = bwd.render_digest(
        [], year=WEEK_YEAR, week=WEEK_NO, monday=MONDAY, sunday=SUNDAY
    )
    assert '<meta charset="utf-8">' in html_doc
    assert "viewport" in html_doc


# ---------- write_digest + main ------------------------------------------------


def test_write_digest_creates_file_named_by_iso_week(tmp_path):
    out_dir = tmp_path / "weekly"
    path, count = bwd.write_digest(
        _events(), year=WEEK_YEAR, week=WEEK_NO, out_dir=out_dir
    )
    assert path.name == "2026-W17.html"
    assert path.exists()
    assert count >= 1
    body = path.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in body
    assert "Bold Baroque Night" in body


def test_main_writes_digest_for_explicit_week(tmp_path):
    data_path = tmp_path / "data.json"
    data_path.write_text(json.dumps(_events()))
    out_dir = tmp_path / "weekly"
    exit_code = bwd.main(
        [
            "--data",
            str(data_path),
            "--out-dir",
            str(out_dir),
            "--week",
            "2026-W17",
            "--quiet",
        ]
    )
    assert exit_code == 0
    files = sorted(out_dir.glob("*.html"))
    assert [f.name for f in files] == ["2026-W17.html"]


def test_main_all_upcoming_generates_one_file_per_week(tmp_path, monkeypatch):
    data_path = tmp_path / "data.json"
    extra = _events() + [
        {
            "id": "next-week",
            "title": "Next Week Show",
            "rating": 8,
            "description": "<p>Body.</p>",
            "type": "concert",
            "venue": "Symphony Hall",
            "screenings": [{"date": "2026-04-29", "time": "19:30"}],
        }
    ]
    data_path.write_text(json.dumps(extra))
    out_dir = tmp_path / "weekly"

    # Freeze "today" so --all-upcoming sweeps deterministically.
    frozen = date(2026, 4, 20)

    class _FrozenDateTime:
        @classmethod
        def now(cls):
            class _D:
                @staticmethod
                def date():
                    return frozen
            return _D()

    monkeypatch.setattr(bwd, "datetime", _FrozenDateTime)

    exit_code = bwd.main(
        [
            "--data",
            str(data_path),
            "--out-dir",
            str(out_dir),
            "--all-upcoming",
            "--weeks-ahead",
            "8",
            "--quiet",
        ]
    )
    assert exit_code == 0
    names = sorted(f.name for f in out_dir.glob("*.html"))
    assert "2026-W17.html" in names
    assert "2026-W18.html" in names


def test_load_events_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        bwd.load_events(tmp_path / "nope.json")


def test_load_events_rejects_non_list(tmp_path):
    bad = tmp_path / "data.json"
    bad.write_text(json.dumps({"not": "a list"}))
    with pytest.raises(ValueError):
        bwd.load_events(bad)


def test_render_digest_output_is_single_html_document():
    html_doc = bwd.render_digest(
        [], year=WEEK_YEAR, week=WEEK_NO, monday=MONDAY, sunday=SUNDAY
    )
    # Exactly one opening <html and one </html>.
    assert len(re.findall(r"<html[\s>]", html_doc)) == 1
    assert html_doc.count("</html>") == 1
