"""Unit tests for ``scripts/build_config_json.py``.

Covers master_config extraction, default handling when the yaml is
missing or malformed, JSON output shape, and the CLI entry point.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_config_json.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("build_config_json", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["build_config_json"] = mod
    spec.loader.exec_module(mod)
    return mod


bcj = _load_module()


def _write_yaml(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")


def test_build_client_config_reads_buttondown_from_distribution():
    master = {"distribution": {"buttondown_endpoint": "https://buttondown.email/foo"}}
    payload = bcj.build_client_config(master_config=master)
    assert payload["buttondown_endpoint"] == "https://buttondown.email/foo"


def test_build_client_config_defaults_site_base_url_to_constant():
    payload = bcj.build_client_config(master_config={})
    assert payload["site_base_url"] == bcj.SITE_BASE_URL
    assert payload["site_base_url"].startswith("https://")


def test_build_client_config_accepts_base_url_override():
    payload = bcj.build_client_config(
        master_config={}, site_base_url="https://preview.example.com/"
    )
    assert payload["site_base_url"] == "https://preview.example.com/"


def test_build_client_config_empty_endpoint_when_distribution_missing():
    payload = bcj.build_client_config(master_config={})
    assert payload["buttondown_endpoint"] == ""


def test_build_client_config_empty_endpoint_when_value_missing():
    master = {"distribution": {}}
    payload = bcj.build_client_config(master_config=master)
    assert payload["buttondown_endpoint"] == ""


def test_build_client_config_empty_endpoint_when_value_non_string():
    master: dict[str, Any] = {"distribution": {"buttondown_endpoint": None}}
    payload = bcj.build_client_config(master_config=master)
    assert payload["buttondown_endpoint"] == ""


def test_build_client_config_empty_endpoint_when_distribution_not_mapping():
    master: dict[str, Any] = {"distribution": ["not", "a", "mapping"]}
    payload = bcj.build_client_config(master_config=master)
    assert payload["buttondown_endpoint"] == ""


def test_build_client_config_required_keys_present():
    payload = bcj.build_client_config(master_config={})
    assert set(payload.keys()) == {"buttondown_endpoint", "site_base_url"}


def test_load_master_config_returns_empty_when_file_missing(tmp_path: Path):
    missing = tmp_path / "nonexistent.yaml"
    assert bcj._load_master_config(missing) == {}


def test_load_master_config_parses_real_yaml(tmp_path: Path):
    cfg = tmp_path / "master_config.yaml"
    _write_yaml(
        cfg,
        "distribution:\n  buttondown_endpoint: https://buttondown.email/x\n",
    )
    loaded = bcj._load_master_config(cfg)
    assert loaded["distribution"]["buttondown_endpoint"] == "https://buttondown.email/x"


def test_load_master_config_rejects_non_mapping_top_level(tmp_path: Path):
    cfg = tmp_path / "master_config.yaml"
    _write_yaml(cfg, "- just\n- a\n- list\n")
    with pytest.raises(ValueError):
        bcj._load_master_config(cfg)


def test_load_master_config_handles_empty_file(tmp_path: Path):
    cfg = tmp_path / "master_config.yaml"
    _write_yaml(cfg, "")
    assert bcj._load_master_config(cfg) == {}


def test_write_config_produces_valid_json(tmp_path: Path):
    out = tmp_path / "config.json"
    payload = {"buttondown_endpoint": "", "site_base_url": bcj.SITE_BASE_URL}
    bcj.write_config(payload, out_path=out)
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded == payload


def test_write_config_sorts_keys_for_deterministic_output(tmp_path: Path):
    out = tmp_path / "config.json"
    payload = {"site_base_url": "x", "buttondown_endpoint": "y"}
    bcj.write_config(payload, out_path=out)
    text = out.read_text(encoding="utf-8")
    # buttondown_endpoint must appear before site_base_url (alphabetical)
    assert text.index("buttondown_endpoint") < text.index("site_base_url")


def test_write_config_ends_with_newline(tmp_path: Path):
    out = tmp_path / "config.json"
    bcj.write_config({"a": 1}, out_path=out)
    assert out.read_text(encoding="utf-8").endswith("\n")


def test_write_config_creates_parent_directory(tmp_path: Path):
    out = tmp_path / "nested" / "deeper" / "config.json"
    bcj.write_config({"a": 1}, out_path=out)
    assert out.exists()


def test_main_writes_config_file_with_required_keys(tmp_path: Path):
    cfg = tmp_path / "master_config.yaml"
    _write_yaml(
        cfg,
        'distribution:\n  buttondown_endpoint: "https://buttondown.email/demo"\n',
    )
    out = tmp_path / "config.json"
    exit_code = bcj.main(
        [
            "--config",
            str(cfg),
            "--out",
            str(out),
            "--quiet",
        ]
    )
    assert exit_code == 0
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["buttondown_endpoint"] == "https://buttondown.email/demo"
    assert loaded["site_base_url"] == bcj.SITE_BASE_URL


def test_main_accepts_base_url_override(tmp_path: Path):
    cfg = tmp_path / "master_config.yaml"
    _write_yaml(cfg, "distribution:\n  buttondown_endpoint: ''\n")
    out = tmp_path / "config.json"
    exit_code = bcj.main(
        [
            "--config",
            str(cfg),
            "--out",
            str(out),
            "--base-url",
            "https://staging.example.com/",
            "--quiet",
        ]
    )
    assert exit_code == 0
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["site_base_url"] == "https://staging.example.com/"


def test_main_defaults_produce_expected_shape(tmp_path: Path):
    """Sanity check that CLI invocation round-trips both keys."""
    cfg = tmp_path / "master_config.yaml"
    _write_yaml(cfg, "{}\n")
    out = tmp_path / "config.json"
    bcj.main(["--config", str(cfg), "--out", str(out), "--quiet"])
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert set(loaded.keys()) == {"buttondown_endpoint", "site_base_url"}
