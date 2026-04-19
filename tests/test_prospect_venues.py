"""Unit tests for scripts.prospect_venues."""
from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "prospect_venues.py"


def _load_module():
    """Dynamically load scripts/prospect_venues.py as an importable module."""
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    spec = importlib.util.spec_from_file_location("prospect_venues", _SCRIPT_PATH)
    assert spec and spec.loader, "Failed to create module spec for prospect_venues.py"
    module = importlib.util.module_from_spec(spec)
    sys.modules["prospect_venues"] = module
    spec.loader.exec_module(module)
    return module


prospect_venues = _load_module()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_config(tmp_path: Path, venue_entries: dict[str, dict[str, Any]]) -> Path:
    """Write a minimal master_config-shaped YAML for load_existing_venues."""
    import yaml

    config_path = tmp_path / "master_config.yaml"
    config_path.write_text(yaml.safe_dump({"venues": venue_entries}))
    return config_path


class _StubLLM:
    """Mocked LLMService.call_perplexity used in place of the real thing."""

    def __init__(self, response: Any):
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def call_perplexity(self, prompt: str, temperature: float = 0.2, **kwargs: Any):
        self.calls.append({"prompt": prompt, "temperature": temperature, **kwargs})
        return self.response


# ---------------------------------------------------------------------------
# build_prompt
# ---------------------------------------------------------------------------


def test_build_prompt_lists_existing_venues_and_category():
    prompt = prospect_venues.build_prompt(
        category="visual_arts",
        existing_venues=["Austin Film Society", "NowPlayingAustin — Visual Arts"],
    )
    assert "visual_arts" in prompt
    assert "Austin Film Society" in prompt
    assert "NowPlayingAustin" in prompt
    assert "JSON" in prompt


def test_build_prompt_handles_empty_existing_venues():
    prompt = prospect_venues.build_prompt(category="concert", existing_venues=[])
    assert "(none)" in prompt


# ---------------------------------------------------------------------------
# load_existing_venues
# ---------------------------------------------------------------------------


def test_load_existing_venues_reads_display_names(tmp_path: Path):
    config_path = _write_config(
        tmp_path,
        {
            "afs": {"display_name": "Austin Film Society"},
            "hyperreal": {"display_name": "Hyperreal"},
            "bare": {},  # falls back to key when no display_name
        },
    )
    names = prospect_venues.load_existing_venues(config_path)
    assert "Austin Film Society" in names
    assert "Hyperreal" in names
    assert "bare" in names


# ---------------------------------------------------------------------------
# _coerce_candidates + _parse_json_loose
# ---------------------------------------------------------------------------


def test_coerce_candidates_from_dict_with_candidates_key():
    payload = {
        "candidates": [
            {"name": "Blanton Museum", "url": "https://blanton.org", "sample_event": "x", "why_relevant": "y"},
        ]
    }
    out = prospect_venues._coerce_candidates(payload)
    assert len(out) == 1
    assert out[0]["name"] == "Blanton Museum"


def test_coerce_candidates_from_list():
    payload = [{"name": "Foo", "url": "https://foo", "sample_event": "", "why_relevant": ""}]
    out = prospect_venues._coerce_candidates(payload)
    assert out[0]["name"] == "Foo"


def test_coerce_candidates_from_fenced_json_string():
    raw = """```json
    {"candidates": [{"name": "Mexic-Arte Museum", "url": "https://mexic-artemuseum.org", "sample_event": "Dia de los Muertos", "why_relevant": "visual arts focus"}]}
    ```"""
    out = prospect_venues._coerce_candidates(raw)
    assert len(out) == 1
    assert out[0]["name"] == "Mexic-Arte Museum"
    assert out[0]["url"].startswith("https://")


def test_coerce_candidates_returns_empty_on_garbage():
    assert prospect_venues._coerce_candidates(None) == []
    assert prospect_venues._coerce_candidates("not json at all") == []
    assert prospect_venues._coerce_candidates({"unrelated": 1}) == []


