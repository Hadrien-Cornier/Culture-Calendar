"""Tests for the Bedrock port of scripts/persona_critique.py.

The scripts fold two auth flavors of the Anthropic SDK into one code path:

- Direct API (``anthropic.Anthropic``) — requires ``ANTHROPIC_API_KEY``.
- AWS Bedrock (``anthropic.AnthropicBedrock``) — routes through the AWS
  SDK's default credential chain when ``CLAUDE_CODE_USE_BEDROCK=1``.

Each ``_fresh_module`` call reloads ``persona_critique`` under a fabricated
``os.environ`` so the module-level model-ID constants pick up the right
defaults for the scenario under test.
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "persona_critique.py"
BENCH_PATH = REPO_ROOT / "scripts" / "bench_personas.py"


def _fresh_module(monkeypatch: pytest.MonkeyPatch, env: dict[str, str | None]) -> Any:
    """Import ``persona_critique`` under ``env`` — fresh module each call.

    The module's model-ID constants are evaluated at import time, so tests
    that flip ``CLAUDE_CODE_USE_BEDROCK`` or override a model env var must
    reload the module rather than poke existing attributes.

    ``load_dotenv()`` runs during import and would repopulate vars the test
    just cleared; we stub it with a no-op dotenv module so test-scoped env
    fully controls the resolution path.
    """
    for key, value in env.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    stub = types.ModuleType("dotenv")
    stub.load_dotenv = lambda *a, **kw: None  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "dotenv", stub)
    sys.modules.pop("persona_critique_bedrock_test", None)
    spec = importlib.util.spec_from_file_location(
        "persona_critique_bedrock_test", SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["persona_critique_bedrock_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def _fresh_bench(monkeypatch: pytest.MonkeyPatch, env: dict[str, str | None]) -> Any:
    """Import ``bench_personas`` under ``env`` — fresh module each call."""
    for key, value in env.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    stub = types.ModuleType("dotenv")
    stub.load_dotenv = lambda *a, **kw: None  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "dotenv", stub)
    # Clear both the bench module and the sibling it imports lazily.
    sys.modules.pop("bench_personas_bedrock_test", None)
    sys.modules.pop("_persona_critique_bench", None)
    spec = importlib.util.spec_from_file_location(
        "bench_personas_bedrock_test", BENCH_PATH
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["bench_personas_bedrock_test"] = mod
    spec.loader.exec_module(mod)
    return mod


# --- Bedrock mode flag ----------------------------------------------------


@pytest.mark.parametrize("raw,expected", [
    ("1", True),
    ("true", True),
    ("TRUE", True),
    ("yes", True),
    ("0", False),
    ("false", False),
    ("", False),
])
def test_bedrock_mode_recognizes_truthy_values(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: bool
) -> None:
    mod = _fresh_module(monkeypatch, {"CLAUDE_CODE_USE_BEDROCK": raw})
    assert mod._bedrock_mode() is expected


def test_bedrock_mode_unset_is_false(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _fresh_module(monkeypatch, {"CLAUDE_CODE_USE_BEDROCK": None})
    assert mod._bedrock_mode() is False


# --- Model ID resolution --------------------------------------------------


def test_direct_mode_uses_direct_model_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _fresh_module(
        monkeypatch,
        {
            "CLAUDE_CODE_USE_BEDROCK": None,
            "ANTHROPIC_DEFAULT_SONNET_MODEL": None,
            "ANTHROPIC_DEFAULT_HAIKU_MODEL": None,
            "ANTHROPIC_DEFAULT_OPUS_MODEL": None,
        },
    )
    assert mod.SONNET_MODEL == "claude-sonnet-4-6"
    assert mod.HAIKU_MODEL == "claude-haiku-4-5-20251001"
    assert mod.OPUS_MODEL == "claude-opus-4-7"
    assert mod.DEFAULT_MODEL == mod.HAIKU_MODEL


def test_bedrock_mode_uses_bedrock_inference_profile_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _fresh_module(
        monkeypatch,
        {
            "CLAUDE_CODE_USE_BEDROCK": "1",
            "ANTHROPIC_DEFAULT_SONNET_MODEL": None,
            "ANTHROPIC_DEFAULT_HAIKU_MODEL": None,
            "ANTHROPIC_DEFAULT_OPUS_MODEL": None,
        },
    )
    # Bedrock inference-profile IDs follow us.anthropic.<family>-v1:0 format.
    for value in (mod.SONNET_MODEL, mod.HAIKU_MODEL, mod.OPUS_MODEL):
        assert value.startswith("us.anthropic."), value
        assert value.endswith("v1:0"), value
    assert "sonnet" in mod.SONNET_MODEL
    assert "haiku" in mod.HAIKU_MODEL
    assert "opus" in mod.OPUS_MODEL
    assert mod.DEFAULT_MODEL == mod.HAIKU_MODEL


def test_explicit_env_overrides_take_precedence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _fresh_module(
        monkeypatch,
        {
            "CLAUDE_CODE_USE_BEDROCK": "1",
            "ANTHROPIC_DEFAULT_SONNET_MODEL": "custom.sonnet",
            "ANTHROPIC_DEFAULT_HAIKU_MODEL": "custom.haiku",
            "ANTHROPIC_DEFAULT_OPUS_MODEL": "custom.opus",
        },
    )
    assert mod.SONNET_MODEL == "custom.sonnet"
    assert mod.HAIKU_MODEL == "custom.haiku"
    assert mod.OPUS_MODEL == "custom.opus"


def test_explicit_env_override_works_in_direct_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _fresh_module(
        monkeypatch,
        {
            "CLAUDE_CODE_USE_BEDROCK": None,
            "ANTHROPIC_DEFAULT_HAIKU_MODEL": "my-haiku",
        },
    )
    assert mod.HAIKU_MODEL == "my-haiku"
    assert mod.DEFAULT_MODEL == "my-haiku"


# --- Client factory -------------------------------------------------------


def test_client_factory_uses_subprocess_shim_when_flag_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bedrock mode must route through ``_ClaudeCodeSubprocessClient``.

    The Anthropic SDK's ``AnthropicBedrock`` requires boto3-resolvable IAM
    credentials, but operators using ``AWS_BEARER_TOKEN_BEDROCK`` (the Claude
    CLI auth shortcut) have none. Shelling out to ``claude -p`` inherits the
    CLI's already-wired Bedrock auth without needing a second credential
    surface — see ``_ClaudeCodeSubprocessClient`` docstring.
    """
    mod = _fresh_module(monkeypatch, {"CLAUDE_CODE_USE_BEDROCK": "1"})
    # Direct-client must not be used in Bedrock mode.
    fake_anthropic = MagicMock()
    fake_anthropic.Anthropic = MagicMock(
        side_effect=AssertionError("direct Anthropic() called in Bedrock mode")
    )
    monkeypatch.setitem(sys.modules, "anthropic", fake_anthropic)

    client = mod._default_anthropic_client_factory()
    assert isinstance(client, mod._ClaudeCodeSubprocessClient)
    assert hasattr(client, "messages")
    assert hasattr(client.messages, "create")


