"""Venue scraper registry.

Every class exported here is instantiated by
:class:`src.scraper.MultiVenueScraper` and must extend
:class:`src.base_scraper.BaseScraper` (contract documented there).
Scraper categories:

- **Live HTML scrape + LLM extraction**: AFS, Hyperreal, Paramount,
  Alienated Majesty, First Light, Libra Books.
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
from .austin_chamber_music_scraper import AustinChamberMusicScraper
from .austin_opera_scraper import AustinOperaScraper
from .austin_symphony_scraper import AustinSymphonyScraper
from .ballet_austin_scraper import BalletAustinScraper
from .early_music_scraper import EarlyMusicAustinScraper
from .first_light_scraper import FirstLightAustinScraper
from .hyperreal_scraper import HyperrealScraper
from .la_follia_scraper import LaFolliaAustinScraper
from .libra_books_scraper import LibraBooksScraper
from .now_playing_austin_visual_arts_scraper import NowPlayingAustinVisualArtsScraper
from .paramount_scraper import ParamountScraper

__all__ = [
    "FirstLightAustinScraper",
    "AFSScraper",
    "HyperrealScraper",
    "AlienatedMajestyBooksScraper",
    "ArtsOnAlexanderScraper",
    "AustinChamberMusicScraper",
    "AustinOperaScraper",
    "AustinSymphonyScraper",
    "BalletAustinScraper",
    "EarlyMusicAustinScraper",
    "LaFolliaAustinScraper",
    "LibraBooksScraper",
    "NowPlayingAustinVisualArtsScraper",
    "ParamountScraper",
]
