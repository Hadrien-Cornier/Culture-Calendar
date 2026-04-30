"""Austin Opera scraper (static JSON, fanned out per date)."""

from typing import Any, Optional

from src.scrapers._static_json_scraper import StaticJsonScraper


class AustinOperaScraper(StaticJsonScraper):
    def __init__(self, config: Optional[Any] = None, venue_key: str = "austin_opera"):
        super().__init__(
            base_url="https://austinopera.org",
            venue_name="Opera",
            venue_key=venue_key,
            config=config,
            data_file="",
            top_level_key="austinOpera",
            default_event_type="opera",
            default_time="8:00 PM",
            default_location="Long Center for the Performing Arts",
            expand_dates=True,
        )
        self.data_file = self.get_project_path("docs", "classical_data.json")
