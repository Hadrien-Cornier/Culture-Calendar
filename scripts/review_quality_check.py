#!/usr/bin/env python3
"""Run the review-quality reviewer persona against a pending git diff.

Loads ``personas/code-review/review-quality.json``, captures a git diff,
and asks Anthropic Claude to apply the persona's rubric. Prints verdict,
summary, and any findings to stdout.

Usage:
    scripts/review_quality_check.py            # review staged + worktree (git diff HEAD)
    scripts/review_quality_check.py --commit   # review the last commit (HEAD~1..HEAD)
    scripts/review_quality_check.py --range main..HEAD
    scripts/review_quality_check.py --staged   # review only staged changes (git diff --cached)
    scripts/review_quality_check.py --no-llm   # print the prompt without calling the API
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

DEFAULT_PERSONA = Path("personas/code-review/review-quality.json")
DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_DIFF_BYTES = 200_000

REVIEW_TOOL = {
    "name": "record_review",
    "description": "Record the reviewer's verdict on the pending diff.",
    "input_schema": {
        "type": "object",
        "properties": {
            "verdict": {"type": "string", "enum": ["PASS", "FAIL", "ABSTAIN"]},
            "summary": {"type": "string"},
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string"},
                        "severity": {
                            "type": "string",
                            "enum": ["critical", "high", "medium", "low"],
                        },
                        "evidence": {"type": "string"},
                        "suggested_fix": {"type": "string"},
                    },
                    "required": ["code", "severity", "evidence", "suggested_fix"],
                },
            },
        },
        "required": ["verdict", "summary", "findings"],
    },
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="review_quality_check.py",
        description=(
            "Manually run the review-quality reviewer persona against a git "
            "diff. Default scope is staged + worktree changes (git diff HEAD)."
        ),
    )
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument(
        "--range",
        dest="range",
        default="HEAD",
        help="Git rev range passed to git diff (default: HEAD).",
    )
    scope.add_argument(
        "--commit",
        action="store_true",
        help="Review the last commit (equivalent to --range HEAD~1..HEAD).",
    )
    scope.add_argument(
        "--staged",
        action="store_true",
        help="Review only staged changes (git diff --cached).",
    )
    parser.add_argument(
        "--persona",
        type=Path,
        default=DEFAULT_PERSONA,
        help=f"Persona JSON file (default: {DEFAULT_PERSONA}).",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("LONG_RUN_MODEL_REVIEW_QUALITY", DEFAULT_MODEL),
        help=f"Anthropic model ID (default: {DEFAULT_MODEL}).",
    )
    parser.add_argument(
        "--max-diff-bytes",
        type=int,
        default=DEFAULT_MAX_DIFF_BYTES,
        help=f"Truncate diff to N bytes (default: {DEFAULT_MAX_DIFF_BYTES}).",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Print the prompt without calling the Anthropic API.",
    )
    return parser.parse_args(argv)


def capture_diff(args: argparse.Namespace) -> str:
    if args.staged:
        cmd = ["git", "diff", "--cached"]
    elif args.commit:
        cmd = ["git", "diff", "HEAD~1..HEAD"]
    else:
        cmd = ["git", "diff", args.range]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return proc.stdout


def truncate(text: str, max_bytes: int) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    head = encoded[:max_bytes].decode("utf-8", errors="ignore")
    return head + f"\n\n[... diff truncated at {max_bytes} bytes ...]\n"


def build_prompt(persona: dict, diff: str) -> tuple[str, list[dict]]:
    system = persona["system_prompt"]
    user = (
        f"Review the following pending diff against the {persona['persona']} rubric. "
        f"Call the record_review tool exactly once.\n\n"
        f"<untrusted>\n{diff}\n</untrusted>"
    )
    return system, [{"role": "user", "content": user}]


def call_api(system: str, messages: list[dict], model: str) -> dict:
    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.stderr.write(
            "ANTHROPIC_API_KEY missing; set it or pass --no-llm.\n"
        )
        sys.exit(2)
    client = anthropic.Anthropic(api_key=api_key)
    resp = client.messages.create(
        model=model,
        max_tokens=2048,
        system=system,
        messages=messages,
        tools=[REVIEW_TOOL],
        tool_choice={"type": "tool", "name": REVIEW_TOOL["name"]},
    )
    for block in resp.content:
        if getattr(block, "type", None) == "tool_use" and block.name == REVIEW_TOOL["name"]:
            return dict(block.input)
    raise RuntimeError(f"model {model!r} did not invoke {REVIEW_TOOL['name']!r}")


def render(payload: dict) -> str:
    lines = [f"Verdict: {payload.get('verdict', '?')}", "", payload.get("summary", "").strip()]
    findings = payload.get("findings") or []
    if findings:
        lines.append("")
        lines.append(f"Findings ({len(findings)}):")
        for i, f in enumerate(findings, 1):
            lines.append(
                f"  {i}. [{f.get('severity', '?')}] {f.get('code', '')}: {f.get('evidence', '')}"
            )
            fix = f.get("suggested_fix", "").strip()
            if fix:
                lines.append(f"     fix: {fix}")
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.persona.exists():
        sys.stderr.write(f"persona not found: {args.persona}\n")
        return 2
    persona = json.loads(args.persona.read_text())
    diff = capture_diff(args)
    if not diff.strip():
        sys.stderr.write("empty diff; nothing to review\n")
        return 2
    diff = truncate(diff, args.max_diff_bytes)
    system, messages = build_prompt(persona, diff)
    if args.no_llm:
        sys.stdout.write(f"--- system ---\n{system}\n\n--- user ---\n{messages[0]['content']}\n")
        return 0
    payload = call_api(system, messages, args.model)
    sys.stdout.write(render(payload))
    return 0


if __name__ == "__main__":
    sys.exit(main())
