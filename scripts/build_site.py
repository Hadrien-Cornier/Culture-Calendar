#!/usr/bin/env python3
"""Assemble the full publishable site into a clean output directory.

This is the *build* step for the gh-pages split: ``main`` keeps only the
source (scrapers, generators, hand-authored ``docs/`` pages, and the
committed data/cache JSON), while the rendered site lives on a separate
``gh-pages`` branch. ``build_site.py`` reproduces the current ``docs/``
tree faithfully so nothing is lost on publish.

No network, no re-rating, no API or Chromium calls. The flow is:

1. Clean + recreate ``--out`` (default ``_site``).
2. ``shutil.copytree(docs_dir, out_dir)`` FIRST. This seeds ``out/`` with
   every hand-authored page, the four committed data/cache files
   (``data.json``, ``source_update_times.json``, ``classical_data.json``,
   ``ballet_data.json``), ``config.json``, AND the no-generator artifacts
   (``variants/``, ``archive/v0/``). So even if a generator is missing or
   fails, the file still exists in ``out/``.
3. Run each site generator INTO ``out/`` (best-effort) so generated
   artifacts are freshened. Each generator reads the *seeded*
   ``out/data.json`` — never the network. A failure in one generator is
   logged as a WARN and does not abort the build; the copytree seed
   covers it.
4. RESTORE the seed for any file a generator *deleted*. Several generators
   (``build_event_shells``, ``build_event_ics``, ``build_api_json``,
   ``build_og_cards``) clean stale outputs that no longer match the current
   ``data.json``. When the committed ``docs/`` tree has drifted from
   ``data.json`` (e.g. ``docs/events/`` holds shells from an older dataset),
   that clean step would otherwise *delete a committed file*, violating the
   "nothing is lost on publish" guarantee. This pass copies back any file
   present in ``docs/`` but missing from ``out/`` after generation, so the
   seed invariant holds even under drift.
5. PARITY CHECK: compare the set of files under ``docs/`` and ``out/`` and
   loudly report any ``docs/`` file missing from ``out/`` (the regression
   signal — should be empty after the restore pass).

Always exits 0 — it is a build tool, and the parity report is the
actionable signal.

Usage::

    python scripts/build_site.py --out _site --docs-dir docs
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

# scripts/ lives directly under the repo root.
_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS_DIR = _REPO_ROOT / "scripts"


def _gen(name: str, build_args: Callable[[Path], list[str]]) -> dict:
    """Describe one generator: its script name and a builder for its CLI args.

    ``build_args`` receives the resolved ``out_dir`` and returns the list of
    CLI flags that re-point the generator's inputs at the seeded ``out/``
    tree and its outputs back into ``out/``.
    """
    return {"name": name, "build_args": build_args}


# Generators are run in this exact order. ``build_archive`` must run AFTER
# ``build_weekly_digest`` (it scans ``weekly/*.html``), and ``build_sitemap``
# runs LAST because it enumerates the finished tree.
#
# Every generator is invoked as a subprocess of its own CLI so the build is
# isolated from module-level import state. Each ``--data`` / ``--docs`` flag
# points at the SEEDED ``out/`` copy, so no generator re-reads ``docs/`` and
# no network/re-rating ever happens.
def _generators() -> list[dict]:
    return [
        _gen(
            "build_api_json.py",
            lambda out: [
                "--data",
                str(out / "data.json"),
                "--out-dir",
                str(out / "api"),
                "--event-json-dir",
                str(out / "events"),
                "--og-dir",
                str(out / "og"),
                "--quiet",
            ],
        ),
        _gen(
            "build_event_shells.py",
            lambda out: [
                "--data",
                str(out / "data.json"),
                "--out",
                str(out / "events"),
                "--quiet",
            ],
        ),
        _gen(
            "build_event_ics.py",
            lambda out: [
                "--data",
                str(out / "data.json"),
                "--out",
                str(out / "events"),
                "--quiet",
            ],
        ),
        _gen(
            "build_ics_feed.py",
            lambda out: [
                "--data",
                str(out / "data.json"),
                "--all-out",
                str(out / "calendar.ics"),
                "--top-out",
                str(out / "top-picks.ics"),
                "--quiet",
            ],
        ),
        _gen(
            "build_rss_feed.py",
            lambda out: [
                "--data",
                str(out / "data.json"),
                "--out",
                str(out / "feed.xml"),
                "--quiet",
            ],
        ),
        _gen(
            "build_llms_txt.py",
            lambda out: [
                "--data",
                str(out / "data.json"),
                "--docs",
                str(out),
                "--about",
                str(out / "ABOUT.md"),
                "--out-index",
                str(out / "llms.txt"),
                "--out-full",
                str(out / "llms-full.txt"),
                "--quiet",
            ],
        ),
        _gen(
            "build_ai_agent_manifest.py",
            # No --data flag: builds from static endpoint constants.
            lambda out: [
                "--out",
                str(out / ".well-known" / "ai-agent.json"),
                "--quiet",
            ],
        ),
        _gen(
            "build_weekly_digest.py",
            lambda out: [
                "--data",
                str(out / "data.json"),
                "--out-dir",
                str(out / "weekly"),
                "--all-upcoming",
                "--weeks-ahead",
                "4",
                "--quiet",
            ],
        ),
        # AFTER build_weekly_digest: scans weekly/*.html.
        _gen(
            "build_archive.py",
            lambda out: [
                "--weekly-dir",
                str(out / "weekly"),
                "--out",
                str(out / "archive.html"),
                "--quiet",
            ],
        ),
        _gen(
            "build_people_pages.py",
            lambda out: [
                "--data",
                str(out / "data.json"),
                "--out-dir",
                str(out / "people"),
                "--quiet",
            ],
        ),
        _gen(
            "build_venue_pages.py",
            lambda out: [
                "--data",
                str(out / "data.json"),
                "--out-dir",
                str(out / "venues"),
                "--quiet",
            ],
        ),
        _gen(
            "build_og_cards.py",
            lambda out: [
                "--data",
                str(out / "data.json"),
                "--out-dir",
                str(out / "og"),
                "--quiet",
            ],
        ),
        _gen(
            "build_config_json.py",
            lambda out: [
                "--out",
                str(out / "config.json"),
                "--quiet",
            ],
        ),
        _gen(
            "build_wishlist.py",
            # No --data flag: reads venue-prospects / README.
            lambda out: [
                "--out",
                str(out / "wishlist.html"),
                "--quiet",
            ],
        ),
        _gen(
            "build_composer_feature.py",
            # --offline keeps the LLM call off the network (static fallback).
            lambda out: [
                "--data",
                str(out / "data.json"),
                "--out-dir",
                str(out / "features"),
                "--offline",
                "--quiet",
            ],
        ),
        _gen(
            "build_robots.py",
            lambda out: [
                "--out",
                str(out / "robots.txt"),
                "--quiet",
            ],
        ),
        # LAST: enumerates the finished tree.
        _gen(
            "build_sitemap.py",
            lambda out: [
                "--docs",
                str(out),
                "--out",
                str(out / "sitemap.xml"),
                "--robots",
                str(out / "robots.txt"),
                "--quiet",
            ],
        ),
    ]


def _relative_file_set(root: Path) -> set[str]:
    """Return the set of file paths (relative to ``root``) under ``root``."""
    if not root.is_dir():
        return set()
    return {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}


def seed_out_dir(docs_dir: Path, out_dir: Path) -> None:
    """Clean + recreate ``out_dir`` and copy the whole ``docs_dir`` into it."""
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    # dirs_exist_ok=True is belt-and-braces (out_dir is freshly empty).
    shutil.copytree(docs_dir, out_dir, dirs_exist_ok=True)


def run_generators(out_dir: Path, generators: list[dict]) -> list[str]:
    """Run every generator into ``out_dir``, best-effort.

    Returns the list of generator names that WARNed (failed). Each generator
    is a subprocess of its own CLI; a non-zero exit or an exception is logged
    and the build continues (the copytree seed covers the artifact).
    """
    warned: list[str] = []
    for gen in generators:
        name = gen["name"]
        script_path = _SCRIPTS_DIR / name
        if not script_path.is_file():
            print(f"[build_site] WARN {name}: script not found at {script_path}")
            warned.append(name)
            continue
        argv = [sys.executable, str(script_path)] + gen["build_args"](out_dir)
        try:
            result = subprocess.run(
                argv,
                cwd=str(_REPO_ROOT),
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                detail = (result.stderr or result.stdout or "").strip()
                # Keep the WARN line readable: last meaningful line only.
                last = detail.splitlines()[-1] if detail else f"rc={result.returncode}"
                print(f"[build_site] WARN {name}: {last}")
                warned.append(name)
            else:
                print(f"[build_site] OK {name}")
        except Exception as exc:  # pragma: no cover - defensive only
            print(f"[build_site] WARN {name}: {exc}")
            warned.append(name)
    return warned


# Directories/files produced by generators (mirrors .gitignore). Generator
# output is AUTHORITATIVE for these: build_event_shells.py etc. delete stale
# artifacts before writing, so the seed must never resurrect a pruned file —
# that is exactly how stale event shells (from docs/data-pilot.json drift) used
# to leak back onto the published site. Static, no-generator content
# (docs/variants/, docs/archive/, hand-authored pages) is still restored.
_GENERATED_PREFIXES = ("events/", "people/", "venues/", "weekly/", "og/")
_GENERATED_FILES = {
    "sitemap.xml",
    "robots.txt",
    "feed.xml",
    "calendar.ics",
    "top-picks.ics",
    "llms.txt",
    "llms-full.txt",
    ".well-known/ai-agent.json",
}


def _is_generator_owned(rel: str) -> bool:
    """True if ``rel`` is produced by a generator (so the seed must not override it).

    ``api/`` is mixed: ``api/*.json`` + ``api/index.html`` are generated, but
    ``api/README.md`` is hand-authored, so api is matched specifically rather
    than by a blanket prefix.
    """
    rel = rel.replace("\\", "/")
    if rel.startswith(_GENERATED_PREFIXES):
        return True
    if rel.startswith("api/") and (rel.endswith(".json") or rel == "api/index.html"):
        return True
    return rel in _GENERATED_FILES


def restore_deleted_seed(docs_dir: Path, out_dir: Path) -> list[str]:
    """Copy back any *non-generated* ``docs/`` file missing from ``out/``.

    Static, no-generator content (variants/, archive/, hand-authored pages) is
    restored so nothing hand-made is lost. Generator-owned artifacts that a
    generator pruned (stale event shells/ics/json, og cards, feeds) are left
    pruned — the generator output reflects the current ``data.json`` and is
    authoritative. Returns the restored paths.
    """
    docs_files = _relative_file_set(docs_dir)
    out_files = _relative_file_set(out_dir)
    restored: list[str] = []
    for rel in sorted(docs_files - out_files):
        if _is_generator_owned(rel):
            continue  # generator pruned a stale artifact — keep it pruned
        src = docs_dir / rel
        dest = out_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        restored.append(rel)
    if restored:
        print(
            f"[build_site] restored {len(restored)} static seed file(s) "
            f"(no-generator content not reproduced by any generator)"
        )
    return restored


def parity_check(docs_dir: Path, out_dir: Path, warned: list[str]) -> set[str]:
    """Compare file sets under ``docs_dir`` and ``out_dir``; print a report.

    Returns the set of paths present in ``docs/`` but MISSING from ``out/``
    (the regression signal). Because ``out/`` is seeded by copytree before any
    generator runs, this set should be empty in a healthy build.
    """
    docs_files = _relative_file_set(docs_dir)
    out_files = _relative_file_set(out_dir)
    missing = docs_files - out_files
    # Split: a missing STATIC file is a real regression; a missing GENERATED
    # file is an intentionally-pruned stale artifact (docs/ drifted from the
    # current data.json) and is expected, not a loss.
    lost = {rel for rel in missing if not _is_generator_owned(rel)}
    pruned = missing - lost
    extra = out_files - docs_files

    print()
    print("=" * 64)
    print("[build_site] PARITY CHECK")
    print("=" * 64)
    print(f"  files in docs/ : {len(docs_files)}")
    print(f"  files in out/  : {len(out_files)}")
    print(f"  lost   (static docs/ file MISSING from out/): {len(lost)}")
    print(f"  pruned (stale generated artifact dropped)   : {len(pruned)}")
    print(f"  extra  (out/ but NOT docs/, fresh content)  : {len(extra)}")
    if warned:
        print(f"  generators WARNed: {len(warned)} -> {', '.join(warned)}")
    else:
        print("  generators WARNed: 0")

    if lost:
        print()
        print("  !!! REGRESSION: static docs/ files MISSING from out/:")
        for rel in sorted(lost):
            print(f"      - {rel}")
    else:
        print()
        print("  OK: no static docs/ file is missing from out/. Parity gap is EMPTY.")
        if pruned:
            print(
                f"  ({len(pruned)} stale generated artifact(s) pruned to match "
                "current data.json — expected.)"
            )

    print("=" * 64)
    return lost


def build_site(out_dir: Path, docs_dir: Path, generators: list[dict]) -> set[str]:
    """End-to-end build: seed, generate, parity-check. Returns missing set."""
    print(f"[build_site] docs_dir = {docs_dir}")
    print(f"[build_site] out_dir  = {out_dir}")
    if not docs_dir.is_dir():
        print(f"[build_site] ERROR: docs_dir does not exist: {docs_dir}")
        return set()

    print(f"[build_site] seeding {out_dir} from {docs_dir} (copytree) ...")
    seed_out_dir(docs_dir, out_dir)

    print("[build_site] running generators into out/ (best-effort) ...")
    warned = run_generators(out_dir, generators)

    print("[build_site] restoring any seed files deleted by generators ...")
    restore_deleted_seed(docs_dir, out_dir)

    return parity_check(docs_dir, out_dir, warned)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--out",
        default="_site",
        help="Output directory for the assembled site (default: %(default)s).",
    )
    parser.add_argument(
        "--docs-dir",
        default="docs",
        help="Source docs directory to reproduce (default: %(default)s).",
    )
    args = parser.parse_args(argv)

    # Resolve relative paths against the repo root (parent of scripts/).
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = _REPO_ROOT / out_dir
    out_dir = out_dir.resolve()

    docs_dir = Path(args.docs_dir)
    if not docs_dir.is_absolute():
        docs_dir = _REPO_ROOT / docs_dir
    docs_dir = docs_dir.resolve()

    build_site(out_dir, docs_dir, _generators())
    # Always exit 0 — this is a build tool; the parity report is the signal.
    return 0


if __name__ == "__main__":
    sys.exit(main())
