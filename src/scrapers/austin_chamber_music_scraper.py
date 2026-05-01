"""Austin Chamber Music Festival scraper (static JSON, fanned out per date)."""

from typing import Any, Optional

from src.scrapers._static_json_scraper import StaticJsonScraper


class AustinChamberMusicScraper(StaticJsonScraper):
    def __init__(self, config: Optional[Any] = None, venue_key: str = "austin_chamber_music"):
        super().__init__(
            base_url="https://austinchambermusic.org",
            venue_name="Chamber Music",
            venue_key=venue_key,
            config=config,
            data_file="",
            top_level_key="austinChamberMusic",
            default_event_type="concert",
            default_time="7:30 PM",
            default_location="Austin Chamber Music Center",
            expand_dates=True,
        )
        self.data_file = self.get_project_path("docs", "classical_data.json")
