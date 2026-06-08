"""Unit tests for ``scripts/build_site.py``.

Offline + fast. Build a tiny fake ``docs/`` tree in ``tmp_path``, run the
build with an empty generator list (so no real generator/network runs), and
assert that:

* the copytree seed reproduces every hand-authored file in ``out/``,
* the parity check reports zero missing files, and
* the restore pass copies back any seeded file a (fake) generator deletes,
  preserving the "nothing is lost on publish" guarantee even under drift.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_site.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("build_site", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["build_site"] = mod
    spec.loader.exec_module(mod)
    return mod


bs = _load_module()


@pytest.fixture
def fake_docs(tmp_path: Path) -> Path:
    """A minimal synthetic ``docs/`` tree: a couple of files + a subdir."""
    root = tmp_path / "docs"
    root.mkdir()
    (root / "index.html").write_text("<!doctype html><title>home</title>")
    (root / "data.json").write_text("[]")
    (root / "styles.css").write_text("body{}")
    sub = root / "variants"
    sub.mkdir()
    (sub / "v1.html").write_text("<!doctype html><title>v1</title>")
    return root


def test_seed_copies_every_file(fake_docs: Path, tmp_path: Path):
    out_dir = tmp_path / "_site"
    bs.seed_out_dir(fake_docs, out_dir)

    assert (out_dir / "index.html").read_text() == "<!doctype html><title>home</title>"
    assert (out_dir / "data.json").read_text() == "[]"
    assert (out_dir / "styles.css").read_text() == "body{}"
    assert (out_dir / "variants" / "v1.html").exists()

    assert bs._relative_file_set(fake_docs) == bs._relative_file_set(out_dir)


def test_seed_recreates_clean_out_dir(fake_docs: Path, tmp_path: Path):
    out_dir = tmp_path / "_site"
    out_dir.mkdir()
    # A stale file that should be wiped by the clean+recreate step.
    (out_dir / "stale.txt").write_text("old")

    bs.seed_out_dir(fake_docs, out_dir)

    assert not (out_dir / "stale.txt").exists()
    assert (out_dir / "index.html").exists()


def test_build_site_no_generators_has_empty_parity_gap(
    fake_docs: Path, tmp_path: Path, capsys
):
    out_dir = tmp_path / "_site"
    # Empty generator list: pure seed, no generator or network calls.
    missing = bs.build_site(out_dir, fake_docs, generators=[])

    assert missing == set()
    assert bs._relative_file_set(fake_docs) == bs._relative_file_set(out_dir)

    captured = capsys.readouterr().out
    assert "Parity gap is EMPTY" in captured
    assert "file MISSING from out/): 0" in captured


def test_restore_brings_back_files_deleted_by_a_generator(
    fake_docs: Path, tmp_path: Path, monkeypatch
):
    out_dir = tmp_path / "_site"

    # Mimic the destructive "clean stale outputs" step that real generators
    # (build_event_shells/og_cards/api_json) run under data drift: it deletes
    # a seeded file from out/. Patch run_generators so this happens regardless
    # of the script-exists check, isolating the restore-pass behaviour.
    def _fake_run_generators(out: Path, generators):
        (out / "index.html").unlink()
        return []

    monkeypatch.setattr(bs, "run_generators", _fake_run_generators)

    # Sanity: without the restore pass the file would be gone.
    missing = bs.build_site(out_dir, fake_docs, generators=[{"name": "x"}])

    # The restore pass must have copied index.html back; parity stays empty.
    assert (out_dir / "index.html").exists()
    assert missing == set()


def _write_ics(path: Path, n_vevents: int) -> None:
    """Write a minimal iCalendar file containing ``n_vevents`` VEVENTs."""
    body = b"BEGIN:VCALENDAR\r\n"
    body += b"BEGIN:VEVENT\r\nSUMMARY:x\r\nEND:VEVENT\r\n" * n_vevents
    body += b"END:VCALENDAR\r\n"
    path.write_bytes(body)


def test_assert_required_feeds_healthy(tmp_path: Path):
    out = tmp_path / "_site"
    out.mkdir()
    _write_ics(out / "calendar.ics", 5)
    _write_ics(out / "top-picks.ics", 0)  # top-picks may legitimately be empty
    assert bs.assert_required_feeds(out) == []


def test_assert_required_feeds_missing_calendar_is_a_problem(tmp_path: Path):
    out = tmp_path / "_site"
    out.mkdir()
    _write_ics(out / "top-picks.ics", 2)
    problems = bs.assert_required_feeds(out)
    assert any("calendar.ics" in p and "MISSING" in p for p in problems)


def test_assert_required_feeds_empty_calendar_is_a_problem(tmp_path: Path):
    out = tmp_path / "_site"
    out.mkdir()
    _write_ics(out / "calendar.ics", 0)  # valid iCal but zero events == dead feed
    _write_ics(out / "top-picks.ics", 0)
    problems = bs.assert_required_feeds(out)
    assert any("calendar.ics" in p and "need >= 1" in p for p in problems)


def test_main_fails_when_required_feeds_missing(tmp_path: Path, monkeypatch):
    # No generators + a missing docs dir means no .ics feeds are produced, so
    # main() must FAIL (non-zero) rather than ship a deploy without a calendar.
    monkeypatch.setattr(bs, "_generators", lambda: [])
    rc = bs.main(
        ["--out", str(tmp_path / "_site"), "--docs-dir", str(tmp_path / "nope")]
    )
    assert rc == 1
