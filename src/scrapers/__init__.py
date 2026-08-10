"""Venue scraper registry.

Every class exported here is instantiated by
:class:`src.scraper.MultiVenueScraper` and must extend
:class:`src.base_scraper.BaseScraper` (contract documented there).

Most venues need no class at all. Two config-driven registries in
``config/master_config.yaml`` cover them, and adding a venue to either is a
YAML edit with no Python:

- ``static_json_scrapers:`` builds a :class:`StaticJsonScraper` per entry, for
  season-based venues that ship a curated JSON file (Austin Symphony, Early
  Music Austin, La Follia, Austin Chamber Music, Austin Opera, Ballet Austin).
- ``web_llm_scrapers:`` builds a :class:`WebLlmScraper` per entry, for venues
  that publish listings on a live site (galleries, museums, artist pages,
  NowPlayingAustin, ISHIDA Dance). Fetch mode is per-venue: ``http``,
  ``playwright``, or ``perplexity`` for sites that 403 scrapers.

The classes below are the remaining bespoke scrapers, kept because each parses
something structural that generic extraction would only approximate:

- **Live HTML scrape + LLM extraction**: AFS, Hyperreal, Paramount,
  Alienated Majesty, First Light, Libra Books.
- **Perplexity domain search**: Art Austin (site 403s).
- **Disabled**: Arts on Alexander (kept registered for easy re-enable
  via ``config/master_config.yaml``).

Prefer a ``web_llm_scrapers:`` entry over a new class. Only write one when the
site exposes structured data worth parsing directly (JSON-LD, a stable API) or
needs multi-step navigation. If you do need a class:

1. Create ``src/scrapers/<venue>_scraper.py`` extending ``BaseScraper``.
2. Import and re-export it from this file.
3. Register it in :class:`src.scraper.MultiVenueScraper` (two edits:
   the import block and :meth:`scrape_all_venues`).
4. Add a ``venues:`` entry to ``config/master_config.yaml``.
5. Write unit tests in ``tests/test_<venue>_scraper_unit.py``.

See ``CLAUDE.md §Common Development Tasks`` for the full checklist.
"""

from .afs_scraper import AFSScraper
from .alienated_majesty_scraper import AlienatedMajestyBooksScraper
from .art_austin_scraper import ArtAustinScraper
from .arts_on_alexander_scraper import ArtsOnAlexanderScraper
from .first_light_scraper import FirstLightAustinScraper
from .hyperreal_scraper import HyperrealScraper
from .libra_books_scraper import LibraBooksScraper
from .paramount_scraper import ParamountScraper

# Config-driven scraper bases. Neither is instantiated directly here;
# MultiVenueScraper builds one per registry entry in master_config.yaml.
from ._static_json_scraper import StaticJsonScraper
from ._web_llm_scraper import WebLlmScraper

__all__ = [
    "FirstLightAustinScraper",
    "AFSScraper",
    "ArtAustinScraper",
    "HyperrealScraper",
    "AlienatedMajestyBooksScraper",
    "ArtsOnAlexanderScraper",
    "LibraBooksScraper",
    "ParamountScraper",
    "StaticJsonScraper",
    "WebLlmScraper",
]
