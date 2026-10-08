"""The daily update must recover real summaries from empty reasoning responses."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.summary_generator import SummaryGenerator

HOOK = "Kobayashi's ghost stories unfold as theatrical tableaux of color and dread."
EVENT = {
    "title": "KWAIDAN",
    "type": "screening",
    "venue": "AFS",
    "director": "Masaki Kobayashi",
    "description": "Four ghost stories staged in painted sets with expressive color and sound. "
    * 4,
    "dates": ["2026-10-09", "2026-10-10"],
    "times": ["19:00", "16:00"],
    "url": "https://www.austinfilm.org/films/kwaidan/",
}


def completion(text, finish="stop"):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content=text), finish_reason=finish)
        ]
    )


@pytest.fixture
def generator(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic")
    monkeypatch.setattr(SummaryGenerator, "_load_cache", lambda self: None)
    monkeypatch.setattr(SummaryGenerator, "_save_cache", lambda self: None)
    monkeypatch.setattr("src.summary_generator.time.sleep", lambda _: None)
    gen = SummaryGenerator()
    gen.llm_service.openai = Mock()
    gen.llm_service.anthropic = Mock()
    gen.llm_service.anthropic.messages.create.return_value = SimpleNamespace(
        content=[SimpleNamespace(text=HOOK)]
    )
    return gen


def test_summary_retries_reasoning_budget_and_caches_real_text(generator):
    call = generator.llm_service.openai.chat.completions.create
    call.side_effect = [completion(None, "length"), completion(HOOK)]

    assert generator.generate_summary_with_cache_info(EVENT) == (HOOK, True)
    assert generator.generate_summary_with_cache_info(EVENT) == (HOOK, False)
    assert [c.kwargs["max_tokens"] for c in call.call_args_list] == [2000, 8000]
    assert EVENT["description"] in call.call_args.kwargs["messages"][1]["content"]
    generator.llm_service.anthropic.messages.create.assert_not_called()


@pytest.mark.parametrize("failure", ["empty", "error"])
def test_summary_falls_back_with_same_source_context(generator, failure):
    call = generator.llm_service.openai.chat.completions.create
    if failure == "error":
        call.side_effect = OSError("provider unavailable")
    else:
        call.return_value = completion(None, "length")

    assert generator.generate_summary(EVENT) == HOOK
    primary = call.call_args.kwargs
    fallback = generator.llm_service.anthropic.messages.create.call_args.kwargs
    assert fallback["messages"][0]["content"] == primary["messages"][1]["content"]
    assert fallback["system"] == primary["messages"][0]["content"]


def test_summary_all_providers_fail_leaves_gap_without_fabrication(generator):
    generator.llm_service.openai.chat.completions.create.return_value = completion(None)
    generator.llm_service.anthropic.messages.create.side_effect = OSError("unavailable")
    assert generator.generate_summary(EVENT) is None
    assert generator.summary_cache == {}


def test_summary_refusal_is_not_cached(generator):
    generator.llm_service.openai.chat.completions.create.return_value = completion(
        "I cannot provide a meaningful summary without actual information about this film."
    )
    assert generator.generate_summary(EVENT) is None
    assert generator.summary_cache == {}


def test_summary_missing_movie_analysis_remains_hard_error(generator):
    event = {**EVENT, "description": ""}
    with pytest.raises(RuntimeError, match="missing required AI analysis"):
        generator.generate_summary(event)
    generator.llm_service.openai.chat.completions.create.assert_not_called()


def test_processor_preserves_events_and_screenings_during_summary_failover(generator):
    from src.processor import EventProcessor
    from update_website_data import generate_website_data

    processor = EventProcessor.__new__(EventProcessor)
    processor.movie_cache = {
        EVENT["title"]: {"score": 8, "summary": EVENT["description"]}
    }
    processor.force_reprocess = False
    processor.reprocessed_titles = set()
    processor.summary_generator = generator
    generator.llm_service.openai.chat.completions.create.return_value = completion(
        None, "length"
    )
    original = deepcopy(EVENT)
    processed = processor.process_events([deepcopy(EVENT)])

    assert len(processed) == 1
    assert processed[0]["oneLinerSummary"] == HOOK
    for key in ("title", "dates", "times", "url", "venue"):
        assert processed[0][key] == original[key]
    data = generate_website_data(processed)
    assert data[0]["one_liner_summary"] == HOOK
    assert len(data[0]["screenings"]) == 2
