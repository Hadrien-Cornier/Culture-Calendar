"""Emit ``docs/.well-known/ai-agent.json`` — a discovery manifest for AI agents.

The manifest is the agent-oriented analogue of ``sitemap.xml`` + ``llms.txt``:
a single JSON document an autonomous client can fetch at a well-known path
to discover every structured surface this site offers (feeds, JSON APIs,
per-event canonical JSON, llmstxt corpus, etc.) without crawling HTML.

The schema is hand-rolled — there is no single ratified standard for this
file yet; we align loosely with the ``/.well-known/`` convention (RFC 8615)
and with the emerging llmstxt.org and ``ai-plugin.json`` practices. The
payload is deliberately forward-compatible: unknown top-level keys should
be ignored by clients.

Top-level shape::

    {
      "schema_version": "1",
      "name": "Culture Calendar",
      "description": "...",
      "site_url": "https://hadrien-cornier.github.io/Culture-Calendar/",
      "contact": {"type": "github", "url": "..."},
      "policies": {"robots_txt": "...", "license": "..."},
      "endpoints": [
          {"id": "...", "title": "...", "url": "...",
           "content_type": "...", "method": "GET", "agent_usage": "..."},
          ...
      ],
      "generated_at": "2026-04-22T06:00:00Z"
    }

Stdlib only — no new deps.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
WELL_KNOWN_DIR = DOCS_DIR / ".well-known"
OUT_PATH = WELL_KNOWN_DIR / "ai-agent.json"

SCHEMA_VERSION = "1"
SITE_NAME = "Culture Calendar"
SITE_DESCRIPTION = (
    "Austin cultural events, AI-curated. Films, concerts, opera, ballet, "
    "book clubs, and visual arts — sorted by merit, not marketing."
)
SITE_BASE_URL = "https://hadrien-cornier.github.io/Culture-Calendar/"
CONTACT_URL = "https://github.com/Hadrien-Cornier/Culture-Calendar"
LICENSE_LABEL = "MIT"

LOG = logging.getLogger("build_ai_agent_manifest")


@dataclass(frozen=True)
class Endpoint:
    """One structured surface advertised to agents.

    Fields mirror the emerging ``ai-plugin.json`` vocabulary (``id``,
    ``url``, ``content_type``) but we add ``agent_usage`` for a short
    natural-language hint about when to fetch each one.
    """

    id: str
    title: str
    url: str
    content_type: str
    agent_usage: str
    method: str = "GET"
    params: tuple[str, ...] = field(default_factory=tuple)

    def to_payload(self) -> dict:
        payload = {
            "id": self.id,
            "title": self.title,
            "url": self.url,
            "content_type": self.content_type,
            "method": self.method,
            "agent_usage": self.agent_usage,
        }
        if self.params:
            payload["params"] = list(self.params)
        return payload


def _absolute_url(rel: str, *, base_url: str = SITE_BASE_URL) -> str:
    base = base_url if base_url.endswith("/") else base_url + "/"
    if not rel:
        return base
    if rel.startswith("http://") or rel.startswith("https://"):
        return rel
    return base + rel.lstrip("/")


def build_endpoints(*, base_url: str = SITE_BASE_URL) -> list[Endpoint]:
    """Return the static list of endpoints advertised to agents.

    Order is stable — clients that cache the manifest can diff by ``id``.
    """
    return [
        Endpoint(
            id="llms_index",
            title="llmstxt.org index",
            url=_absolute_url("llms.txt", base_url=base_url),
            content_type="text/plain",
            agent_usage=(
                "Start here: short llmstxt.org-formatted index of every "
                "page and feed on the site."
            ),
        ),
        Endpoint(
            id="llms_full",
            title="Full text corpus",
            url=_absolute_url("llms-full.txt", base_url=base_url),
            content_type="text/plain",
            agent_usage=(
                "Plain-text dump of the top events with HTML stripped. Use "
                "when you want to reason over the corpus without fetching "
                "per-event pages."
            ),
        ),
        Endpoint(
            id="api_events",
            title="All events (JSON)",
            url=_absolute_url("api/events.json", base_url=base_url),
            content_type="application/json",
            agent_usage=(
                "Structured view of every event. Wrapper: "
                "{generated_at, site_url, count, data: [...]}."
            ),
        ),
        Endpoint(
            id="api_top_picks",
            title="Top picks (JSON)",
            url=_absolute_url("api/top-picks.json", base_url=base_url),
            content_type="application/json",
            agent_usage=(
                "Only events rated >= 7, sorted by rating. Use for "
                "recommendation answers."
            ),
        ),
        Endpoint(
            id="api_venues",
            title="Venues (JSON)",
            url=_absolute_url("api/venues.json", base_url=base_url),
            content_type="application/json",
            agent_usage=(
                "One row per venue with event count and categories."
            ),
        ),
        Endpoint(
            id="api_people",
            title="People (JSON)",
            url=_absolute_url("api/people.json", base_url=base_url),
            content_type="application/json",
            agent_usage=(
                "One row per composer, director, or author with event "
                "counts and deep-link URLs."
            ),
        ),
        Endpoint(
            id="api_categories",
            title="Categories (JSON)",
            url=_absolute_url("api/categories.json", base_url=base_url),
            content_type="application/json",
            agent_usage="One row per event category with its human label and count.",
        ),
        Endpoint(
            id="event_canonical_json",
            title="Per-event canonical JSON (template)",
            url=_absolute_url("events/{slug}.json", base_url=base_url),
            content_type="application/json",
            agent_usage=(
                "Mirror of the schema.org Event JSON-LD for a single event. "
                "Replace {slug} with the event id. Slugs are enumerated in "
                "api/events.json."
            ),
            params=("slug",),
        ),
        Endpoint(
            id="rss_top_picks",
            title="RSS — top picks",
            url=_absolute_url("feed.xml", base_url=base_url),
            content_type="application/rss+xml",
            agent_usage="RSS 2.0 feed of the top-ranked events.",
        ),
        Endpoint(
            id="ical_all",
            title="iCalendar — all events",
            url=_absolute_url("calendar.ics", base_url=base_url),
            content_type="text/calendar",
            agent_usage="Every event as a subscribable calendar.",
        ),
        Endpoint(
            id="ical_top_picks",
            title="iCalendar — top picks",
            url=_absolute_url("top-picks.ics", base_url=base_url),
            content_type="text/calendar",
            agent_usage="Only the top-ranked events as a subscribable calendar.",
        ),
        Endpoint(
            id="sitemap",
            title="XML sitemap",
            url=_absolute_url("sitemap.xml", base_url=base_url),
            content_type="application/xml",
            agent_usage="Standard sitemap.xml enumerating every HTML page.",
        ),
    ]


def build_manifest(
    *,
    base_url: str = SITE_BASE_URL,
    now: Optional[datetime] = None,
) -> dict:
    """Assemble the manifest payload."""
    generated_at = (now or datetime.now(tz=timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    endpoints = [endpoint.to_payload() for endpoint in build_endpoints(base_url=base_url)]
    return {
        "schema_version": SCHEMA_VERSION,
        "name": SITE_NAME,
        "description": SITE_DESCRIPTION,
        "site_url": _absolute_url("", base_url=base_url),
        "contact": {
            "type": "github",
            "url": CONTACT_URL,
        },
        "policies": {
            "robots_txt": _absolute_url("robots.txt", base_url=base_url),
            "license": LICENSE_LABEL,
        },
        "endpoints": endpoints,
        "generated_at": generated_at,
    }


def write_manifest(
    payload: Mapping[str, object],
    *,
    out_path: Path = OUT_PATH,
) -> int:
    """Write ``payload`` as pretty-printed JSON and return byte-count."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=False) + "\n"
    out_path.write_text(text, encoding="utf-8")
    return len(text)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--out",
        type=Path,
        default=OUT_PATH,
        help="Output path for ai-agent.json (default: %(default)s).",
    )
    parser.add_argument(
        "--base-url",
        default=SITE_BASE_URL,
        help="Site base URL used for absolute links.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress the summary line on stdout.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    payload = build_manifest(base_url=args.base_url)
    written = write_manifest(payload, out_path=args.out)

    if not args.quiet:
        print(
            f"Wrote {args.out} ({written} bytes, "
            f"{len(payload['endpoints'])} endpoints)"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
