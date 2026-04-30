#!/usr/bin/env python3
"""Gate B: run the LLM persona council against the local ``docs/`` tree.

Use case: the pre-push hook under ``.githooks/pre-push`` invokes this
whenever an outgoing commit subject contains the ``[persona-gate]`` tag.
Exits non-zero if any persona's LLM verdict is FAIL — blocking the push.

The script:

1. Spins up ``python -m http.server`` rooted at ``docs/`` on a free port.
2. Copies every persona JSON to a tempdir, rewriting the ``url`` field
   from ``https://hadrien-cornier.github.io/Culture-Calendar/`` to
   ``http://localhost:<port>/``. Persona assertions that ``fetch('data.json')``
   work because the HTTP server serves ``data.json`` alongside ``index.html``.
3. Invokes ``scripts/persona_critique.py`` pointed at the rewritten specs.
4. Returns 0 if all personas PASS, 1 otherwise.

Local preflight only. The post-deploy Gate A (``.github/workflows/
persona-audit.yml``) is the non-blocking audit that runs on every push.
"""
from __future__ import annotations

import argparse
import http.server
import json
import os
import shutil
import socket
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Sequence

LIVE_HOST = "https://hadrien-cornier.github.io/Culture-Calendar/"
DEFAULT_PERSONAS_DIR = Path("personas/live-site")
DEFAULT_DOCS_DIR = Path("docs")
DEFAULT_OUT = Path(".overnight/gate-b-scorecard.md")


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _SilentHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None:  # noqa: A003
        # Swallow access logs so the hook output stays readable.
        pass


def start_server(docs_dir: Path, port: int) -> tuple[socketserver.TCPServer, threading.Thread]:
    """Start an HTTP server on ``port`` rooted at ``docs_dir``. Returns (srv, thread)."""
    os.chdir(docs_dir)

    class _Handler(_SilentHandler):
        pass

    httpd = socketserver.TCPServer(("127.0.0.1", port), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, thread


def rewrite_personas(
    personas_dir: Path, tmp_dir: Path, base_url: str
) -> list[Path]:
    """Copy persona JSONs to ``tmp_dir`` with their ``url`` field rewritten.

    Rewriting strategy: prefix replacement. Anything under the live host
    URL gets its host swapped for ``base_url``; other fields untouched.
    """
    rewritten: list[Path] = []
    for src in sorted(personas_dir.glob("*.json")):
        data = json.loads(src.read_text(encoding="utf-8"))
        url = data.get("url", "")
        if isinstance(url, str) and url.startswith(LIVE_HOST):
            data["url"] = url.replace(LIVE_HOST, base_url, 1)
        elif url == LIVE_HOST.rstrip("/"):
            data["url"] = base_url.rstrip("/")
        dest = tmp_dir / src.name
        dest.write_text(json.dumps(data, indent=2), encoding="utf-8")
        rewritten.append(dest)
    return rewritten


def run_gate(
    personas_dir: Path = DEFAULT_PERSONAS_DIR,
    docs_dir: Path = DEFAULT_DOCS_DIR,
    out_path: Path = DEFAULT_OUT,
    python_exe: str | None = None,
) -> int:
    """Run the full gate. Return 0 on success, non-zero on block."""
    if not personas_dir.is_dir():
        print(f"error: personas dir not found: {personas_dir}", file=sys.stderr)
        return 2
    if not docs_dir.is_dir():
        print(f"error: docs dir not found: {docs_dir}", file=sys.stderr)
        return 2

    port = _pick_free_port()
    base_url = f"http://127.0.0.1:{port}/"
    original_cwd = Path.cwd()

    # Resolve paths BEFORE start_server chdir()s to docs/.
    personas_dir_abs = personas_dir.resolve()
    out_path_abs = out_path.resolve()
    check_script_abs = Path("scripts/check_live_site.py").resolve()
    persona_critique_abs = Path("scripts/persona_critique.py").resolve()

    httpd, thread = start_server(docs_dir, port)
    try:
        # Small wait so SimpleHTTPRequestHandler binds cleanly.
        time.sleep(0.2)

        with tempfile.TemporaryDirectory(prefix="persona-gate-") as tmp:
            tmp_dir = Path(tmp) / "personas"
            tmp_dir.mkdir()
            rewrite_personas(personas_dir_abs, tmp_dir, base_url)

            exe = python_exe or sys.executable
            print(
                f"[persona-gate] serving docs/ at {base_url}; "
                f"running LLM council against {len(list(tmp_dir.iterdir()))} personas."
            )
            cmd = [
                exe,
                str(persona_critique_abs),
                "--out",
                str(out_path_abs),
                "--personas-dir",
                str(tmp_dir),
                "--check-script",
                str(check_script_abs),
            ]
            proc = subprocess.run(cmd, check=False)
            if proc.returncode == 0:
                print(f"[persona-gate] all personas PASS. Scorecard: {out_path_abs}")
                return 0
            print(
                f"[persona-gate] FAIL — at least one persona did not pass. "
                f"Scorecard: {out_path_abs}",
                file=sys.stderr,
            )
            return 1
    finally:
        httpd.shutdown()
        httpd.server_close()
        os.chdir(original_cwd)


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="require_persona_approval.py",
        description=(
            "Run the LLM persona council against docs/ served on localhost. "
            "Exits 0 if all personas PASS; non-zero otherwise. Intended for "
            "invocation from a pre-push git hook when a commit is tagged "
            "[persona-gate]."
        ),
    )
    p.add_argument(
        "--personas-dir",
        type=Path,
        default=DEFAULT_PERSONAS_DIR,
    )
    p.add_argument(
        "--docs-dir",
        type=Path,
        default=DEFAULT_DOCS_DIR,
    )
    p.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
    )
    return p.parse_args(list(argv))


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    return run_gate(
        personas_dir=args.personas_dir,
        docs_dir=args.docs_dir,
        out_path=args.out,
    )


if __name__ == "__main__":
    sys.exit(main())
