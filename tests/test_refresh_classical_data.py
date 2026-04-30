"""Unit tests for scripts.refresh_classical_data (task 3.1a skeleton)."""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest


_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "refresh_classical_data.py"


def _load_module():
    """Dynamically load scripts/refresh_classical_data.py as an importable module."""
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    spec = importlib.util.spec_from_file_location("refresh_classical_data", _SCRIPT_PATH)
    assert spec and spec.loader, "Failed to create module spec for refresh_classical_data.py"
    module = importlib.util.module_from_spec(spec)
    sys.modules["refresh_classical_data"] = module
    spec.loader.exec_module(module)
    return module


refresh = _load_module()


# ---------------------------------------------------------------------------
# validate_event
# ---------------------------------------------------------------------------


def _good_event(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "title": "Sample Concert",
        "program": "Beethoven Symphony No. 9",
        "dates": ["2025-09-12", "2025-09-13"],
        "times": ["8:00 PM", "8:00 PM"],
        "venue_name": "Dell Hall",
        "series": "Masterworks",
        "featured_artist": "Joshua Bell (violin)",
        "composers": ["Ludwig van Beethoven"],
        "works": ["Symphony No. 9 in D Minor"],
        "type": "concert",
    }
    base.update(overrides)
    return base


def test_validate_event_accepts_well_formed_concert():
    assert refresh.validate_event(_good_event(), venue_key="austinSymphony[0]") == []


def test_validate_event_accepts_opera_and_dance_types():
    assert refresh.validate_event(_good_event(type="opera")) == []
    assert refresh.validate_event(_good_event(type="dance")) == []


def test_validate_event_rejects_unknown_type():
    errs = refresh.validate_event(_good_event(type="film"))
    assert any("'type'" in e for e in errs)


def test_validate_event_rejects_missing_required_fields():
    bad = _good_event()
    bad.pop("title")
    bad.pop("dates")
    errs = refresh.validate_event(bad, venue_key="austinSymphony[0]")
    joined = "\n".join(errs)
    assert "missing required field 'title'" in joined
    assert "missing required field 'dates'" in joined


def test_validate_event_rejects_bad_date_format():
    errs = refresh.validate_event(_good_event(dates=["09/12/2025"], times=["8:00 PM"]))
    assert any("YYYY-MM-DD" in e for e in errs)


def test_validate_event_rejects_dates_times_length_mismatch():
    errs = refresh.validate_event(
        _good_event(dates=["2025-09-12", "2025-09-13"], times=["8:00 PM"])
    )
    assert any("pairwise zip" in e for e in errs)


def test_validate_event_rejects_empty_title():
    errs = refresh.validate_event(_good_event(title="   "))
    assert any("'title'" in e and "non-empty" in e for e in errs)


def test_validate_event_rejects_non_list_composers():
    errs = refresh.validate_event(_good_event(composers="Beethoven"))
    assert any("'composers'" in e for e in errs)


def test_validate_event_rejects_non_dict_input():
    errs = refresh.validate_event("not an event", venue_key="austinSymphony[0]")
    assert errs and "not a JSON object" in errs[0]


def test_validate_event_rejects_empty_dates_or_times():
    errs = refresh.validate_event(_good_event(dates=[], times=[]))
    joined = "\n".join(errs)
    assert "'dates' must be a non-empty list" in joined
    assert "'times' must be a non-empty list" in joined


# ---------------------------------------------------------------------------
# validate_classical_data — full payload
# ---------------------------------------------------------------------------


def _good_classical_payload() -> dict[str, Any]:
    return {
        "austinSymphony": [_good_event()],
        "earlyMusicAustin": [_good_event(title="Early Music Recital")],
        "laFolliaAustin": [_good_event(title="La Follia Concert")],
        "austinChamberMusic": [_good_event(title="Chamber Music Series")],
        "austinOpera": [_good_event(title="Opera Production", type="opera")],
        "lastUpdated": "2026-04-30T16:00:00+00:00",
        "season": "2025-26",
    }


