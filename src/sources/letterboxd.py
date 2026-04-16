import json
import time
import re
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup


def _slugify(title: str) -> str:
    """Convert title to Letterboxd-style slug."""
    slug = title.lower()
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    slug = slug.strip('-')
    return slug


def fetch_letterboxd_film(title: str, year: int) -> Optional[dict]:
    """
    Fetch film metadata from Letterboxd.

    Uses requests + BeautifulSoup4. Caches to cache/sources/letterboxd/.
    Rate-limited to 1 second between requests.

    Args:
        title: Film title
        year: Release year (used for caching but not in URL)

    Returns:
        {title, rating, review_excerpt, tags, url} or None if not found/error
    """
    slug = _slugify(title)
    cache_dir = Path("cache/sources/letterboxd")
    cache_path = cache_dir / f"{slug}.json"

    if cache_path.exists():
        with open(cache_path, "r") as f:
            return json.load(f)

    time.sleep(1.0)

    url = f"https://letterboxd.com/film/{slug}/"

    try:
        headers = {"User-Agent": "Culture-Calendar/1.0"}
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 404:
            return None
        if response.status_code == 403:
            return None
        if response.status_code == 429:
            return None

        response.raise_for_status()
    except requests.RequestException:
        return None

    try:
        soup = BeautifulSoup(response.content, "html.parser")
    except Exception:
        return None

    # Extract rating from meta tag or data attribute
    rating = None
    rating_meta = soup.find("meta", {"name": "twitter:data1"})
    if rating_meta and rating_meta.get("content"):
        rating_text = rating_meta.get("content", "")
        match = re.search(r"[\d.]+", rating_text)
        if match:
            try:
                rating = float(match.group())
            except ValueError:
                rating = None

    # Extract popular review excerpt
    review_excerpt = None
    review_elem = soup.find("div", class_="review-text")
    if review_elem:
        review_excerpt = review_elem.get_text(strip=True)[:200]

    # Extract tags (Letterboxd uses various tag classes)
    tags = []
    tag_elems = soup.find_all("a", class_="tag")
    for tag_elem in tag_elems[:5]:  # Limit to 5 tags
        tag_text = tag_elem.get_text(strip=True)
        if tag_text:
            tags.append(tag_text)

    result = {
        "title": title,
        "rating": rating,
        "review_excerpt": review_excerpt,
        "tags": tags,
        "url": url,
    }

    cache_dir.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w") as f:
        json.dump(result, f)

    return result
