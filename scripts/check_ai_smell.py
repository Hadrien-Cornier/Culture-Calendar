#!/usr/bin/env python3
"""Lint docs/data.json for AI-smell: banned phrases and excessive em-dashes."""

import argparse
import json
import re
import sys

BANNED_PHRASES = (
    "haunting",
    "profound",
    "profound meditation",
    "resonates",
    "resonates deeply",
    "masterfully",
    "masterfully crafted",
    "breathtaking",
    "visceral",
    "lush",
    "luminous",
    "poignant",
    "exquisite",
    "meditation on",
    "in this film we see",
    "in this work we see",
    "tour de force",
    "transcendent",
)

BANNED_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(p) for p in BANNED_PHRASES) + r")\b",
    re.IGNORECASE,
)

FIELDS = ("description", "one_liner_summary")

EM_DASH = "\u2014"


def check_event(event, threshold):
    """Return list of violation strings for a single event."""
    violations = []
    title = event.get("title", "<untitled>")
    total_em = 0

    for field in FIELDS:
        text = event.get(field) or ""

        matches = BANNED_RE.findall(text)
        for m in matches:
            violations.append(f"  [{field}] banned phrase: \"{m}\"")

        count = text.count(EM_DASH)
        total_em += count

    if total_em > threshold:
        violations.append(
            f"  em-dash count {total_em} exceeds threshold {threshold}"
        )

    return (title, violations)


def main():
    parser = argparse.ArgumentParser(
        description="Check docs/data.json for AI-smell patterns."
    )
    parser.add_argument(
        "file",
        nargs="?",
        default="docs/data.json",
        help="Path to data.json (default: docs/data.json)",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=5,
        help="Max em-dashes per event before flagging (default: 5)",
    )
    args = parser.parse_args()

    with open(args.file, "r", encoding="utf-8") as f:
        events = json.load(f)

    total_violations = 0
    for event in events:
        title, violations = check_event(event, args.threshold)
        if violations:
            total_violations += len(violations)
            print(f"\n{title}:")
            for v in violations:
                print(v)

    if total_violations:
        print(f"\n{total_violations} violation(s) found across {len(events)} events.")
        return 1

    print(f"Clean: {len(events)} events checked, 0 violations.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
