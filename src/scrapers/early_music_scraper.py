"""Texas Early Music Project scraper (static JSON, fanned out per date)."""

from typing import Any, Optional

from src.scrapers._static_json_scraper import StaticJsonScraper


class EarlyMusicAustinScraper(StaticJsonScraper):
    def __init__(self, config: Optional[Any] = None, venue_key: str = "early_music_austin"):
        super().__init__(
            base_url="https://www.early-music.org",
            venue_name="EarlyMusic",
            venue_key=venue_key,
            config=config,
            data_file="",
            top_level_key="earlyMusicAustin",
            default_event_type="concert",
            default_time="7:30 PM",
            default_location="Various Austin Venues",
            expand_dates=True,
        )
        self.data_file = self.get_project_path("docs", "classical_data.json")
