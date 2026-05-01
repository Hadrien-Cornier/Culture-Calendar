"""La Follia Austin chamber music scraper (static JSON, fanned out per date)."""

from typing import Any, Optional

from src.scrapers._static_json_scraper import StaticJsonScraper


class LaFolliaAustinScraper(StaticJsonScraper):
    def __init__(self, config: Optional[Any] = None, venue_key: str = "la_follia"):
        super().__init__(
            base_url="https://www.lafolliaaustin.org",
            venue_name="LaFollia",
            venue_key=venue_key,
            config=config,
            data_file="",
            top_level_key="laFolliaAustin",
            default_event_type="concert",
            default_time="7:30 PM",
            default_location="Various Austin Venues",
            expand_dates=True,
        )
        self.data_file = self.get_project_path("docs", "classical_data.json")
