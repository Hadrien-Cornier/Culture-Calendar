#!/usr/bin/env python3
"""Benchmark Anthropic models on the persona critique task.

Runs each persona against the live site with each candidate model, captures
PASS/FAIL verdicts and per-call latency, then picks the cheapest model whose
verdicts agree with the reference model (Sonnet 4.6) on at least
``AGREEMENT_THRESHOLD`` / N personas.

Outputs:

- ``docs/persona_model_benchmark.md`` — human-readable scorecard.
- ``config/persona_model.json`` — ``{"model": "<chosen>", ...}`` consumed by
  ``scripts/persona_critique.py`` on subsequent runs.

Deliberately modest: 3 models × 6 personas = 18 API calls per bench, roughly
$1-2 at current Anthropic pricing. Re-run on model releases, not routinely.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Sequence

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    def load_dotenv(*_args: Any, **_kwargs: Any) -> None:
        return None

load_dotenv()


def _load_persona_critique_module() -> Any:
    """Import sibling ``persona_critique.py`` without requiring a package."""
    module_name = "_persona_critique_bench"
    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached
    here = Path(__file__).resolve().parent / "persona_critique.py"
    spec = importlib.util.spec_from_file_location(module_name, here)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return mod


# --- Pricing (USD per 1M tokens) -----------------------------------------
# Source: https://www.anthropic.com/pricing (2026-04)
# Keeping rough for bench cost estimation; not the on-invoice truth.
PRICING_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    # model: (input_rate, output_rate)
    "claude-haiku-4-5-20251001": (1.0, 5.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-4-7": (15.0, 75.0),
}

REFERENCE_MODEL = "claude-sonnet-4-6"
AGREEMENT_THRESHOLD = 5  # out of 6 personas


def _model_cost_usd(
    model: str, input_tokens: int, output_tokens: int
) -> float | None:
    """Estimate one-call cost; return ``None`` if pricing unknown."""
    rate = PRICING_USD_PER_MTOK.get(model)
    if rate is None:
        return None
    in_rate, out_rate = rate
    return (input_tokens * in_rate + output_tokens * out_rate) / 1_000_000.0


def _extract_verdict(critique: Any) -> str:
    """Extract the verdict field from a PersonaCritique (or fall back)."""
    if critique is None:
        return "UNKNOWN"
    verdict = getattr(critique, "verdict", None)
    if isinstance(verdict, str) and verdict.upper() in {"PASS", "FAIL"}:
        return verdict.upper()
    return "UNKNOWN"


def benchmark_models(
    personas_dir: Path,
    check_script: Path,
    models: Sequence[str],
    *,
    anthropic_client_factory: Any = None,
    capture_fn: Any = None,
) -> dict[str, Any]:
    """Run every persona × every model. Return a dict of raw results."""
    pc = _load_persona_critique_module()
    paths = pc.load_persona_paths(personas_dir)
    if not check_script.is_file():
        raise FileNotFoundError(f"check script not found: {check_script}")

    factory = anthropic_client_factory or pc._default_anthropic_client_factory
    client = factory()
    capture = capture_fn or pc.capture_screenshot_and_dom

    per_model: dict[str, dict[str, Any]] = {}
    for model in models:
        per_persona: dict[str, Any] = {}
        for path in paths:
            persona = json.loads(path.read_text(encoding="utf-8"))
            name = persona.get("persona") or path.stem
            passed, rc, stdout, stderr = pc.run_check_live_site(
                check_script, path
            )
            t0 = time.monotonic()
            critique: Any = None
            critique_error: str | None = None
            verdict = "UNKNOWN"
            input_tokens = output_tokens = 0
            try:
                shot, dom = capture(persona)
                _, messages = pc.build_anthropic_messages(
                    persona,
                    pc.PersonaResult(
                        name=name,
                        passed=passed,
                        exit_code=rc,
                        stdout=stdout,
                        stderr=stderr,
                    ),
                    shot,
                    dom,
                )
                call_kwargs: dict[str, Any] = {
                    "model": model,
                    "max_tokens": pc.DEFAULT_MAX_TOKENS,
                    "system": (persona.get("llm", {}).get("system_prompt") or ""),
                    "messages": messages,
                    "tools": [pc.PERSONA_CRITIQUE_TOOL],
                    "tool_choice": {
                        "type": "tool",
                        "name": pc.PERSONA_CRITIQUE_TOOL["name"],
                    },
                }
                if model not in pc.MODELS_WITHOUT_TEMPERATURE:
                    call_kwargs["temperature"] = pc.DEFAULT_TEMPERATURE
                resp = client.messages.create(**call_kwargs)
                usage = getattr(resp, "usage", None)
                if usage is not None:
                    input_tokens = getattr(usage, "input_tokens", 0) or 0
                    output_tokens = getattr(usage, "output_tokens", 0) or 0
                payload = pc._extract_tool_use_block(
                    resp, pc.PERSONA_CRITIQUE_TOOL["name"]
                )
                if payload is None:
                    raise ValueError(f"{model} did not invoke the critique tool")
                critique = pc._parse_critique_payload(payload)
                verdict = critique.verdict
            except Exception as exc:  # noqa: BLE001
                critique_error = f"{type(exc).__name__}: {exc}"
            latency_s = time.monotonic() - t0
            cost_usd = _model_cost_usd(model, input_tokens, output_tokens)
            per_persona[name] = {
                "structural_pass": passed,
                "verdict": verdict,
                "critique": critique,
                "error": critique_error,
                "latency_s": round(latency_s, 2),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": cost_usd,
            }
        per_model[model] = per_persona

    return per_model


def _verdicts_for(model_data: dict[str, Any]) -> dict[str, str]:
    return {k: v["verdict"] for k, v in model_data.items()}


def select_model(
    per_model: dict[str, Any],
    *,
    reference: str = REFERENCE_MODEL,
    threshold: int = AGREEMENT_THRESHOLD,
) -> tuple[str, dict[str, int]]:
    """Pick cheapest model whose verdicts agree with ``reference`` on >= threshold.

    Returns ``(chosen_model, agreement_map)`` where ``agreement_map`` counts
    matching verdicts per candidate model.
    """
    ref_verdicts = _verdicts_for(per_model[reference])
    agreements: dict[str, int] = {}
    for model, data in per_model.items():
        v = _verdicts_for(data)
        agreements[model] = sum(
            1 for k in ref_verdicts if ref_verdicts[k] == v.get(k)
        )

    # Rank candidates by cost then latency; reference model is always eligible.
    def avg_cost(model: str) -> float:
        costs = [
            v["cost_usd"]
            for v in per_model[model].values()
            if v["cost_usd"] is not None
        ]
        return sum(costs) / len(costs) if costs else float("inf")

    eligible = [m for m in per_model if agreements[m] >= threshold]
    if not eligible:
        # Fall back to reference when nobody meets the bar.
        return reference, agreements
    eligible.sort(key=lambda m: (avg_cost(m), m != reference))
    return eligible[0], agreements


def render_markdown(
    per_model: dict[str, Any],
    chosen: str,
    agreements: dict[str, int],
) -> str:
    """Render the benchmark scorecard as markdown."""
    lines = ["# Persona-Critique Model Benchmark", ""]
    lines.append(f"Reference model: `{REFERENCE_MODEL}`. Agreement threshold: {AGREEMENT_THRESHOLD}/N.")
    lines.append(f"**Chosen model: `{chosen}`**")
    lines.append("")
    lines.append("## Per-model summary")
    lines.append("")
    lines.append("| Model | Agreement vs reference | Avg latency (s) | Total cost (USD) |")
    lines.append("|---|---|---|---|")
    for model, data in per_model.items():
        latencies = [v["latency_s"] for v in data.values()]
        costs = [v["cost_usd"] or 0.0 for v in data.values()]
        avg_lat = sum(latencies) / len(latencies) if latencies else 0
        total_cost = sum(costs)
        lines.append(
            f"| `{model}` | {agreements[model]}/{len(data)} | "
            f"{avg_lat:.2f} | ${total_cost:.4f} |"
        )
    lines.append("")
    lines.append("## Per-persona verdicts")
    lines.append("")
    personas = sorted(next(iter(per_model.values())).keys())
    header = "| Persona | " + " | ".join(f"`{m}`" for m in per_model) + " |"
    sep = "|---|" + "|".join("---" for _ in per_model) + "|"
    lines.append(header)
    lines.append(sep)
    for persona in personas:
        row = [persona]
        for model in per_model:
            d = per_model[model][persona]
            row.append(d["verdict"])
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    # Surface errors so silent failures (e.g. deprecated params) aren't hidden
    error_rows: list[str] = []
    for model, data in per_model.items():
        for persona, d in data.items():
            if d.get("error"):
                error_rows.append(
                    f"| `{model}` | {persona} | {d['error'][:140]} |"
                )
    if error_rows:
        lines.append("## Errors")
        lines.append("")
        lines.append("| Model | Persona | Error |")
        lines.append("|---|---|---|")
        lines.extend(error_rows)
        lines.append("")

    lines.append("## Notes")
    lines.append("")
    lines.append(
        "- All models called via tool-use (`record_persona_critique`); "
        "verdicts are read from the structured payload, not prose."
    )
    lines.append("- Re-run: `.venv/bin/python scripts/bench_personas.py`")
    return "\n".join(lines) + "\n"


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="bench_personas.py",
        description="Benchmark Anthropic models on the persona critique task.",
    )
    p.add_argument(
        "--personas-dir",
        type=Path,
        default=Path(".overnight/personas"),
        help="Directory of persona *.json specs.",
    )
    p.add_argument(
        "--check-script",
        type=Path,
        default=Path("scripts/check_live_site.py"),
        help="Path to check_live_site.py.",
    )
    p.add_argument(
        "--models",
        nargs="+",
        default=list(PRICING_USD_PER_MTOK.keys()),
        help="Models to benchmark.",
    )
    p.add_argument(
        "--out-md",
        type=Path,
        default=Path("docs/persona_model_benchmark.md"),
        help="Markdown scorecard output path.",
    )
    p.add_argument(
        "--out-config",
        type=Path,
        default=Path("config/persona_model.json"),
        help="Config file to write with chosen model.",
    )
    return p.parse_args(list(argv))


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "error: ANTHROPIC_API_KEY missing; benchmark requires live Anthropic",
            file=sys.stderr,
        )
        return 2
    per_model = benchmark_models(
        args.personas_dir, args.check_script, args.models
    )
    chosen, agreements = select_model(per_model)
    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    args.out_md.write_text(render_markdown(per_model, chosen, agreements), encoding="utf-8")
    args.out_config.parent.mkdir(parents=True, exist_ok=True)
    args.out_config.write_text(
        json.dumps(
            {
                "model": chosen,
                "reference": REFERENCE_MODEL,
                "agreement_threshold": AGREEMENT_THRESHOLD,
                "agreements": agreements,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"chosen model: {chosen}; wrote {args.out_md} and {args.out_config}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