def test_client_factory_direct_path_requires_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _fresh_module(
        monkeypatch,
        {
            "CLAUDE_CODE_USE_BEDROCK": None,
            "ANTHROPIC_API_KEY": None,
        },
    )
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY missing"):
        mod._default_anthropic_client_factory()


def test_client_factory_direct_path_constructs_anthropic_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _fresh_module(
        monkeypatch,
        {
            "CLAUDE_CODE_USE_BEDROCK": None,
            "ANTHROPIC_API_KEY": "sk-test",
        },
    )
    fake_direct_instance = MagicMock(name="direct-client")
    fake_direct_cls = MagicMock(return_value=fake_direct_instance)
    fake_anthropic = MagicMock()
    fake_anthropic.Anthropic = fake_direct_cls
    fake_anthropic.AnthropicBedrock = MagicMock(
        side_effect=AssertionError("Bedrock called in direct mode")
    )
    monkeypatch.setitem(sys.modules, "anthropic", fake_anthropic)

    client = mod._default_anthropic_client_factory()
    assert client is fake_direct_instance
    fake_direct_cls.assert_called_once_with(api_key="sk-test")


def test_client_factory_bedrock_does_not_touch_anthropic_sdk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bedrock mode must not import or touch the Anthropic SDK at all.

    Old test asserted the factory called ``anthropic.AnthropicBedrock``;
    that path was replaced with a subprocess shim because the SDK's
    ``AnthropicBedrock`` needs IAM credentials ``claude -p`` does not
    require. This test now pins the new invariant: nothing from the
    ``anthropic`` module gets constructed when the flag is set.
    """
    mod = _fresh_module(monkeypatch, {"CLAUDE_CODE_USE_BEDROCK": "1"})
    fake_anthropic = MagicMock()
    fake_anthropic.AnthropicBedrock = MagicMock(
        side_effect=AssertionError("AnthropicBedrock called in subprocess mode")
    )
    fake_anthropic.Anthropic = MagicMock(
        side_effect=AssertionError("Anthropic called in subprocess mode")
    )
    monkeypatch.setitem(sys.modules, "anthropic", fake_anthropic)
    client = mod._default_anthropic_client_factory()
    assert isinstance(client, mod._ClaudeCodeSubprocessClient)


# --- Temperature handling (opus-family skips it) --------------------------


def test_model_accepts_temperature_skips_opus_substring(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _fresh_module(monkeypatch, {"CLAUDE_CODE_USE_BEDROCK": None})
    # Opus variants — direct + Bedrock inference profiles — both skip temp.
    assert mod._model_accepts_temperature("claude-opus-4-7") is False
    assert (
        mod._model_accepts_temperature(
            "us.anthropic.claude-opus-4-1-20250805-v1:0"
        )
        is False
    )
    # Sonnet + Haiku accept temperature.
    assert mod._model_accepts_temperature("claude-sonnet-4-6") is True
    assert (
        mod._model_accepts_temperature(
            "us.anthropic.claude-haiku-4-5-20251001-v1:0"
        )
        is True
    )


# --- Smoke imports --------------------------------------------------------


def test_persona_critique_smoke_import_direct_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _fresh_module(monkeypatch, {"CLAUDE_CODE_USE_BEDROCK": None})
    # Top-level surface every caller relies on stays stable across modes.
    for attr in (
        "SONNET_MODEL",
        "HAIKU_MODEL",
        "OPUS_MODEL",
        "DEFAULT_MODEL",
        "PERSONA_CRITIQUE_TOOL",
        "call_anthropic_critique",
        "run_all_personas",
        "main",
    ):
        assert hasattr(mod, attr), attr


def test_persona_critique_smoke_import_bedrock_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _fresh_module(monkeypatch, {"CLAUDE_CODE_USE_BEDROCK": "1"})
    assert hasattr(mod, "main")
    # Pricing table keys get rebuilt so bench agrees on pricing per-mode.
    assert mod.HAIKU_MODEL in mod.PRICING_USD_PER_MTOK
    assert mod.SONNET_MODEL in mod.PRICING_USD_PER_MTOK
    assert mod.OPUS_MODEL in mod.PRICING_USD_PER_MTOK


def test_bench_personas_skips_api_key_check_in_bedrock_mode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Bedrock mode relies on AWS credentials — no ANTHROPIC_API_KEY needed."""
    bench = _fresh_bench(
        monkeypatch,
        {
            "CLAUDE_CODE_USE_BEDROCK": "1",
            "ANTHROPIC_API_KEY": None,
        },
    )

    fake_per_model = {"claude-sonnet-4-6": {}}
    monkeypatch.setattr(
        bench, "benchmark_models", lambda *a, **kw: fake_per_model
    )
    monkeypatch.setattr(
        bench, "select_model", lambda pm: ("claude-sonnet-4-6", {})
    )
    monkeypatch.setattr(
        bench, "render_markdown", lambda pm, chosen, agreements: "# md"
    )

    out_md = tmp_path / "bench.md"
    out_config = tmp_path / "config.json"
    argv = [
        "--personas-dir",
        str(tmp_path),
        "--check-script",
        str(REPO_ROOT / "scripts" / "check_live_site.py"),
        "--out-md",
        str(out_md),
        "--out-config",
        str(out_config),
    ]
    assert bench.main(argv) == 0
    assert out_md.exists()
    assert out_config.exists()


def test_bench_personas_still_requires_api_key_in_direct_mode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bench = _fresh_bench(
        monkeypatch,
        {
            "CLAUDE_CODE_USE_BEDROCK": None,
            "ANTHROPIC_API_KEY": None,
        },
    )
    argv = [
        "--personas-dir",
        str(tmp_path),
        "--check-script",
        str(REPO_ROOT / "scripts" / "check_live_site.py"),
        "--out-md",
        str(tmp_path / "bench.md"),
        "--out-config",
        str(tmp_path / "config.json"),
    ]
    assert bench.main(argv) == 2
