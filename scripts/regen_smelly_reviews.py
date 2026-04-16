#!/usr/bin/env python3
"""Identify and invalidate cached reviews/summaries that contain banned AI-smell phrases."""

import argparse
import json
import re
import sys
from pathlib import Path

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

SUMMARY_CACHE_PATH = Path("cache/summary_cache.json")
DATA_JSON_PATH = Path("docs/data.json")


def scan_summary_cache(cache_path: Path) -> list[dict]:
    """Return list of smelly entries from the summary cache."""
    if not cache_path.exists():
        return []

    with open(cache_path, "r", encoding="utf-8") as f:
        cache = json.load(f)

    hits = []
    for key, summary in cache.items():
        matches = BANNED_RE.findall(summary)
        if matches:
            hits.append({"source": "summary_cache", "key": key, "text": summary, "matches": matches})
    return hits


def scan_data_json(data_path: Path) -> list[dict]:
    """Return list of smelly entries from docs/data.json descriptions/summaries."""
    if not data_path.exists():
        return []

    with open(data_path, "r", encoding="utf-8") as f:
        events = json.load(f)

    hits = []
    for event in events:
        title = event.get("title", "<untitled>")
        for field in ("description", "one_liner_summary"):
            text = event.get(field) or ""
            matches = BANNED_RE.findall(text)
            if matches:
                hits.append({
                    "source": "data_json",
                    "key": f"{title} [{field}]",
                    "text": text[:120],
                    "matches": matches,
                })
    return hits


def purge_summary_cache(cache_path: Path, smelly_keys: set[str]) -> int:
    """Remove smelly keys from the summary cache file. Returns count removed."""
    if not cache_path.exists() or not smelly_keys:
        return 0

    with open(cache_path, "r", encoding="utf-8") as f:
        cache = json.load(f)

    original_len = len(cache)
    cleaned = {k: v for k, v in cache.items() if k not in smelly_keys}
    removed = original_len - len(cleaned)

    if removed > 0:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cleaned, f, indent=2, ensure_ascii=False)

    return removed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Find and invalidate cached reviews containing banned AI-smell phrases."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report smelly entries without modifying caches.",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Delete smelly entries from caches.",
    )
    args = parser.parse_args()

    if not args.dry_run and not args.commit:
        print("Error: specify --dry-run or --commit", file=sys.stderr)
        return 1

    summary_hits = scan_summary_cache(SUMMARY_CACHE_PATH)
    data_hits = scan_data_json(DATA_JSON_PATH)
    all_hits = summary_hits + data_hits

    print(f"Scanned summary cache: {SUMMARY_CACHE_PATH} ({'found' if SUMMARY_CACHE_PATH.exists() else 'missing'})")
    print(f"Scanned data file:     {DATA_JSON_PATH} ({'found' if DATA_JSON_PATH.exists() else 'missing'})")
    print(f"Smelly entries found:  {len(all_hits)}")

    if all_hits:
        print("\nSample (up to 10):")
        for hit in all_hits[:10]:
            phrases = ", ".join(hit["matches"])
            print(f"  [{hit['source']}] {hit['key']}: {phrases}")

    if args.commit:
        smelly_summary_keys = {h["key"] for h in summary_hits}
        removed = purge_summary_cache(SUMMARY_CACHE_PATH, smelly_summary_keys)
        print(f"\nPurged {removed} entries from {SUMMARY_CACHE_PATH}.")
        if data_hits:
            print(
                f"Note: {len(data_hits)} smelly entries in {DATA_JSON_PATH} require "
                "re-running update_website_data.py to regenerate."
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
