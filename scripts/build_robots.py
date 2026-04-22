"""Build ``docs/robots.txt`` with an explicit AI-crawler allowlist.

The body allows the general web (``User-agent: *``) and then repeats
``Allow: /`` for each named AI crawler so the intent is unambiguous to
site operators who grep the file: these agents are welcome.

Named crawlers (order is stable for deterministic diffs):

* ``GPTBot``            — OpenAI training crawler
* ``ClaudeBot``         — Anthropic content fetcher
* ``PerplexityBot``     — Perplexity answer engine
* ``CCBot``             — Common Crawl
* ``Google-Extended``   — Google's AI-training opt-in token
* ``Meta-ExternalAgent``— Meta's LLM fetcher
* ``Amazonbot``         — Amazon's generative retrieval agent

The sitemap directive is preserved at the bottom so traditional
crawlers keep their index entry-point.

Stdlib only — no third-party deps.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
OUT_ROBOTS = DOCS_DIR / "robots.txt"

SITE_BASE_URL = "https://hadrien-cornier.github.io/Culture-Calendar/"

AI_CRAWLERS: tuple[str, ...] = (
    "GPTBot",
    "ClaudeBot",
    "PerplexityBot",
    "CCBot",
    "Google-Extended",
    "Meta-ExternalAgent",
    "Amazonbot",
)


def render_robots(
    *,
    base_url: str = SITE_BASE_URL,
    sitemap_filename: str = "sitemap.xml",
    ai_crawlers: Sequence[str] = AI_CRAWLERS,
) -> str:
    """Return the robots.txt body string.

    Each named crawler gets its own ``User-agent`` block with an explicit
    ``Allow: /`` so the allowlist reads as an intentional policy rather
    than an accident of the wildcard rule.
    """
    base = base_url if base_url.endswith("/") else base_url + "/"
    sitemap_url = base + sitemap_filename

    blocks: list[str] = ["User-agent: *", "Allow: /"]
    for agent in ai_crawlers:
        blocks.append("")
        blocks.append(f"User-agent: {agent}")
        blocks.append("Allow: /")

    blocks.append("")
    blocks.append(f"Sitemap: {sitemap_url}")
    return "\n".join(blocks) + "\n"


def write_robots(
    *,
    out_path: Path = OUT_ROBOTS,
    base_url: str = SITE_BASE_URL,
    sitemap_filename: str = "sitemap.xml",
    ai_crawlers: Sequence[str] = AI_CRAWLERS,
) -> Path:
    """Write the rendered robots.txt to ``out_path`` and return the path."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    body = render_robots(
        base_url=base_url,
        sitemap_filename=sitemap_filename,
        ai_crawlers=ai_crawlers,
    )
    out_path.write_text(body, encoding="utf-8")
    return out_path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--out",
        type=Path,
        default=OUT_ROBOTS,
        help="Output path for robots.txt (default: %(default)s).",
    )
    parser.add_argument(
        "--base-url",
        default=SITE_BASE_URL,
        help="Site base URL used for the Sitemap directive.",
    )
    parser.add_argument(
        "--sitemap-filename",
        default="sitemap.xml",
        help="Sitemap filename appended to the base URL.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress the summary line on stdout.",
    )
    args = parser.parse_args(argv)

    path = write_robots(
        out_path=args.out,
        base_url=args.base_url,
        sitemap_filename=args.sitemap_filename,
    )
    if not args.quiet:
        print(f"Wrote {path} ({len(AI_CRAWLERS)} AI crawlers allowlisted)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
