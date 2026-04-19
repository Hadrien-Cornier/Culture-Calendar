"""Unit tests for scripts/require_persona_approval.py (Gate B)."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "require_persona_approval.py"


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("require_persona_approval", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["require_persona_approval"] = mod
    spec.loader.exec_module(mod)
    return mod


rpa = _load_module()


def test_rewrite_personas_swaps_live_host_for_localhost(tmp_path):
    personas_dir = tmp_path / "in"
    personas_dir.mkdir()
    (personas_dir / "a.json").write_text(
        json.dumps(
            {
                "persona": "p1",
                "url": "https://hadrien-cornier.github.io/Culture-Calendar/",
                "other": "keep me",
            }
        )
    )
    (personas_dir / "b.json").write_text(
        json.dumps(
            {
                "persona": "p2",
                "url": "https://hadrien-cornier.github.io/Culture-Calendar/data.json",
            }
        )
    )

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    base = "http://127.0.0.1:9999/"
    rewritten = rpa.rewrite_personas(personas_dir, out_dir, base)

    assert len(rewritten) == 2
    a = json.loads((out_dir / "a.json").read_text())
    b = json.loads((out_dir / "b.json").read_text())
    assert a["url"] == "http://127.0.0.1:9999/"
    assert a["other"] == "keep me"  # other fields unchanged
    assert b["url"] == "http://127.0.0.1:9999/data.json"


def test_rewrite_personas_leaves_unrelated_urls_alone(tmp_path):
    personas_dir = tmp_path / "in"
    personas_dir.mkdir()
    (personas_dir / "custom.json").write_text(
        json.dumps(
            {
                "persona": "custom",
                "url": "https://some-other-site.example/",
            }
        )
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    rpa.rewrite_personas(personas_dir, out_dir, "http://127.0.0.1:1/")
    data = json.loads((out_dir / "custom.json").read_text())
    # Not under LIVE_HOST prefix → untouched.
    assert data["url"] == "https://some-other-site.example/"


def test_rewrite_personas_handles_trailing_slash_variant(tmp_path):
    personas_dir = tmp_path / "in"
    personas_dir.mkdir()
    (personas_dir / "x.json").write_text(
        json.dumps(
            {
                "persona": "x",
                "url": "https://hadrien-cornier.github.io/Culture-Calendar",
            }
        )
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    rpa.rewrite_personas(personas_dir, out_dir, "http://127.0.0.1:1/")
    data = json.loads((out_dir / "x.json").read_text())
    assert data["url"] == "http://127.0.0.1:1"


def test_pick_free_port_returns_int_in_valid_range():
    port = rpa._pick_free_port()
    assert isinstance(port, int)
    assert 1024 <= port <= 65535