def test_validate_classical_data_accepts_full_payload():
    assert refresh.validate_classical_data(_good_classical_payload()) == []


def test_validate_classical_data_rejects_missing_venue_key():
    payload = _good_classical_payload()
    del payload["austinOpera"]
    errs = refresh.validate_classical_data(payload)
    assert any("missing venue key 'austinOpera'" in e for e in errs)


def test_validate_classical_data_rejects_non_list_venue_value():
    payload = _good_classical_payload()
    payload["austinSymphony"] = {"oops": "not a list"}
    errs = refresh.validate_classical_data(payload)
    assert any("austinSymphony" in e and "list" in e for e in errs)


def test_validate_classical_data_rejects_non_dict_payload():
    errs = refresh.validate_classical_data(["not", "a", "dict"])
    assert errs and "not a JSON object" in errs[0]


def test_validate_classical_data_propagates_event_errors_with_venue_index():
    payload = _good_classical_payload()
    payload["austinSymphony"][0].pop("title")
    errs = refresh.validate_classical_data(payload)
    assert any("austinSymphony[0]" in e and "title" in e for e in errs)


def test_validate_classical_data_rejects_non_string_lastupdated():
    payload = _good_classical_payload()
    payload["lastUpdated"] = 12345
    errs = refresh.validate_classical_data(payload)
    assert any("lastUpdated" in e for e in errs)


def test_validate_classical_data_accepts_subset_of_keys_when_requested():
    payload = {"austinSymphony": [_good_event()]}
    assert refresh.validate_classical_data(
        payload, expected_venue_keys=["austinSymphony"]
    ) == []


# ---------------------------------------------------------------------------
# stub_fetch + refresh_venues
# ---------------------------------------------------------------------------


def test_stub_fetch_returns_one_valid_event_per_venue():
    for key in refresh.ALL_VENUE_KEYS:
        events = refresh.stub_fetch(key)
        assert isinstance(events, list) and len(events) == 1
        errs = refresh.validate_event(events[0], venue_key=key)
        assert errs == [], f"stub for {key} failed validation: {errs}"


def test_stub_fetch_uses_dance_type_for_ballet():
    [event] = refresh.stub_fetch("balletAustin")
    assert event["type"] == "dance"


def test_stub_fetch_uses_opera_type_for_opera():
    [event] = refresh.stub_fetch("austinOpera")
    assert event["type"] == "opera"


def test_refresh_venues_invokes_fetcher_per_key():
    seen: list[str] = []

    def fetcher(key: str) -> list[dict[str, Any]]:
        seen.append(key)
        return [_good_event(title=f"{key} Event")]

    results = refresh.refresh_venues(
        ["austinSymphony", "austinOpera"], fetcher=fetcher, source_label="test"
    )
    assert seen == ["austinSymphony", "austinOpera"]
    assert [r.venue_key for r in results] == ["austinSymphony", "austinOpera"]
    assert all(r.source == "test" for r in results)


def test_refresh_venues_raises_on_invalid_event():
    def bad_fetcher(_key: str) -> list[dict[str, Any]]:
        return [{"title": "missing-fields"}]

    with pytest.raises(ValueError):
        refresh.refresh_venues(["austinSymphony"], fetcher=bad_fetcher)


def test_refresh_venues_raises_when_fetcher_returns_non_list():
    def bad_fetcher(_key: str) -> Any:
        return {"oops": "not a list"}

    with pytest.raises(ValueError):
        refresh.refresh_venues(["austinSymphony"], fetcher=bad_fetcher)


# ---------------------------------------------------------------------------
# assemble_payload + infer_season
# ---------------------------------------------------------------------------


