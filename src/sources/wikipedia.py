"""Wikipedia fallback source for non-film metadata.

Queries Wikipedia's REST API (``/api/rest_v1/page/summary/<title>``)
for composers, ensembles, venues, and book authors when Perplexity
comes back thin. Returns a shallow dict of ``{title, extract, url}``
callers can use to pad event descriptions with canonical background.

Cached on disk under ``cache/wikipedia/<sha1>.json`` so repeated runs
don't re-hit the API. Cache key is the exact query string, so titles
with punctuation variants will miss and refetch.

No API key required. Wikipedia has a generous rate limit for
anonymous users but we still sleep ~0.2s between calls to be polite.
"""

import json
import os
import time
import urllib.request
import urllib.parse
from hashlib import sha1
from pathlib import Path
from typing import Optional


def fetch_wikipedia(query: str) -> Optional[dict]:
    """
    Fetch Wikipedia article extract for a given query.

    Uses only stdlib (urllib, json, hashlib). Caches to cache/sources/wikipedia/.
    Rate-limited to 1 second between requests.

    Args:
        query: Wikipedia article title or search term

    Returns:
        {title, extract, url} or None if not found
    """
    cache_dir = Path("cache/sources/wikipedia")
    cache_key = sha1(query.encode()).hexdigest()
    cache_path = cache_dir / f"{cache_key}.json"

    if cache_path.exists():
        with open(cache_path, "r") as f:
            return json.load(f)

    time.sleep(1.0)

    params = {
        "action": "query",
        "prop": "extracts|pageprops",
        "exintro": "true",
        "explaintext": "true",
        "redirects": "true",
        "titles": query,
        "format": "json"
    }

    url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(params)

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Culture-Calendar/1.0"}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
    except Exception:
        return None

    pages = data.get("query", {}).get("pages", {})
    if not pages:
        return None

    page = list(pages.values())[0]
    if "missing" in page or "invalid" in page:
        return None

    result = {
        "title": page.get("title", ""),
        "extract": page.get("extract", ""),
        "url": f"https://en.wikipedia.org/wiki/{urllib.parse.quote(page.get('title', ''))}"
    }

    cache_dir.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w") as f:
        json.dump(result, f)

    return result
