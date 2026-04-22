"""Unit tests for ``scripts/build_robots.py`` and the published
``docs/robots.txt``.

Pins:

* Every canonical AI crawler has an explicit ``User-agent`` block.
* The wildcard ``User-agent: *`` and its ``Allow: /`` survive.
* The ``Sitemap`` directive points at the configured base URL.
* The generator is idempotent.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_robots.py"
LIVE_ROBOTS = REPO_ROOT / "docs" / "robots.txt"

REQUIRED_AGENTS = (
    "GPTBot",
    "ClaudeBot",
    "PerplexityBot",
    "CCBot",
    "Google-Extended",
    "Meta-ExternalAgent",
    "Amazonbot",
)


def _load_module():
    spec = importlib.util.spec_from_file_location("build_robots", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["build_robots"] = mod
    spec.loader.exec_module(mod)
    return mod


br = _load_module()


@pytest.mark.parametrize("agent", REQUIRED_AGENTS)
def test_render_robots_contains_agent_block(agent: str) -> None:
    body = br.render_robots()
    pattern = rf"^User-agent:\s*{re.escape(agent)}\s*$"
    assert re.search(pattern, body, flags=re.MULTILINE), (
        f"Missing explicit User-agent block for {agent}"
    )


def test_render_robots_preserves_wildcard_allow() -> None:
    body = br.render_robots()
    assert re.search(r"^User-agent:\s*\*\s*$", body, flags=re.MULTILINE)
    assert re.search(r"^Allow:\s*/\s*$", body, flags=re.MULTILINE)


def test_render_robots_has_one_allow_per_agent() -> None:
    body = br.render_robots()
    # wildcard + len(AI_CRAWLERS) = one Allow: / per user-agent block
    allow_lines = re.findall(r"^Allow:\s*/\s*$", body, flags=re.MULTILINE)
    assert len(allow_lines) == 1 + len(br.AI_CRAWLERS)


def test_render_robots_sitemap_uses_base_url() -> None:
    body = br.render_robots(base_url="https://example.com/site")
    assert "Sitemap: https://example.com/site/sitemap.xml" in body


def test_render_robots_sitemap_respects_trailing_slash() -> None:
    with_slash = br.render_robots(base_url="https://example.com/")
    without_slash = br.render_robots(base_url="https://example.com")
    assert "Sitemap: https://example.com/sitemap.xml" in with_slash
    assert "Sitemap: https://example.com/sitemap.xml" in without_slash


def test_render_robots_custom_sitemap_filename() -> None:
    body = br.render_robots(sitemap_filename="sitemap-main.xml")
    assert body.rstrip().endswith("sitemap-main.xml")


def test_render_robots_ends_with_newline() -> None:
    assert br.render_robots().endswith("\n")


def test_write_robots_is_idempotent(tmp_path: Path) -> None:
    out = tmp_path / "robots.txt"
    br.write_robots(out_path=out)
    first = out.read_text(encoding="utf-8")
    br.write_robots(out_path=out)
    second = out.read_text(encoding="utf-8")
    assert first == second


def test_write_robots_creates_missing_parents(tmp_path: Path) -> None:
    out = tmp_path / "nested" / "dir" / "robots.txt"
    br.write_robots(out_path=out)
    assert out.is_file()


def test_ai_crawlers_constant_matches_required_agents() -> None:
    assert tuple(br.AI_CRAWLERS) == REQUIRED_AGENTS


@pytest.mark.parametrize("agent", REQUIRED_AGENTS)
def test_live_robots_file_allowlists_agent(agent: str) -> None:
    assert LIVE_ROBOTS.is_file(), "docs/robots.txt missing — regenerate it"
    body = LIVE_ROBOTS.read_text(encoding="utf-8")
    pattern = rf"^User-agent:\s*{re.escape(agent)}\s*$"
    assert re.search(pattern, body, flags=re.MULTILINE), (
        f"docs/robots.txt missing {agent} block — run scripts/build_robots.py"
    )


def test_live_robots_file_has_sitemap_line() -> None:
    body = LIVE_ROBOTS.read_text(encoding="utf-8")
    assert re.search(
        r"^Sitemap:\s+https?://\S+/sitemap\.xml\s*$",
        body,
        flags=re.MULTILINE,
    )
