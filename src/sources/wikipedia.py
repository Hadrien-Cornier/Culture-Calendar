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
