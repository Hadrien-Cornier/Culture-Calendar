"""Ballet Austin scraper (static JSON, fanned out per date).

Ballet Austin events must be tagged ``type=dance`` so the processor
routes them to the dance-rating handler instead of the classical
prompt — the original bug from CLAUDE.md task-2.1. The
:class:`StaticJsonScraper` resolves type from per-event JSON ➜ venue
config (``master_config.yaml`` declares
``assumed_event_category: dance``) ➜ constructor default. All three
tiers point at ``dance`` for this venue, so the regression is pinned.
"""

from typing import Any, Optional

from src.scrapers._static_json_scraper import StaticJsonScraper


class BalletAustinScraper(StaticJsonScraper):
    def __init__(self, config: Optional[Any] = None, venue_key: str = "ballet_austin"):
        super().__init__(
            base_url="https://balletaustin.org",
            venue_name="BalletAustin",
            venue_key=venue_key,
            config=config,
            data_file="",
            top_level_key="balletAustin",
            default_event_type="dance",
            default_time="7:30 PM",
            default_location="The Long Center",
            expand_dates=True,
        )
        self.data_file = self.get_project_path("docs", "ballet_data.json")
