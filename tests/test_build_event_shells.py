"""Tests for ``scripts/build_event_shells.py``.

Covers: slug hygiene, per-event OG metadata, JSON-LD ``Event`` schema,
canonical URLs, link-unfurl bot compatibility (meta fetched before JS
redirect fires), and deduplication.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_event_shells.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("build_event_shells", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


bes = _load_module()


def _event(**overrides) -> dict:
    base = {
        "id": "test-movie",
        "title": "Test Movie",
        "rating": 9,
        "oneLiner": "A stirring test of cinematic rigour.",
        "description": "<p>A long-form <strong>description</strong> with HTML tags.</p>",
        "venue": "Paramount Theatre",
        "type": "movie",
        "screenings": [{"date": "2026-05-01", "time": "19:30"}],
    }
    base.update(overrides)
    return base


class TestSlugify:
    def test_strips_diacritics(self):
        assert bes._slugify("Camille Saint-Saëns") == "camille-saint-saens"

    def test_lowercases_and_hyphenates(self):
        assert bes._slugify("8 1/2") == "8-1-2"

    def test_strips_apostrophes(self):
        assert bes._slugify("Don't Look Back") == "don-t-look-back"

    def test_empty_returns_fallback(self):
        assert bes._slugify("") == "event"
        assert bes._slugify(None or "") == "event"

    def test_only_symbols_returns_fallback(self):
        assert bes._slugify("!!!") == "event"


class TestShellBuild:
    def test_shell_from_event_produces_canonical_and_anchor(self):
        shell = bes._shell_from_event(_event())
        assert shell is not None
        assert shell.canonical_url.endswith("/events/test-movie.html")
        assert shell.anchor_url.endswith("/#event=test-movie")

    def test_shell_uses_per_event_og_card_when_present(self, tmp_path, monkeypatch):
        # Simulate an existing SVG card alongside the output dir
        out_dir = tmp_path / "events"
        og_dir = tmp_path / "og"
        og_dir.mkdir()
        (og_dir / "test-movie.svg").write_text("<svg/>")
        monkeypatch.setattr(bes, "OUT_DIR", out_dir)
        shell = bes._shell_from_event(_event())
        assert shell.og_image.endswith("/og/test-movie.svg")

    def test_shell_falls_back_to_site_default_when_no_card(self, tmp_path, monkeypatch):
        out_dir = tmp_path / "events"
        monkeypatch.setattr(bes, "OUT_DIR", out_dir)
        shell = bes._shell_from_event(_event())
        assert shell.og_image.endswith("/og/site-default.svg")

    def test_rating_non_int_is_none(self):
        shell = bes._shell_from_event(_event(rating="not-a-number"))
        assert shell.rating is None

    def test_missing_title_still_builds_from_id(self):
        shell = bes._shell_from_event(_event(title=None))
        assert shell is not None
        assert shell.title  # non-empty fallback

    def test_no_id_or_title_returns_none(self):
        shell = bes._shell_from_event({"id": "", "title": ""})
        assert shell is None


class TestRenderHtml:
    def test_meta_tags_before_redirect_script(self):
        shell = bes._shell_from_event(_event())
        html = bes.render_shell_html(shell)
        og_idx = html.find('property="og:title"')
        redirect_idx = html.find("window.location.replace")
        assert og_idx > 0 and redirect_idx > 0
        assert og_idx < redirect_idx, "OG meta must precede JS redirect so bots see it"

    def test_json_ld_present_and_valid_json(self):
        shell = bes._shell_from_event(_event())
        html = bes.render_shell_html(shell)
        match = re.search(
            r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL
        )
        assert match is not None
        payload = json.loads(match.group(1))
        assert payload["@type"] == "Event"
        assert payload["name"] == "Test Movie"
        assert payload["startDate"] == "2026-05-01"
        assert payload["location"]["name"] == "Paramount Theatre"

    def test_twitter_card_summary_large_image(self):
        shell = bes._shell_from_event(_event())
        html = bes.render_shell_html(shell)
        assert 'name="twitter:card" content="summary_large_image"' in html

    def test_canonical_link_present(self):
        shell = bes._shell_from_event(_event())
        html = bes.render_shell_html(shell)
        assert 'rel="canonical"' in html

    def test_description_plain_text_strips_html(self):
        shell = bes._shell_from_event(_event())
        assert "<strong>" not in shell.description_plain
        assert "description" in shell.description_plain

    def test_html_body_escapes_unsafe_title(self):
        """Title in the visible <h1> must be HTML-escaped."""
        shell = bes._shell_from_event(
            _event(title='<script>alert("xss")</script>', id="xss-test")
        )
        html = bes.render_shell_html(shell)
        # The visible <h1> must contain the escaped form, not a raw script tag.
        assert "<h1>&lt;script&gt;alert" in html

    def test_json_ld_escapes_closing_script(self):
        """A hostile ``</script>`` inside a JSON-LD string must not terminate the block."""
        shell = bes._shell_from_event(
            _event(title='X</script><img src=x onerror=alert(1)>', id="json-xss")
        )
        html = bes.render_shell_html(shell)
        match = re.search(
            r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL
        )
        assert match is not None
        # Any </ inside the JSON payload must be backslash-escaped.
        assert "</script>" not in match.group(1)
        # Outside the JSON-LD block, an injected ``<img`` tag must have been
        # HTML-escaped — never appear as a live element opener.
        outside_jsonld = html.replace(match.group(0), "")
        assert "<img src" not in outside_jsonld


class TestBuildAll:
    def test_deduplicates_by_slug(self):
        events = [_event(id="same-slug", title="A"), _event(id="same-slug", title="B")]
        shells = bes.build_shells(events)
        assert len(shells) == 1

    def test_writes_one_file_per_shell(self, tmp_path):
        events = [_event(id=f"event-{i}") for i in range(3)]
        shells = bes.build_shells(events)
        count = bes.write_shells(shells, out_dir=tmp_path)
        assert count == 3
        assert len(list(tmp_path.glob("*.html"))) == 3
        assert (tmp_path / ".gitkeep").exists()

    def test_write_clears_stale_shells(self, tmp_path):
        (tmp_path / "old-event.html").write_text("<html>stale</html>")
        events = [_event(id="new-event")]
        shells = bes.build_shells(events)
        bes.write_shells(shells, out_dir=tmp_path)
        assert not (tmp_path / "old-event.html").exists()
        assert (tmp_path / "new-event.html").exists()