def test_assemble_payload_groups_events_by_venue_with_metadata():
    results = [
        refresh.RefreshResult(
            venue_key="austinSymphony", events=[_good_event()], source="stub"
        ),
        refresh.RefreshResult(
            venue_key="austinOpera",
            events=[_good_event(title="Opera", type="opera")],
            source="stub",
        ),
    ]
    fixed_now = datetime(2026, 4, 30, 16, 0, tzinfo=timezone.utc)
    payload = refresh.assemble_payload(
        results,
        expected_venue_keys=refresh.CLASSICAL_VENUE_KEYS,
        season="2025-26",
        now=fixed_now,
    )
    assert payload["austinSymphony"][0]["title"] == "Sample Concert"
    assert payload["austinOpera"][0]["type"] == "opera"
    # Untouched expected keys must still appear, defaulting to empty lists.
    assert payload["earlyMusicAustin"] == []
    assert payload["lastUpdated"] == fixed_now.isoformat()
    assert payload["season"] == "2025-26"


def test_infer_season_august_starts_new_season():
    assert refresh.infer_season(datetime(2025, 8, 1, tzinfo=timezone.utc)) == "2025-26"
    assert refresh.infer_season(datetime(2025, 12, 31, tzinfo=timezone.utc)) == "2025-26"


def test_infer_season_january_to_july_belongs_to_prior_year():
    assert refresh.infer_season(datetime(2026, 1, 15, tzinfo=timezone.utc)) == "2025-26"
    assert refresh.infer_season(datetime(2026, 7, 31, tzinfo=timezone.utc)) == "2025-26"


# ---------------------------------------------------------------------------
# CLI / --dry-run end-to-end
# ---------------------------------------------------------------------------


def test_dry_run_main_exits_zero_and_emits_valid_payload(capsys: pytest.CaptureFixture[str]):
    rc = refresh.main(["--dry-run"])
    assert rc == 0
    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert summary["dry_run"] is True
    assert summary["source"] == "stub"
    assert "classical_payload" in summary
    assert "ballet_payload" in summary
    # The emitted payload itself must validate.
    assert refresh.validate_classical_data(summary["classical_payload"]) == []
    assert (
        refresh.validate_classical_data(
            summary["ballet_payload"], expected_venue_keys=refresh.BALLET_VENUE_KEYS
        )
        == []
    )


def test_dry_run_with_specific_venue(capsys: pytest.CaptureFixture[str]):
    rc = refresh.main(["--dry-run", "--venue", "austinSymphony"])
    assert rc == 0
    summary = json.loads(capsys.readouterr().out)
    # Only the classical group should be present.
    assert "classical_payload" in summary
    assert "ballet_payload" not in summary
    assert summary["venues"]["classical"] == {"austinSymphony": 1}


def test_dry_run_with_ballet_only(capsys: pytest.CaptureFixture[str]):
    rc = refresh.main(["--dry-run", "--venue", "balletAustin"])
    assert rc == 0
    summary = json.loads(capsys.readouterr().out)
    assert "ballet_payload" in summary
    assert "classical_payload" not in summary


def test_unknown_venue_argument_exits_with_systemexit():
    with pytest.raises(SystemExit):
        refresh.main(["--dry-run", "--venue", "not-a-real-venue"])


def test_live_mode_not_implemented_yet_returns_nonzero(capsys: pytest.CaptureFixture[str]):
    """Until task 3.1b lands, live mode must refuse to write rather than emit empty data."""
    rc = refresh.main([])
    assert rc != 0
    err = capsys.readouterr().err
    assert "task 3.1b" in err or "not implemented" in err


def test_writes_no_files_in_dry_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    out_classical = tmp_path / "classical.json"
    out_ballet = tmp_path / "ballet.json"
    rc = refresh.main(
        [
            "--dry-run",
            "--out-classical",
            str(out_classical),
            "--out-ballet",
            str(out_ballet),
        ]
    )
    assert rc == 0
    # Skeleton stage must not write to disk; phase 3.1b will add real I/O.
    assert not out_classical.exists()
    assert not out_ballet.exists()
