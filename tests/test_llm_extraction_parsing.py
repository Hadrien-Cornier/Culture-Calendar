"""Tests for parsing an LLM extraction response into structured data.

Every shape here was observed in a live gallery scrape. Each one used to cost
the entire page: the parser sliced from the first "{" to the *last* "}", so a
closing remark after the JSON produced "Extra data", and a response clipped by
the token budget produced "Expecting ',' delimiter" - in both cases returning
zero events for a page that had plenty.
"""

from __future__ import annotations

import pytest

from src.llm_service import LLMService

SCHEMA = {"events": {"type": "array", "items": {}}}


@pytest.fixture
def service() -> LLMService:
    """An LLMService with no network wiring - only the parser is under test."""
    return LLMService.__new__(LLMService)


def _events(result: dict) -> list:
    data = result.get("data")
    return data.get("events", []) if isinstance(data, dict) else []


@pytest.mark.unit
class TestWellFormedResponses:
    def test_clean_json(self, service):
        result = service._parse_extraction_response(
            '{"events": [{"title": "A", "dates": ["2026-08-14"]}]}', SCHEMA
        )
        assert result["success"] is True
        assert _events(result)[0]["title"] == "A"

    def test_fenced_json(self, service):
        result = service._parse_extraction_response(
            '```json\n{"events": [{"title": "A"}]}\n```', SCHEMA
        )
        assert result["success"] is True
        assert len(_events(result)) == 1


@pytest.mark.unit
class TestTrailingContent:
    """raw_decode reads one value and ignores whatever follows."""

    def test_prose_after_the_json(self, service):
        result = service._parse_extraction_response(
            '{"events": [{"title": "A"}]}\n\nNote: only one show is listed.', SCHEMA
        )
        assert result["success"] is True
        assert len(_events(result)) == 1

    def test_second_object_after_the_json(self, service):
        result = service._parse_extraction_response(
            '{"events": [{"title": "A"}]}\n{"note": "extra"}', SCHEMA
        )
        assert result["success"] is True
        assert len(_events(result)) == 1


@pytest.mark.unit
class TestTruncatedResponses:
    """A clipped response should cost the clipped entry, not the whole page."""

    def test_recovers_entries_before_a_mid_object_cut(self, service):
        result = service._parse_extraction_response(
            '{"events": [{"title": "A", "dates": ["2026-08-14"]}, {"title": "B", "dat',
            SCHEMA,
        )
        assert result["success"] is True
        assert result["truncated"] is True
        assert [e["title"] for e in _events(result)] == ["A"]

    def test_recovers_entries_before_a_mid_string_cut(self, service):
        result = service._parse_extraction_response(
            '{"events": [{"title": "A"}, {"title": "B has a very long titl', SCHEMA
        )
        assert result["success"] is True
        assert [e["title"] for e in _events(result)] == ["A"]

    def test_keeps_many_complete_entries(self, service):
        entries = ", ".join(f'{{"title": "E{i}"}}' for i in range(12))
        result = service._parse_extraction_response(
            '{"events": [' + entries + ', {"title": "clip', SCHEMA
        )
        assert len(_events(result)) == 12


@pytest.mark.unit
class TestUnparseableResponses:
    def test_no_json_at_all(self, service):
        result = service._parse_extraction_response(
            "I could not find any events on this page.", SCHEMA
        )
        assert result["success"] is False
        assert "No valid JSON" in result["error"]

    def test_empty_response(self, service):
        result = service._parse_extraction_response("", SCHEMA)
        assert result["success"] is False

    def test_opening_brace_with_nothing_usable(self, service):
        result = service._parse_extraction_response("{ this is not json", SCHEMA)
        assert result["success"] is False


@pytest.mark.unit
class TestSalvageHelper:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ('{"a": {"b": 1}, "c": ', {"a": {"b": 1}}),
            ('{"events": [{"t": "x"}, {"t": "y"}, {"t": ', {"events": [{"t": "x"}, {"t": "y"}]}),
        ],
    )
    def test_closes_open_containers(self, raw, expected):
        assert LLMService._salvage_truncated_json(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "{",
            '{"a": "unterminated',
            # Nothing has closed yet, so there is no known-good boundary to cut
            # at. Real extraction responses are arrays of objects, which close
            # one per entry, so this shape does not occur in practice.
            '{"a": [1, 2',
        ],
    )
    def test_returns_none_when_nothing_completed(self, raw):
        assert LLMService._salvage_truncated_json(raw) is None

    def test_ignores_braces_inside_strings(self):
        """A '}' in a description must not be read as a container close."""
        salvaged = LLMService._salvage_truncated_json(
            '{"events": [{"title": "Set }{ Theory"}, {"title": "cut'
        )
        assert salvaged == {"events": [{"title": "Set }{ Theory"}]}
