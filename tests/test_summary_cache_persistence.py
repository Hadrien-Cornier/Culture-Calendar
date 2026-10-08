"""Daily runs retain verified hooks without reusing changed source context."""

import json
import shlex
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml

from src.summary_generator import SummaryGenerator

ROOT = Path(__file__).resolve().parents[1]
HOOK = "Kobayashi's ghost stories unfold as theatrical tableaux of color and dread."
EVENT = {
    "title": "KWAIDAN",
    "type": "screening",
    "venue": "AFS",
    "url": "https://www.austinfilm.org/screening/kwaidan/",
    "director": "Masaki Kobayashi",
    "description": "Four ghost stories staged in painted sets with expressive color. "
    * 4,
    "dates": ["2026-10-09"],
    "times": ["19:00"],
}


@pytest.fixture
def generator(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("src.summary_generator.time.sleep", lambda _: None)
    gen = SummaryGenerator.__new__(SummaryGenerator)
    gen.summary_cache = {}
    gen.provider = "openrouter"
    gen.llm_service = SimpleNamespace(_chat=Mock(return_value=HOOK))
    return gen


def publish(events):
    Path("docs").mkdir(exist_ok=True)
    Path("docs/data.json").write_text(json.dumps(events))


def test_published_hook_survives_new_dates_and_process_restart(generator):
    publish([{**EVENT, "one_liner_summary": HOOK}])
    generator._load_cache()
    later = {**EVENT, "dates": ["2026-10-11"], "times": ["16:00"]}
    assert generator.generate_summary_with_cache_info(later) == (HOOK, False)
    generator.llm_service._chat.assert_not_called()
    generator._save_cache()

    # A subsequent checkout can use the persisted cache even without data.json.
    Path("docs/data.json").rename("docs/previous-data.json")
    restarted = SummaryGenerator.__new__(SummaryGenerator)
    restarted.summary_cache = {}
    restarted.llm_service = generator.llm_service
    restarted._load_cache()
    assert restarted.generate_summary_with_cache_info(later) == (HOOK, False)
    restarted.llm_service._chat.assert_not_called()


@pytest.mark.parametrize(
    "changes",
    [
        {"description": EVENT["description"] + "A newly revised critical reading."},
        {"url": "https://www.austinfilm.org/screening/a-different-kwaidan/"},
        {"director": "A different director"},
        {"release_year": 2026},
        {"venue": "Hyperreal"},
        {"book": "A different work"},
        {"program": "A different program"},
    ],
)
def test_changed_context_requires_new_generation(generator, changes):
    publish([{**EVENT, "one_liner_summary": HOOK}])
    generator._load_cache()
    assert generator.generate_summary_with_cache_info({**EVENT, **changes}) == (
        HOOK,
        True,
    )
    generator.llm_service._chat.assert_called_once()


def test_changed_style_requires_new_generation(generator, monkeypatch):
    publish([{**EVENT, "one_liner_summary": HOOK}])
    generator._load_cache()
    monkeypatch.setattr("src.processor._style_rubric", lambda: "Changed style rubric")
    assert generator.generate_summary_with_cache_info(EVENT) == (HOOK, True)
    generator.llm_service._chat.assert_called_once()


def test_legacy_title_cache_without_source_context_is_not_reused(generator):
    Path("cache").mkdir()
    Path("cache/summary_cache.json").write_text(
        json.dumps({"KWAIDAN_screening": "A hook from an unknown source and review."})
    )
    generator._load_cache()
    assert generator.generate_summary_with_cache_info(EVENT) == (HOOK, True)
    generator.llm_service._chat.assert_called_once()


@pytest.mark.parametrize(
    "bad_hook",
    [
        "",
        "I cannot provide a meaningful summary without actual information about this film.",
    ],
)
def test_invalid_published_and_cached_hooks_require_generation(generator, bad_hook):
    publish([{**EVENT, "one_liner_summary": bad_hook}])
    generator._load_cache()
    generator.summary_cache[generator._summary_cache_key(EVENT)] = bad_hook
    assert generator.generate_summary_with_cache_info(EVENT) == (HOOK, True)
    generator.llm_service._chat.assert_called_once()


def test_missing_analysis_is_not_rescued_by_a_published_hook(generator):
    invalid = {**EVENT, "description": ""}
    publish([{**invalid, "one_liner_summary": HOOK}])
    generator._load_cache()
    with pytest.raises(RuntimeError, match="missing required AI analysis"):
        generator.generate_summary(invalid)
    generator.llm_service._chat.assert_not_called()


def test_force_refresh_still_replaces_a_published_hook(generator):
    publish([{**EVENT, "one_liner_summary": HOOK}])
    generator._load_cache()
    assert generator.generate_summary_with_cache_info(EVENT, force_regenerate=True) == (
        HOOK,
        True,
    )
    generator.llm_service._chat.assert_called_once()


def test_daily_publication_stages_summary_cache_and_excludes_other_cache(tmp_path):
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/daily-calendar-update.yml").read_text()
    )
    step = next(
        s
        for s in workflow["jobs"]["daily-update"]["steps"]
        if s["name"] == "Commit and push changes"
    )
    add_line = next(
        line.strip()
        for line in step["run"].splitlines()
        if line.strip().startswith("git add ")
    )
    files = {
        "docs/data.json": "[]",
        "docs/source_update_times.json": "{}",
        "docs/weekly/week.json": "[]",
        "cache/summary_cache.json": json.dumps({"v2:context": HOOK}),
        "cache/llm_cache.json": "{}",
        "unrelated.txt": "unrelated local work",
    }
    for name, contents in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents)
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    subprocess.run(shlex.split(add_line), cwd=tmp_path, check=True)
    staged = subprocess.check_output(
        ["git", "diff", "--cached", "--name-only"], cwd=tmp_path, text=True
    ).splitlines()
    assert set(staged) == set(files) - {"cache/llm_cache.json", "unrelated.txt"}
