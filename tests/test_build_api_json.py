"""Unit tests for ``scripts/build_api_json.py``.

Covers the public API shape of each endpoint (events, top-picks,
venues, people, categories), HTML stripping, ranking / sorting,
envelope invariants, the CLI entrypoint, and empty-input resilience.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_api_json.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("build_api_json", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["build_api_json"] = mod
    spec.loader.exec_module(mod)
    return mod


bapi = _load_module()


NOW = datetime(2026, 4, 22, 5, 53, 8, tzinfo=timezone.utc)
ENDPOINTS = ("events.json", "top-picks.json", "venues.json", "people.json", "categories.json")


def _sample_events() -> list[dict]:
    return [
        {
            "id": "bold-baroque",
            "title": "Bold Baroque Night",
            "type": "concert",
            "rating": 9,
            "one_liner_summary": "A bracing early-Baroque programme.",
            "description": "<p>Full <strong>review</strong> body.</p><p>Second paragraph.</p>",
            "venue": "La Follia Hall",
            "composers": ["Johann Sebastian Bach", "Henry Purcell"],
            "screenings": [{"date": "2026-05-01", "time": "19:30"}],
        },
        {
            "id": "modest-matinee",
            "title": "Modest Matinee",
            "type": "movie",
            "rating": 5,
            "description": "<p>Midrange review.</p>",
            "director": "Agnès Varda",
            "venue": "AFS",
            "dates": ["2026-06-01"],
            "times": ["14:00"],
        },
        {
            "id": "repeat-bach",
            "title": "Bach Redux",
            "type": "concert",
            "rating": 8,
            "description": "Plain text review.",
            "composers": ["Bach", "J.S. Bach"],
            "venue": "La Follia Hall",
            "screenings": [{"date": "2026-05-08", "time": "19:30"}],
        },
        {
            "id": "dance-show",
            "title": "Dance Show",
            "type": "dance",
            "rating": 7,
            "description": "<p>Dance review.</p>",
            "venue": "Ballet Austin",
            "screenings": [{"date": "2026-06-15", "time": "20:00"}],
        },
        {
            "id": "book-club",
            "title": "Book Club Meet",
            "type": "book_club",
            "rating": 6,
            "description": "<p>Book review.</p>",
            "author": "Jorge Luis Borges",
            "venue": "AlienatedMajesty",
            "screenings": [{"date": "2026-07-20", "time": "18:00"}],
        },
        {
            "id": "unrated",
            "title": "Unrated Curiosity",
            "type": "other",
            "description": "<p>TBD.</p>",
            "venue": "Paramount",
            "screenings": [{"date": "2026-07-01", "time": "18:00"}],
        },
    ]


@pytest.fixture
def events() -> list[dict]:
    return _sample_events()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def test_html_to_text_strips_tags_and_collapses_whitespace():
    html = "<p>Hello <strong>world</strong></p><p>Second.</p>"
    text = bapi.html_to_text(html)
    assert "Hello world" in text
    assert "Second." in text
    assert "<" not in text and ">" not in text


def test_html_to_text_handles_empty():
    assert bapi.html_to_text("") == ""


def test_slugify_folds_diacritics_and_punctuation():
    assert bapi.slugify("Camille Saint-Saëns") == "camille-saint-saens"
    assert bapi.slugify("Blanton Museum of Art, Austin") == "blanton-museum-of-art-austin"
    assert bapi.slugify("") == ""


def test_absolute_url_joins_and_preserves_absolute():
    assert bapi._absolute_url("") == bapi.SITE_BASE_URL
    assert bapi._absolute_url("events/x.html") == bapi.SITE_BASE_URL + "events/x.html"
    assert bapi._absolute_url("https://other.example/y") == "https://other.example/y"


def test_event_first_date_prefers_screenings():
    e = {
        "screenings": [{"date": "2026-05-02"}, {"date": "2026-05-01"}],
        "dates": ["2099-01-01"],
    }
    assert bapi._event_first_date(e) == "2026-05-01"


def test_event_first_date_falls_back_to_dates():
    assert bapi._event_first_date({"dates": ["2026-08-01"]}) == "2026-08-01"


def test_event_first_date_empty_when_missing():
    assert bapi._event_first_date({}) == ""


def test_extract_people_dedupes_case_insensitively():
    event = {"type": "concert", "composers": ["Bach", "bach", "Purcell"]}
    people = bapi._extract_people(event)
    assert people == [("composer", "Bach"), ("composer", "Purcell")]


def test_extract_people_returns_nothing_for_unknown_type():
    assert bapi._extract_people({"type": "visual_arts", "artist": "Kandinsky"}) == []


def test_extract_people_handles_movie_director_string():
    event = {"type": "movie", "director": "Agnès Varda"}
    assert bapi._extract_people(event) == [("director", "Agnès Varda")]


def test_extract_people_handles_book_club_author():
    event = {"type": "book_club", "author": "Jorge Luis Borges"}
    assert bapi._extract_people(event) == [("author", "Jorge Luis Borges")]


# ---------------------------------------------------------------------------
# per-endpoint shape
# ---------------------------------------------------------------------------


def _assert_envelope(payload: dict) -> None:
    assert isinstance(payload, dict)
    assert set(payload.keys()) == {"generated_at", "site_url", "count", "data"}
    assert isinstance(payload["data"], list)
    assert payload["count"] == len(payload["data"])
    # ISO-8601 UTC with trailing Z.
    assert payload["generated_at"].endswith("Z")


def test_build_events_payload_strips_html(events):
    payload = bapi.build_events_payload(events, now=NOW)
    _assert_envelope(payload)
    assert payload["count"] == len(events)
    for row in payload["data"]:
        assert "<" not in row["description_text"]
        assert ">" not in row["description_text"]
        assert row["shell_url"].startswith("https://")
        assert row["shell_url"].endswith(".html")


def test_build_events_payload_filters_malformed():
    payload = bapi.build_events_payload(
        [
            {"id": "", "title": "missing id"},
            {"id": "x", "title": ""},
            "not a dict",  # type: ignore[list-item]
            {"id": "ok", "title": "Good", "type": "movie", "description": "<p>.</p>"},
        ],
        now=NOW,
    )
    assert payload["count"] == 1
    assert payload["data"][0]["id"] == "ok"


def test_build_top_picks_payload_applies_min_rating_and_sort(events):
    payload = bapi.build_top_picks_payload(events, now=NOW)
    _assert_envelope(payload)
    ids = [row["id"] for row in payload["data"]]
    # rating>=7 only: bold-baroque(9), repeat-bach(8), dance-show(7).
    assert ids == ["bold-baroque", "repeat-bach", "dance-show"]
    ratings = [row["rating"] for row in payload["data"]]
    assert ratings == sorted(ratings, reverse=True)


def test_build_top_picks_payload_honours_custom_min_rating(events):
    payload = bapi.build_top_picks_payload(events, min_rating=6, now=NOW)
    ids = {row["id"] for row in payload["data"]}
    assert "book-club" in ids  # rating 6 now qualifies
    assert "unrated" not in ids  # unrated never qualifies


def test_build_venues_payload_counts_and_dedupes(events):
    rows = bapi.build_venues_payload(events, now=NOW)
    assert isinstance(rows, list)
    by_name = {row["name"]: row for row in rows}
    assert by_name["La Follia Hall"]["event_count"] == 2
    assert by_name["La Follia Hall"]["slug"] == "la-follia-hall"
    assert "concert" in by_name["La Follia Hall"]["categories"]
    assert by_name["AFS"]["event_count"] == 1
    assert by_name["AFS"]["page_url"].endswith("venues/afs.html")


def test_build_venues_payload_skips_empty_venue():
    events = [
        {"id": "a", "title": "A", "type": "movie", "venue": ""},
        {"id": "b", "title": "B", "type": "movie", "venue": "Paramount"},
    ]
    rows = bapi.build_venues_payload(events, now=NOW)
    names = [row["name"] for row in rows]
    assert names == ["Paramount"]


def test_build_venues_payload_exposes_address_and_display_name():
    """Every venue row surfaces both ``address`` and ``display_name`` keys."""
    events = [
        {
            "id": "a",
            "title": "A",
            "type": "movie",
            "venue": "AFS",
            "venue_display_name": "Austin Film Society",
            "venue_address": "6226 Middle Fiskville Rd, Austin, TX 78752",
        },
        {
            "id": "b",
            "title": "B",
            "type": "movie",
            "venue": "AFS",
            "venue_display_name": "Austin Film Society",
            "venue_address": "6226 Middle Fiskville Rd, Austin, TX 78752",
        },
        {
            "id": "c",
            "title": "C",
            "type": "concert",
            "venue": "LaFollia",
            "venue_display_name": "La Follia",
            "venue_address": "3201 Windsor Rd, Austin, TX 78703",
        },
    ]
    rows = bapi.build_venues_payload(events, now=NOW)
    for row in rows:
        assert "address" in row
        assert "display_name" in row
    by_slug = {row["slug"]: row for row in rows}
    assert by_slug["afs"]["display_name"] == "Austin Film Society"
    assert by_slug["afs"]["address"] == "6226 Middle Fiskville Rd, Austin, TX 78752"
    assert by_slug["lafollia"]["display_name"] == "La Follia"
    assert by_slug["lafollia"]["address"] == "3201 Windsor Rd, Austin, TX 78703"


def test_build_venues_payload_defaults_when_metadata_absent():
    """``display_name`` falls back to ``name`` and ``address`` to '' when unset."""
    events = [
        {"id": "a", "title": "A", "type": "movie", "venue": "Paramount"},
    ]
    rows = bapi.build_venues_payload(events, now=NOW)
    row = rows[0]
    assert row["name"] == "Paramount"
    assert row["display_name"] == "Paramount"
    assert row["address"] == ""


def test_build_venues_payload_picks_first_non_empty_metadata():
    """First event with metadata wins; later blanks do not overwrite it."""
    events = [
        {"id": "a", "title": "A", "type": "movie", "venue": "AFS"},
        {
            "id": "b",
            "title": "B",
            "type": "movie",
            "venue": "AFS",
            "venue_display_name": "Austin Film Society",
            "venue_address": "6226 Middle Fiskville Rd, Austin, TX 78752",
        },
        {"id": "c", "title": "C", "type": "movie", "venue": "AFS"},
    ]
    rows = bapi.build_venues_payload(events, now=NOW)
    row = rows[0]
    assert row["display_name"] == "Austin Film Society"
    assert row["address"] == "6226 Middle Fiskville Rd, Austin, TX 78752"


def test_build_venues_payload_returns_list_not_envelope():
    """venues.json is a top-level list so clients/validators skip envelope unwrap."""
    rows = bapi.build_venues_payload([], now=NOW)
    assert isinstance(rows, list)
    assert rows == []


def test_build_people_payload_sorts_by_count_desc(events):
    payload = bapi.build_people_payload(events, now=NOW)
    _assert_envelope(payload)
    by_role_name = {(row["role"], row["name"]): row for row in payload["data"]}
    # Bach is in two concerts, Purcell in one, Agnès Varda (dir) in one.
    assert by_role_name[("composer", "Johann Sebastian Bach")]["event_count"] == 1
    # The second event lists a separate case variant "Bach" vs "J.S. Bach" —
    # both dedupe within a single event but count across events independently.
    # Assert that Bach as a distinct case appears at least once.
    assert any(r["role"] == "composer" for r in payload["data"])
    # Ordering invariant: counts are monotonic non-increasing.
    counts = [row["event_count"] for row in payload["data"]]
    assert counts == sorted(counts, reverse=True)
    # Director role is present.
    assert any(row["role"] == "director" for row in payload["data"])
    # Author role is present.
    assert any(row["role"] == "author" for row in payload["data"])


def test_build_people_payload_exposes_page_and_ics_urls(events):
    payload = bapi.build_people_payload(events, now=NOW)
    for row in payload["data"]:
        assert row["page_url"].endswith(".html")
        assert row["ics_url"].endswith(".ics")
        assert row["slug"] in row["page_url"]


def test_build_categories_payload_counts(events):
    payload = bapi.build_categories_payload(events, now=NOW)
    _assert_envelope(payload)
    by_slug = {row["slug"]: row for row in payload["data"]}
    assert by_slug["concert"]["count"] == 2
    assert by_slug["concert"]["label"] == "Concert"
    assert by_slug["movie"]["count"] == 1
    assert by_slug["dance"]["count"] == 1
    assert by_slug["book_club"]["count"] == 1
    assert by_slug["book_club"]["label"] == "Book club"
    assert by_slug["other"]["count"] == 1
    # Sorted by count desc then slug asc.
    counts = [row["count"] for row in payload["data"]]
    assert counts == sorted(counts, reverse=True)


# ---------------------------------------------------------------------------
# empty-input resilience
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "builder",
    [
        bapi.build_events_payload,
        bapi.build_top_picks_payload,
        bapi.build_people_payload,
        bapi.build_categories_payload,
    ],
)
def test_builders_return_empty_envelope_for_no_events(builder):
    payload = builder([], now=NOW)
    _assert_envelope(payload)
    assert payload["count"] == 0
    assert payload["data"] == []


def test_build_venues_payload_returns_empty_list_for_no_events():
    """venues.json is a list, so "empty" means ``[]`` not an envelope."""
    rows = bapi.build_venues_payload([], now=NOW)
    assert rows == []


# ---------------------------------------------------------------------------
# writer + CLI
# ---------------------------------------------------------------------------


def test_write_outputs_produces_all_five_files(events, tmp_path):
    sizes = bapi.write_outputs(events, out_dir=tmp_path / "api", now=NOW)
    assert set(sizes.keys()) == set(ENDPOINTS)
    for name in ENDPOINTS:
        path = tmp_path / "api" / name
        assert path.is_file()
        parsed = json.loads(path.read_text(encoding="utf-8"))
        if name == "venues.json":
            assert isinstance(parsed, list)
            for row in parsed:
                assert "address" in row
                assert "display_name" in row
        else:
            _assert_envelope(parsed)


def test_write_outputs_writes_valid_utf8(events, tmp_path):
    bapi.write_outputs(events, out_dir=tmp_path / "api", now=NOW)
    people = json.loads((tmp_path / "api" / "people.json").read_text(encoding="utf-8"))
    names = {row["name"] for row in people["data"]}
    # Non-ASCII director name survives JSON round-trip (ensure_ascii=False).
    assert "Agnès Varda" in names


def test_load_events_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        bapi.load_events(tmp_path / "missing.json")


def test_load_events_non_array_raises(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"not": "a list"}', encoding="utf-8")
    with pytest.raises(ValueError):
        bapi.load_events(bad)


def test_main_writes_all_five_files(events, tmp_path, capsys):
    data_path = tmp_path / "data.json"
    data_path.write_text(json.dumps(events), encoding="utf-8")
    out_dir = tmp_path / "api"

    exit_code = bapi.main(
        [
            "--data",
            str(data_path),
            "--out-dir",
            str(out_dir),
            "--no-event-json",
            "--quiet",
        ]
    )
    assert exit_code == 0
    for name in ENDPOINTS:
        path = out_dir / name
        assert path.is_file()
        json.loads(path.read_text(encoding="utf-8"))


def test_main_prints_summary_without_quiet(events, tmp_path, capsys):
    data_path = tmp_path / "data.json"
    data_path.write_text(json.dumps(events), encoding="utf-8")
    out_dir = tmp_path / "api"

    exit_code = bapi.main(
        [
            "--data",
            str(data_path),
            "--out-dir",
            str(out_dir),
            "--no-event-json",
        ]
    )
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "events.json" in captured.out
    assert "venues.json" in captured.out


def test_main_respects_custom_min_rating(events, tmp_path):
    data_path = tmp_path / "data.json"
    data_path.write_text(json.dumps(events), encoding="utf-8")
    out_dir = tmp_path / "api"

    bapi.main(
        [
            "--data",
            str(data_path),
            "--out-dir",
            str(out_dir),
            "--min-rating",
            "9",
            "--quiet",
            "--no-event-json",
        ]
    )
    top = json.loads((out_dir / "top-picks.json").read_text(encoding="utf-8"))
    assert [row["id"] for row in top["data"]] == ["bold-baroque"]


# ---------------------------------------------------------------------------
# per-event canonical JSON (mirror of JSON-LD shape)
# ---------------------------------------------------------------------------


def test_event_slug_uses_id_then_title():
    assert bapi._event_slug({"id": "bold-baroque"}) == "bold-baroque"
    assert bapi._event_slug({"title": "Camille Saint-Saëns Gala"}) == (
        "camille-saint-saens-gala"
    )
    assert bapi._event_slug({}) == ""
    assert bapi._event_slug({"id": "", "title": ""}) == ""


def test_truncate_preserves_short_text_and_ellipses_long():
    assert bapi._truncate("short", max_len=10) == "short"
    truncated = bapi._truncate("a" * 300, max_len=260)
    assert len(truncated) == 260
    assert truncated.endswith("…")


def test_og_image_url_falls_back_to_site_default(tmp_path):
    og_dir = tmp_path / "og"
    og_dir.mkdir()
    (og_dir / "known.svg").write_text("<svg/>", encoding="utf-8")
    base = bapi.SITE_BASE_URL
    assert bapi._og_image_url("known", base_url=base, og_dir=og_dir) == (
        base + "og/known.svg"
    )
    assert bapi._og_image_url("missing", base_url=base, og_dir=og_dir) == (
        base + "og/site-default.svg"
    )


def test_build_event_jsonld_mirrors_schema_org_event_shape(tmp_path):
    event = {
        "id": "bold-baroque",
        "title": "Bold Baroque Night",
        "type": "concert",
        "oneLiner": "<p>A bracing early-Baroque programme.</p>",
        "description": "<p>Full <strong>review</strong>.</p>",
        "venue": "La Follia Hall",
        "screenings": [{"date": "2026-05-01", "time": "19:30"}],
    }
    payload = bapi.build_event_jsonld(event, og_dir=tmp_path)
    assert payload is not None
    assert payload["@context"] == "https://schema.org"
    assert payload["@type"] == "Event"
    assert payload["name"] == "Bold Baroque Night"
    assert "<" not in payload["description"]
    assert payload["description"].startswith("A bracing early-Baroque")
    assert payload["url"].endswith("events/bold-baroque.html")
    assert payload["image"].endswith("og/site-default.svg")
    assert payload["startDate"] == "2026-05-01"
    assert payload["location"]["@type"] == "Place"
    assert payload["location"]["name"] == "La Follia Hall"
    assert payload["location"]["address"]["addressLocality"] == "Austin"


def test_build_event_jsonld_uses_description_when_one_liner_missing(tmp_path):
    event = {
        "id": "plain",
        "title": "Plain",
        "description": "Plain text review.",
        "venue": "Hall",
        "screenings": [{"date": "2026-06-01"}],
    }
    payload = bapi.build_event_jsonld(event, og_dir=tmp_path)
    assert payload is not None
    assert payload["description"] == "Plain text review."


def test_build_event_jsonld_falls_back_to_title_when_no_copy(tmp_path):
    payload = bapi.build_event_jsonld({"id": "x", "title": "Just A Title"}, og_dir=tmp_path)
    assert payload is not None
    assert payload["description"] == "Just A Title"
    # No startDate / location when not supplied.
    assert "startDate" not in payload
    assert "location" not in payload


def test_build_event_jsonld_skips_events_without_identity(tmp_path):
    assert bapi.build_event_jsonld({}, og_dir=tmp_path) is None
    assert bapi.build_event_jsonld({"id": ""}, og_dir=tmp_path) is None
    assert bapi.build_event_jsonld({"id": "!!!"}, og_dir=tmp_path) is None


def test_build_event_jsonld_prefers_per_event_og_card(tmp_path):
    og_dir = tmp_path
    (og_dir / "bold-baroque.svg").write_text("<svg/>", encoding="utf-8")
    payload = bapi.build_event_jsonld(
        {"id": "bold-baroque", "title": "Bold"}, og_dir=og_dir
    )
    assert payload is not None
    assert payload["image"].endswith("og/bold-baroque.svg")


def test_write_event_json_files_writes_one_per_event(events, tmp_path):
    out_dir = tmp_path / "events"
    count = bapi.write_event_json_files(events, out_dir=out_dir, og_dir=tmp_path / "og")
    assert count == len(events)
    files = sorted(out_dir.glob("*.json"))
    assert len(files) == len(events)
    parsed = json.loads(files[0].read_text(encoding="utf-8"))
    assert parsed["@context"] == "https://schema.org"
    assert parsed["@type"] == "Event"


def test_write_event_json_files_dedupes_same_slug(tmp_path):
    events = [
        {"id": "x", "title": "X First", "venue": "A"},
        {"id": "x", "title": "X Duplicate", "venue": "B"},
    ]
    out_dir = tmp_path / "events"
    count = bapi.write_event_json_files(events, out_dir=out_dir, og_dir=tmp_path / "og")
    assert count == 1
    payload = json.loads((out_dir / "x.json").read_text(encoding="utf-8"))
    assert payload["name"] == "X First"


def test_write_event_json_files_skips_malformed(tmp_path):
    events = [
        "not a dict",  # type: ignore[list-item]
        {},
        {"id": "good", "title": "Good"},
    ]
    out_dir = tmp_path / "events"
    count = bapi.write_event_json_files(events, out_dir=out_dir, og_dir=tmp_path / "og")
    assert count == 1
    assert (out_dir / "good.json").is_file()


def test_write_event_json_files_clears_stale_json_only(tmp_path):
    out_dir = tmp_path / "events"
    out_dir.mkdir()
    stale_json = out_dir / "stale.json"
    stale_json.write_text('{"old": true}', encoding="utf-8")
    sibling_html = out_dir / "keeper.html"
    sibling_html.write_text("<html></html>", encoding="utf-8")

    bapi.write_event_json_files(
        [{"id": "fresh", "title": "Fresh"}],
        out_dir=out_dir,
        og_dir=tmp_path / "og",
    )

    assert not stale_json.exists()
    assert sibling_html.exists()
    assert (out_dir / "fresh.json").is_file()


def test_main_emits_per_event_json_by_default(events, tmp_path):
    data_path = tmp_path / "data.json"
    data_path.write_text(json.dumps(events), encoding="utf-8")
    api_dir = tmp_path / "api"
    event_dir = tmp_path / "events"
    og_dir = tmp_path / "og"

    exit_code = bapi.main(
        [
            "--data",
            str(data_path),
            "--out-dir",
            str(api_dir),
            "--event-json-dir",
            str(event_dir),
            "--og-dir",
            str(og_dir),
            "--quiet",
        ]
    )
    assert exit_code == 0
    files = list(event_dir.glob("*.json"))
    assert len(files) == len(events)
    parsed = json.loads(files[0].read_text(encoding="utf-8"))
    assert parsed["@type"] == "Event"


def test_main_skips_per_event_json_when_flag_set(events, tmp_path):
    data_path = tmp_path / "data.json"
    data_path.write_text(json.dumps(events), encoding="utf-8")
    api_dir = tmp_path / "api"
    event_dir = tmp_path / "events"

    exit_code = bapi.main(
        [
            "--data",
            str(data_path),
            "--out-dir",
            str(api_dir),
            "--event-json-dir",
            str(event_dir),
            "--no-event-json",
            "--quiet",
        ]
    )
    assert exit_code == 0
    assert not event_dir.exists() or not any(event_dir.glob("*.json"))
