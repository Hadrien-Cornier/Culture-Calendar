"""Austin Symphony Orchestra scraper (static JSON).

Thin subclass of :class:`StaticJsonScraper` — Symphony preserves the
parallel ``dates`` / ``times`` arrays on the standardized event because
its downstream consumer iterates them itself.
"""

from typing import Any, Optional

from src.scrapers._static_json_scraper import StaticJsonScraper


class AustinSymphonyScraper(StaticJsonScraper):
    def __init__(self, config: Optional[Any] = None, venue_key: str = "austin_symphony"):
        super().__init__(
            base_url="https://austinsymphony.org",
            venue_name="Symphony",
            venue_key=venue_key,
            config=config,
            data_file="",
            top_level_key="austinSymphony",
            default_event_type="concert",
            default_time="8:00 PM",
            default_location="Dell Hall at Long Center",
            expand_dates=False,
        )
        self.data_file = self.get_project_path("docs", "classical_data.json")