# ---------------------------------------------------------------------------
# dedupe_candidates — case-insensitive match against existing venues
# ---------------------------------------------------------------------------


def test_dedupe_drops_case_insensitive_matches_with_existing_venues():
    candidates = [
        {"name": "Austin Film Society", "url": "x", "sample_event": "", "why_relevant": ""},
        {"name": "BLANTON MUSEUM OF ART", "url": "x", "sample_event": "", "why_relevant": ""},
    ]
    existing = ["austin film society", "Some Other Venue"]
    out = prospect_venues.dedupe_candidates(candidates, existing)
    assert [c["name"] for c in out] == ["BLANTON MUSEUM OF ART"]


def test_dedupe_drops_duplicates_within_candidates_list():
    candidates = [
        {"name": "Mexic-Arte", "url": "a", "sample_event": "", "why_relevant": ""},
        {"name": "mexic-arte", "url": "b", "sample_event": "", "why_relevant": ""},
    ]
    out = prospect_venues.dedupe_candidates(candidates, [])
    assert len(out) == 1
    assert out[0]["url"] == "a"  # first-seen wins


def test_dedupe_drops_unnamed_candidates():
    candidates = [
        {"name": "", "url": "x", "sample_event": "", "why_relevant": ""},
        {"name": "   ", "url": "y", "sample_event": "", "why_relevant": ""},
    ]
    assert prospect_venues.dedupe_candidates(candidates, []) == []


# ---------------------------------------------------------------------------
# format_section + append_section
# ---------------------------------------------------------------------------


def test_format_section_renders_header_and_checklist_lines():
    now = datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc)
    section = prospect_venues.format_section(
        candidates=[
            {
                "name": "Blanton Museum",
                "url": "https://blanton.org",
                "sample_event": "Ruth Asawa",
                "why_relevant": "Major visual arts venue",
            }
        ],
        category="visual_arts",
        now=now,
    )
    assert "## Prospecting run: 2026-04-18T12:00:00+00:00 — category visual_arts" in section
    assert "- [ ] Blanton Museum (visual_arts) — Major visual arts venue — https://blanton.org" in section


def test_format_section_empty_candidates_still_writes_header():
    now = datetime(2026, 4, 18, tzinfo=timezone.utc)
    section = prospect_venues.format_section([], "concert", now)
    assert "## Prospecting run:" in section
    assert "no new candidates" in section


def test_append_section_is_append_only_not_overwrite(tmp_path: Path):
    out_path = tmp_path / "prospects" / "visual_arts.md"
    prospect_venues.append_section(out_path, "## First run\n- [ ] A — why — url\n")
    prospect_venues.append_section(out_path, "## Second run\n- [ ] B — why — url\n")
    body = out_path.read_text()
    assert "## First run" in body
    assert "## Second run" in body
    # Second section must come after the first in the file.
    assert body.index("## First run") < body.index("## Second run")


# ---------------------------------------------------------------------------
# run() — end-to-end with mocked LLMService
# ---------------------------------------------------------------------------


def test_run_writes_markdown_and_dedupes_against_existing(tmp_path: Path):
    config_path = _write_config(
        tmp_path,
        {
            "afs": {"display_name": "Austin Film Society"},
            "blanton": {"display_name": "Blanton Museum"},
        },
    )
    llm = _StubLLM(
        response={
            "candidates": [
                # dedup: matches existing "Blanton Museum" case-insensitively
                {"name": "blanton museum", "url": "x", "sample_event": "", "why_relevant": "skip me"},
                {
                    "name": "Mexic-Arte Museum",
                    "url": "https://mexic-artemuseum.org",
                    "sample_event": "Dia de los Muertos",
                    "why_relevant": "Contemporary Latino visual arts",
                },
            ]
        }
    )
    out_path = tmp_path / "out" / "visual_arts.md"
    now = datetime(2026, 4, 18, 9, 30, tzinfo=timezone.utc)

    survivors = prospect_venues.run(
        category="visual_arts",
        out_path=out_path,
        config_path=config_path,
        llm=llm,
        now=now,
    )

    assert len(survivors) == 1
    assert survivors[0]["name"] == "Mexic-Arte Museum"

    body = out_path.read_text()
    assert "## Prospecting run: 2026-04-18T09:30:00+00:00 — category visual_arts" in body
    assert "- [ ] Mexic-Arte Museum (visual_arts)" in body
    assert "blanton" not in body.lower()  # dedup stripped it

    # Exactly one Perplexity call, with the prompt built against existing venues.
    assert len(llm.calls) == 1
    assert "Austin Film Society" in llm.calls[0]["prompt"]
    assert "Blanton Museum" in llm.calls[0]["prompt"]


