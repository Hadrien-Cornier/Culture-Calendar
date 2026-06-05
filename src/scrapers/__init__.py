"""Venue scraper registry.

Every class exported here is instantiated by
:class:`src.scraper.MultiVenueScraper` and must extend
:class:`src.base_scraper.BaseScraper` (contract documented there).
Scraper categories:

- **Live HTML scrape + LLM extraction**: AFS, Hyperreal, Paramount,
  Alienated Majesty, First Light, Libra Books.
- **Live HTML + JSON-LD scrape (no LLM)**: ISHIDA Dance (homepage →
  ThunderTix schema.org Event JSON-LD + performances table).
- **Static JSON (season files, manually curated)**: Austin Symphony,
  Early Music Austin, La Follia, Austin Chamber Music, Austin Opera,
  Ballet Austin, NowPlaying Austin Visual Arts.
- **Disabled**: Arts on Alexander (kept registered for easy re-enable
  via ``config/master_config.yaml``).

To add a new scraper:

1. Create ``src/scrapers/<venue>_scraper.py`` extending ``BaseScraper``.
2. Import and re-export it from this file.
3. Register it in :class:`src.scraper.MultiVenueScraper` (two edits:
   the import block and :meth:`scrape_all_venues`).
4. Add a ``venues:`` entry to ``config/master_config.yaml``.
5. Write unit tests in ``tests/test_<venue>_scraper_unit.py``.

See ``CLAUDE.md §Adding a New Venue`` for the full checklist.
"""

from .afs_scraper import AFSScraper
from .alienated_majesty_scraper import AlienatedMajestyBooksScraper
from .arts_on_alexander_scraper import ArtsOnAlexanderScraper
from .first_light_scraper import FirstLightAustinScraper
from .hyperreal_scraper import HyperrealScraper
from .ishida_dance_scraper import IshidaDanceScraper
from .libra_books_scraper import LibraBooksScraper
from .now_playing_austin_visual_arts_scraper import NowPlayingAustinVisualArtsScraper
from .paramount_scraper import ParamountScraper

# Season-based venues (Austin Symphony, Early Music, La Follia, Austin Chamber
# Music, Austin Opera, Ballet Austin) no longer have per-venue wrapper classes:
# they are config-driven StaticJsonScraper instances built by
# MultiVenueScraper from master_config's `static_json_scrapers` block.
from ._static_json_scraper import StaticJsonScraper

__all__ = [
    "FirstLightAustinScraper",
    "AFSScraper",
    "HyperrealScraper",
    "AlienatedMajestyBooksScraper",
    "ArtsOnAlexanderScraper",
    "IshidaDanceScraper",
    "LibraBooksScraper",
    "NowPlayingAustinVisualArtsScraper",
    "ParamountScraper",
    "StaticJsonScraper",
]
