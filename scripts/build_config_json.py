"""Emit ``docs/config.json`` — the runtime client-side config for the site.

The frontend reads this at load to discover:

- ``buttondown_endpoint`` — the Buttondown mailing-list form URL. Empty
  string means the feature is disabled; the signup form renders a
  "Coming soon" stub instead of POSTing anywhere. Sourced from
  ``config/master_config.yaml`` under ``distribution.buttondown_endpoint``
  (seeded by long-run 20260421-225013 task T0.2).
- ``site_base_url`` — absolute URL of the deployed site, used by JS
  share / analytics code that needs canonical links. Defaults to the
  GitHub Pages host; overridable via ``--base-url`` for previews.

All static output: the file is committed to ``docs/`` and served
alongside ``index.html`` on GitHub Pages. Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
OUT_CONFIG = DOCS_DIR / "config.json"
DEFAULT_CONFIG_YAML = REPO_ROOT / "config" / "master_config.yaml"

SITE_BASE_URL = "https://hadrien-cornier.github.io/Culture-Calendar/"

LOG = logging.getLogger("build_config_json")


def _load_master_config(path: Path) -> Mapping[str, Any]:
    """Return the parsed master_config.yaml mapping, or ``{}`` if missing."""
    if not path.is_file():
        LOG.warning("master_config.yaml not found at %s; using defaults", path)
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, Mapping):
        raise ValueError(f"Expected a mapping at top-level of {path}; got {type(data).__name__}")
    return data


def _extract_buttondown_endpoint(master_config: Mapping[str, Any]) -> str:
    """Return ``distribution.buttondown_endpoint`` as a string, or empty string."""
    distribution = master_config.get("distribution") or {}
    if not isinstance(distribution, Mapping):
        return ""
    value = distribution.get("buttondown_endpoint", "")
    return value if isinstance(value, str) else ""


def build_client_config(
    *,
    master_config: Mapping[str, Any],
    site_base_url: str = SITE_BASE_URL,
) -> dict[str, Any]:
    """Assemble the ``docs/config.json`` payload from master_config."""
    return {
        "buttondown_endpoint": _extract_buttondown_endpoint(master_config),
        "site_base_url": site_base_url,
    }


def write_config(
    payload: Mapping[str, Any],
    *,
    out_path: Path = OUT_CONFIG,
) -> None:
    """Write ``payload`` as pretty-printed JSON to ``out_path``."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    out_path.write_text(text, encoding="utf-8")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_YAML,
        help="Path to master_config.yaml (default: %(default)s).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=OUT_CONFIG,
        help="Output path for config.json (default: %(default)s).",
    )
    parser.add_argument(
        "--base-url",
        default=SITE_BASE_URL,
        help="Site base URL exposed to the client (default: %(default)s).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress the summary line on stdout.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    master_config = _load_master_config(args.config)
    payload = build_client_config(
        master_config=master_config,
        site_base_url=args.base_url,
    )
    write_config(payload, out_path=args.out)

    if not args.quiet:
        print(f"Wrote {args.out} ({len(payload)} keys)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
