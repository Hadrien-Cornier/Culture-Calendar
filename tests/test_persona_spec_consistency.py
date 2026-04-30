"""Regression tests for persona spec internal consistency.

Prevents silent recurrence of the class of harness bug that caused the
2026-04-23 T5.3 persona-gate failure: ``search-user.json`` typed "Para"
via a ``js_truthy`` assert AND typed "Para" again via
``pre_screenshot_actions``, resulting in "ParaPara" at screenshot time
while ground truth was captured at the intermediate "Para" state. The
LLM persona correctly flagged the inconsistency.

Rule: asserts and pre_screenshot_actions may not both drive the same
input selector (typing or clearing). One mechanism per input.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

PERSONAS_DIR = Path(__file__).resolve().parent.parent / "personas" / "live-site"
TYPE_ACTION_RE = re.compile(
    r"""document\.getElementById\(['"](?P<id>[^'"]+)['"]\)|
        querySelector\(['"](?P<sel>[^'"]+)['"]\)""",
    re.VERBOSE,
)


def _persona_files() -> list[Path]:
    return sorted(PERSONAS_DIR.glob("*.json"))


def _input_targets_from_js(expr: str) -> set[str]:
    """Extract selectors touched by a js_truthy expression that assigns
    ``.value`` or dispatches a typed event. Conservative — only flags
    selectors that appear alongside a ``.value=`` assignment."""
    if ".value" not in expr and "dispatchEvent" not in expr:
        return set()
    found: set[str] = set()
    for match in TYPE_ACTION_RE.finditer(expr):
        ident = match.group("id") or match.group("sel")
        if ident:
            found.add(f"#{ident}" if match.group("id") else ident)
    return found


def _input_targets_from_asserts(spec: dict) -> set[str]:
    targets: set[str] = set()
    for a in spec.get("asserts") or []:
        if a.get("type") == "js_truthy":
            targets |= _input_targets_from_js(a.get("expression", ""))
    return targets


def _input_targets_from_pre_actions(spec: dict) -> set[str]:
    targets: set[str] = set()
    for action in spec.get("pre_screenshot_actions") or []:
        if action.get("type") == "type" and action.get("selector"):
            targets.add(action["selector"])
    return targets


@pytest.mark.parametrize("spec_path", _persona_files(), ids=lambda p: p.name)
def test_no_duplicate_input_driver(spec_path: Path) -> None:
    """Asserts and pre_screenshot_actions must not both type into the same input.

    Allowing both causes doubled text (e.g. "ParaPara") at screenshot time
    while ground truth was captured at the intermediate state — the LLM
    persona sees a contradiction and correctly reports FAIL.
    """
    spec = json.loads(spec_path.read_text())
    asserted = _input_targets_from_asserts(spec)
    pre = _input_targets_from_pre_actions(spec)
    overlap = asserted & pre
    assert not overlap, (
        f"{spec_path.name}: selector(s) {sorted(overlap)} are driven by BOTH "
        "a js_truthy assert (with .value= or dispatchEvent) AND a "
        "pre_screenshot_actions 'type' entry. Keep one, drop the other — "
        "otherwise the screenshot captures a double-typed state while "
        "ground truth reflects the intermediate state."
    )


def test_persona_dir_has_expected_files() -> None:
    """Guardrail: the parametrization above silently skips if the dir is empty."""
    assert len(_persona_files()) >= 6, (
        f"expected ≥6 persona specs under {PERSONAS_DIR}, "
        f"found {len(_persona_files())}"
    )
