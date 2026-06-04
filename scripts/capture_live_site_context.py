#!/usr/bin/env python3
"""Capture structural live-site context for the LLM council.

This is the thin, *no-LLM* half of the old persona pipeline. Where
``persona_critique.py`` / ``require_persona_approval.py`` used to spin a
localhost server, capture each page, AND call Anthropic per persona to
render a verdict, this script does only the structural-capture step: it
serves ``docs/`` on localhost, runs each spec's asserts and ground-truth
probe via :mod:`check_live_site`, and writes one combined markdown file
that the ``llm-council`` consumes as its ``--context-file``.

The judging itself is delegated to the council — keeping this step free of
API keys and network access (localhost only) so it is safe to run from a
pre-push hook.

Per spec we emit a markdown section containing:

* the persona name + the source spec path,
* the STRUCTURAL verdict (which asserts passed / failed),
* the ground-truth selector JSON block (``{exists, count}`` per selector),
* a trimmed DOM/text snippet (capped per persona).

Graceful degradation: pyppeteer/Chromium may be unavailable. If the
browser cannot launch, we still emit the section using the *static* HTML
fetched from the local server, annotate that dynamic capture was skipped,
and exit 0. The pre-push hook must never hard-crash on this step.

Spec format: the structural specs in ``personas/live-site-specs/*.json``
are the persona JSONs minus the ``llm`` block — i.e. ``persona``, ``url``,
optional ``mobile`` / ``wait_*`` / ``click_before_assert`` /
``pre_screenshot_actions`` / ``ground_truth_selectors``, and ``asserts``.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import http.server
import importlib.util
import json
import os
import socket
import socketserver
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Sequence

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent

DEFAULT_SPECS_DIR = Path("personas/live-site-specs")
DEFAULT_DOCS_DIR = Path("docs")
DEFAULT_OUT = Path(".council/live-site-context.md")

# Live host whose URLs get rewritten to the local server (mirrors
# require_persona_approval.LIVE_HOST). Re-declared here so the rewrite still
# works if that module is unavailable.
LIVE_HOST = "https://hadrien-cornier.github.io/Culture-Calendar/"

# Cap on the DOM/text snippet bytes emitted per persona section.
PER_PERSONA_SNIPPET_CAP = 40_000


def _load_sibling(name: str, filename: str) -> Any:
    """Import a sibling script module by file path (no package install)."""
    path = SCRIPTS_DIR / filename
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"cannot load {filename}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# Reuse the structural engine (capture + ground-truth) verbatim.
check_live_site = _load_sibling("check_live_site", "check_live_site.py")


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _SilentHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None:  # noqa: A003
        pass  # keep pre-push hook output readable


def start_server(docs_dir: Path, port: int):
    """Serve ``docs_dir`` on ``port`` from a daemon thread. Returns (httpd, thread)."""
    os.chdir(docs_dir)
    httpd = socketserver.TCPServer(("127.0.0.1", port), _SilentHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, thread


def rewrite_url(url: str, base_url: str) -> str:
    """Swap the live host prefix of ``url`` for ``base_url``.

    Mirrors require_persona_approval.rewrite_personas' prefix strategy.
    URLs not under the live host are returned unchanged.
    """
    if not isinstance(url, str):
        return url
    if url.startswith(LIVE_HOST):
        return url.replace(LIVE_HOST, base_url, 1)
    if url == LIVE_HOST.rstrip("/"):
        return base_url.rstrip("/")
    return url


def _format_verdict(spec: dict[str, Any], failures: list[Any]) -> str:
    """Render the structural verdict: counts + per-assert PASS/FAIL lines."""
    asserts = spec.get("asserts") or []
    total = len(asserts)
    failed_idx = {f.index: f for f in failures}
    passed = total - len(failed_idx)
    lines = [
        f"Structural verdict: {'PASS' if not failures else 'FAIL'} "
        f"({passed}/{total} asserts passed)"
    ]
    if total == 0:
        lines.append("- (no asserts declared)")
    for i, a in enumerate(asserts):
        a_type = a.get("type", "?") if isinstance(a, dict) else "?"
        if i in failed_idx:
            lines.append(f"- FAIL assert[{i}] ({a_type}): {failed_idx[i].reason}")
        else:
            lines.append(f"- PASS assert[{i}] ({a_type})")
    return "\n".join(lines)


def _trim(text: str, cap: int = PER_PERSONA_SNIPPET_CAP) -> tuple[str, bool]:
    """Trim ``text`` to ``cap`` bytes (utf-8). Returns (text, was_trimmed)."""
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= cap:
        return text, False
    return encoded[:cap].decode("utf-8", errors="ignore"), True


def _fetch_static(url: str) -> str:
    """GET ``url`` (localhost) and return the response body as text.

    Used both as the degraded-capture fallback and is itself the no-browser
    path. Network is localhost-only by construction (the URL was rewritten
    to the local server). Errors are surfaced as a short note string.
    """
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:  # noqa: S310
            raw = resp.read()
        return raw.decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return f"<!-- static fetch failed: {exc} -->"


def capture_spec(spec: dict[str, Any], *, launch: Any = None) -> dict[str, Any]:
    """Run the structural capture for one spec.

    Returns a dict with keys: ``failures`` (list[AssertionFailure]),
    ``ground_truth`` (dict), ``dom`` (str), ``dynamic`` (bool — True if the
    browser capture succeeded, False if we fell back to static HTML), and
    ``note`` (str — degradation reason, empty when dynamic).

    Never raises on browser problems: any capture failure degrades to a
    static GET of the (already-localhost) URL.
    """
    try:
        failures, _b64, dom, ground_truth = asyncio.run(
            check_live_site.run_spec_capture_and_ground_truth(spec, launch=launch)
        )
        return {
            "failures": list(failures),
            "ground_truth": ground_truth or {},
            "dom": dom,
            "dynamic": True,
            "note": "",
        }
    except Exception as exc:  # noqa: BLE001 - browser may be unavailable
        dom = _fetch_static(spec.get("url", ""))
        return {
            "failures": [],
            "ground_truth": {},
            "dom": dom,
            "dynamic": False,
            "note": (
                "Dynamic capture skipped (browser unavailable: "
                f"{type(exc).__name__}: {exc}). "
                "Asserts and ground-truth could not be evaluated; the static "
                "HTML below is the server response only."
            ),
        }


def render_section(
    persona: str, spec_path: Path, spec: dict[str, Any], captured: dict[str, Any]
) -> str:
    """Render one per-persona markdown section."""
    parts: list[str] = []
    parts.append(f"## {persona}")
    parts.append("")
    parts.append(f"- Spec: `{spec_path}`")
    parts.append(f"- URL (rewritten to local server): `{spec.get('url', '')}`")
    desc = spec.get("description")
    if isinstance(desc, str) and desc:
        parts.append(f"- Description: {desc}")
    parts.append("")

    if captured["dynamic"]:
        parts.append(_format_verdict(spec, captured["failures"]))
    else:
        parts.append("Structural verdict: SKIPPED (dynamic capture unavailable)")
        parts.append(f"- NOTE: {captured['note']}")
    parts.append("")

    gt = captured["ground_truth"]
    parts.append("### Ground truth selectors")
    parts.append("")
    parts.append("```json")
    parts.append(json.dumps(gt, indent=2, sort_keys=True))
    parts.append("```")
    parts.append("")

    snippet, trimmed = _trim(captured["dom"])
    label = "DOM snippet (static HTML)" if not captured["dynamic"] else "DOM snippet"
    parts.append(f"### {label}")
    if trimmed:
        parts.append(f"_(trimmed to {PER_PERSONA_SNIPPET_CAP} bytes)_")
    parts.append("")
    parts.append("```html")
    parts.append(snippet)
    parts.append("```")
    parts.append("")
    return "\n".join(parts)


def build_context(
    specs_dir: Path,
    base_url: str,
    *,
    launch: Any = None,
    capture_fn: Any = None,
) -> str:
    """Capture every spec and render the combined context markdown.

    ``capture_fn`` defaults to :func:`capture_spec`; tests inject a mock so
    no browser launches. ``launch`` is forwarded to the default capture_fn.
    """
    if capture_fn is None:

        def capture_fn(spec: dict[str, Any]) -> dict[str, Any]:  # type: ignore[misc]
            return capture_spec(spec, launch=launch)

    spec_paths = sorted(specs_dir.glob("*.json"))
    header = [
        "# Live-site structural context",
        "",
        "Structural capture for the LLM council (no LLM verdict applied here).",
        "Each section reports a persona's structural assert verdict, the "
        "ground-truth selector counts observed on the page, and a trimmed DOM "
        "snippet. The council judges these; this file is mechanical input.",
        "",
        f"Personas captured: {len(spec_paths)}",
        "",
    ]
    sections: list[str] = []
    for spec_path in spec_paths:
        try:
            spec = check_live_site.load_spec(spec_path)
        except (ValueError, json.JSONDecodeError) as exc:
            sections.append(
                f"## {spec_path.stem}\n\n- Spec: `{spec_path}`\n"
                f"- ERROR: invalid spec, skipped ({exc})\n"
            )
            continue
        persona = spec.get("persona") or spec_path.stem
        spec["url"] = rewrite_url(spec.get("url", ""), base_url)
        captured = capture_fn(spec)
        sections.append(render_section(persona, spec_path, spec, captured))
    return "\n".join(header + sections).rstrip() + "\n"


def run(
    specs_dir: Path = DEFAULT_SPECS_DIR,
    docs_dir: Path = DEFAULT_DOCS_DIR,
    out_path: Path = DEFAULT_OUT,
    base_url: str | None = None,
    *,
    launch: Any = None,
    capture_fn: Any = None,
) -> int:
    """Capture context and write it to ``out_path``. Returns process exit code.

    When ``base_url`` is None a localhost http.server is started rooted at
    ``docs_dir`` (see ``start_server`` above) and torn down at exit. When
    ``base_url`` is given the server is skipped.
    """
    if not specs_dir.is_dir():
        # No specs is not a failure — emit an empty-ish context and exit 0 so
        # the pre-push hook never blocks on a missing/forthcoming specs dir.
        print(
            f"[capture] no specs dir at {specs_dir}; writing empty context.",
            file=sys.stderr,
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            "# Live-site structural context\n\n" f"No specs found at `{specs_dir}`.\n",
            encoding="utf-8",
        )
        return 0

    specs_dir_abs = specs_dir.resolve()
    out_path_abs = out_path.resolve()
    original_cwd = Path.cwd()

    httpd = None
    try:
        if base_url is None:
            if not docs_dir.is_dir():
                print(
                    f"[capture] docs dir not found: {docs_dir}; "
                    "writing empty context.",
                    file=sys.stderr,
                )
                out_path_abs.parent.mkdir(parents=True, exist_ok=True)
                out_path_abs.write_text(
                    "# Live-site structural context\n\n"
                    f"docs dir `{docs_dir}` not found.\n",
                    encoding="utf-8",
                )
                return 0
            port = _pick_free_port()
            base_url = f"http://127.0.0.1:{port}/"
            # start_server chdir()s into docs_dir; resolve everything first.
            httpd, _thread = start_server(docs_dir, port)
            print(f"[capture] serving {docs_dir} at {base_url}", file=sys.stderr)

        markdown = build_context(
            specs_dir_abs, base_url, launch=launch, capture_fn=capture_fn
        )
        out_path_abs.parent.mkdir(parents=True, exist_ok=True)
        out_path_abs.write_text(markdown, encoding="utf-8")
        print(f"[capture] wrote live-site context to {out_path_abs}", file=sys.stderr)
        return 0
    finally:
        if httpd is not None:
            with contextlib.suppress(Exception):
                httpd.shutdown()
            with contextlib.suppress(Exception):
                httpd.server_close()
        os.chdir(original_cwd)


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="capture_live_site_context.py",
        description=(
            "Structural-capture step for the LLM council. Serves docs/ on "
            "localhost, runs each live-site spec's asserts + ground-truth "
            "probe, and writes a combined markdown context file. No LLM "
            "calls, no API keys, localhost only. Always exits 0 (degrades "
            "to static HTML if a browser is unavailable) so a pre-push hook "
            "never hard-crashes."
        ),
    )
    p.add_argument("--specs-dir", type=Path, default=DEFAULT_SPECS_DIR)
    p.add_argument("--docs-dir", type=Path, default=DEFAULT_DOCS_DIR)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument(
        "--base-url",
        type=str,
        default=None,
        help="Skip the local server and use this base URL instead.",
    )
    return p.parse_args(list(argv))


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    return run(
        specs_dir=args.specs_dir,
        docs_dir=args.docs_dir,
        out_path=args.out,
        base_url=args.base_url,
    )


if __name__ == "__main__":
    sys.exit(main())