def test_run_is_append_not_overwrite_on_second_invocation(tmp_path: Path):
    config_path = _write_config(tmp_path, {"afs": {"display_name": "Austin Film Society"}})
    out_path = tmp_path / "prospects.md"

    llm_first = _StubLLM(
        response={
            "candidates": [
                {"name": "First Venue", "url": "https://a", "sample_event": "", "why_relevant": "r1"},
            ]
        }
    )
    llm_second = _StubLLM(
        response={
            "candidates": [
                {"name": "Second Venue", "url": "https://b", "sample_event": "", "why_relevant": "r2"},
            ]
        }
    )

    prospect_venues.run(
        category="concert",
        out_path=out_path,
        config_path=config_path,
        llm=llm_first,
        now=datetime(2026, 4, 18, 9, 0, tzinfo=timezone.utc),
    )
    prospect_venues.run(
        category="concert",
        out_path=out_path,
        config_path=config_path,
        llm=llm_second,
        now=datetime(2026, 4, 18, 10, 0, tzinfo=timezone.utc),
    )

    body = out_path.read_text()
    assert "First Venue" in body
    assert "Second Venue" in body
    # Two distinct run headers, in order.
    first_header = "## Prospecting run: 2026-04-18T09:00:00+00:00"
    second_header = "## Prospecting run: 2026-04-18T10:00:00+00:00"
    assert first_header in body and second_header in body
    assert body.index(first_header) < body.index(second_header)


def test_run_handles_llm_returning_none(tmp_path: Path):
    config_path = _write_config(tmp_path, {"afs": {"display_name": "Austin Film Society"}})
    out_path = tmp_path / "out.md"
    llm = _StubLLM(response=None)

    survivors = prospect_venues.run(
        category="book_club",
        out_path=out_path,
        config_path=config_path,
        llm=llm,
        now=datetime(2026, 4, 18, tzinfo=timezone.utc),
    )
    assert survivors == []
    assert "no new candidates" in out_path.read_text()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_parse_args_rejects_unknown_category():
    with pytest.raises(SystemExit):
        prospect_venues.parse_args(["--category", "sports"])


def test_parse_args_accepts_supported_category():
    args = prospect_venues.parse_args(["--category", "visual_arts"])
    assert args.category == "visual_arts"
    assert args.out is None


def test_default_out_path_has_category_and_date():
    path = prospect_venues.default_out_path(
        "visual_arts", datetime(2026, 4, 18, tzinfo=timezone.utc)
    )
    assert path.name == "visual_arts-2026-04-18.md"
    assert path.parent == prospect_venues.DEFAULT_OUT_DIR


def test_main_invokes_run_with_parsed_args(monkeypatch, tmp_path: Path):
    config_path = _write_config(tmp_path, {"afs": {"display_name": "Austin Film Society"}})
    out_path = tmp_path / "out.md"

    captured: dict[str, Any] = {}

    def fake_run(**kwargs: Any) -> list[dict[str, str]]:
        captured.update(kwargs)
        return [{"name": "X", "url": "y", "sample_event": "", "why_relevant": ""}]

    monkeypatch.setattr(prospect_venues, "run", fake_run)

    exit_code = prospect_venues.main(
        [
            "--category",
            "concert",
            "--out",
            str(out_path),
            "--config",
            str(config_path),
        ]
    )
    assert exit_code == 0
    assert captured["category"] == "concert"
    assert captured["out_path"] == out_path
    assert captured["config_path"] == config_path
