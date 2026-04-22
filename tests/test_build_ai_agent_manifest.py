"""Unit tests for scripts/build_ai_agent_manifest.py.

Covers the endpoint catalogue, absolute-URL construction, manifest
envelope, file-writing side effects, and the ``main`` entrypoint.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_ai_agent_manifest.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("build_ai_agent_manifest", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["build_ai_agent_manifest"] = mod
    spec.loader.exec_module(mod)
    return mod


baa = _load_module()


NOW = datetime(2026, 4, 22, 6, 0, 0, tzinfo=timezone.utc)


def test_absolute_url_joins_and_preserves_absolute():
    assert baa._absolute_url("") == baa.SITE_BASE_URL
    assert baa._absolute_url("robots.txt") == baa.SITE_BASE_URL + "robots.txt"
    assert baa._absolute_url("https://other.example/x") == "https://other.example/x"


def test_absolute_url_respects_custom_base():
    assert (
        baa._absolute_url("feed.xml", base_url="https://example.org/site/")
        == "https://example.org/site/feed.xml"
    )


def test_absolute_url_base_without_trailing_slash():
    assert (
        baa._absolute_url("feed.xml", base_url="https://example.org/site")
        == "https://example.org/site/feed.xml"
    )


def test_build_endpoints_has_at_least_five():
    endpoints = baa.build_endpoints()
    # Acceptance criterion for T3.5.
    assert len(endpoints) >= 5


def test_build_endpoints_have_stable_unique_ids():
    endpoints = baa.build_endpoints()
    ids = [e.id for e in endpoints]
    assert len(ids) == len(set(ids)), "endpoint ids must be unique"
    # A handful of known-essential endpoints callers may diff against.
    for required in ("llms_index", "api_events", "api_top_picks", "rss_top_picks", "ical_all"):
        assert required in ids


def test_build_endpoints_urls_are_absolute():
    endpoints = baa.build_endpoints()
    for e in endpoints:
        assert e.url.startswith("https://") or e.url.startswith("http://"), (
            f"endpoint {e.id} must use absolute URL"
        )


def test_endpoint_to_payload_includes_params_only_when_present():
    plain = baa.Endpoint(
        id="x",
        title="X",
        url="https://x/",
        content_type="application/json",
        agent_usage="note",
    ).to_payload()
    assert "params" not in plain

    templated = baa.Endpoint(
        id="y",
        title="Y",
        url="https://y/{slug}",
        content_type="application/json",
        agent_usage="note",
        params=("slug",),
    ).to_payload()
    assert templated["params"] == ["slug"]


def test_endpoint_to_payload_default_method_is_get():
    payload = baa.Endpoint(
        id="x",
        title="X",
        url="https://x/",
        content_type="text/plain",
        agent_usage="note",
    ).to_payload()
    assert payload["method"] == "GET"


def test_build_manifest_shape_and_required_keys():
    manifest = baa.build_manifest(now=NOW)
    for key in (
        "schema_version",
        "name",
        "description",
        "site_url",
        "contact",
        "policies",
        "endpoints",
        "generated_at",
    ):
        assert key in manifest, f"manifest missing {key!r}"

    assert manifest["schema_version"] == baa.SCHEMA_VERSION
    assert manifest["name"] == baa.SITE_NAME
    assert manifest["site_url"].startswith("https://")
    assert manifest["generated_at"] == "2026-04-22T06:00:00Z"
    assert isinstance(manifest["endpoints"], list)
    assert len(manifest["endpoints"]) >= 5


def test_build_manifest_endpoint_payload_fields():
    manifest = baa.build_manifest(now=NOW)
    for ep in manifest["endpoints"]:
        assert isinstance(ep, dict)
        for key in ("id", "title", "url", "content_type", "method", "agent_usage"):
            assert key in ep, f"endpoint {ep.get('id')!r} missing {key!r}"
        assert ep["url"].startswith("https://")


def test_build_manifest_policies_and_contact():
    manifest = baa.build_manifest(now=NOW)
    assert manifest["contact"]["type"] == "github"
    assert manifest["contact"]["url"].startswith("https://")
    assert manifest["policies"]["robots_txt"].endswith("robots.txt")
    assert manifest["policies"]["license"] == baa.LICENSE_LABEL


def test_build_manifest_respects_custom_base_url():
    manifest = baa.build_manifest(base_url="https://example.org/x/", now=NOW)
    assert manifest["site_url"] == "https://example.org/x/"
    for ep in manifest["endpoints"]:
        assert ep["url"].startswith("https://example.org/x/") or ep["url"].startswith(
            "https://example.org/x"
        )


def test_write_manifest_roundtrip(tmp_path):
    out = tmp_path / "ai-agent.json"
    payload = baa.build_manifest(now=NOW)
    written = baa.write_manifest(payload, out_path=out)
    assert written > 0
    assert out.exists()
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded == payload
    # File ends with trailing newline (consistent with other builders).
    assert out.read_text(encoding="utf-8").endswith("\n")


def test_write_manifest_creates_parent_dirs(tmp_path):
    out = tmp_path / "nested" / "dir" / "ai-agent.json"
    baa.write_manifest(baa.build_manifest(now=NOW), out_path=out)
    assert out.exists()


def test_main_writes_valid_manifest(tmp_path):
    out = tmp_path / "ai-agent.json"
    exit_code = baa.main(["--out", str(out), "--quiet"])
    assert exit_code == 0
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert len(loaded["endpoints"]) >= 5
    assert loaded["schema_version"] == baa.SCHEMA_VERSION


def test_main_respects_base_url_flag(tmp_path):
    out = tmp_path / "ai-agent.json"
    exit_code = baa.main(
        [
            "--out",
            str(out),
            "--base-url",
            "https://preview.example/cc/",
            "--quiet",
        ]
    )
    assert exit_code == 0
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["site_url"].startswith("https://preview.example/cc/")
    for ep in loaded["endpoints"]:
        assert ep["url"].startswith("https://preview.example/cc/")
