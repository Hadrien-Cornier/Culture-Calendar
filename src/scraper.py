import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Dict, List

# Import config loader
from .config_loader import ConfigLoader

# Import all new LLM-powered scrapers
from .scrapers import (
    AFSScraper,
    AlienatedMajestyBooksScraper,
    ArtsOnAlexanderScraper,
    AustinChamberMusicScraper,
    AustinOperaScraper,
    AustinSymphonyScraper,
    BalletAustinScraper,
    EarlyMusicAustinScraper,
    FirstLightAustinScraper,
    HyperrealScraper,
    LaFolliaAustinScraper,
    ParamountScraper,
)
from .recurring_events import RecurringEventGenerator


class MultiVenueScraper:
    """
    Unified scraper for all supported venues using LLM-powered architecture
    """

    def __init__(self):
        # Load configuration
        self.config = ConfigLoader()
        print("Loaded master configuration")

        # Initialize all scrapers with config
        self.afs_scraper = AFSScraper(config=self.config, venue_key="afs")
        self.hyperreal_scraper = HyperrealScraper(
            config=self.config, venue_key="hyperreal"
        )
        self.paramount_scraper = ParamountScraper(
            config=self.config, venue_key="paramount"
        )
        self.alienated_majesty_scraper = AlienatedMajestyBooksScraper(
            config=self.config, venue_key="alienated_majesty"
        )
        self.first_light_scraper = FirstLightAustinScraper(
            config=self.config, venue_key="first_light"
        )
        self.arts_on_alexander_scraper = ArtsOnAlexanderScraper(
            config=self.config, venue_key="arts_on_alexander"
        )
        self.austin_symphony_scraper = AustinSymphonyScraper(
            config=self.config, venue_key="austin_symphony"
        )
        self.austin_opera_scraper = AustinOperaScraper(
            config=self.config, venue_key="austin_opera"
        )
        self.austin_chamber_music_scraper = AustinChamberMusicScraper(
            config=self.config, venue_key="austin_chamber_music"
        )
        self.early_music_scraper = EarlyMusicAustinScraper(
            config=self.config, venue_key="early_music_austin"
        )
        self.la_follia_scraper = LaFolliaAustinScraper(
            config=self.config, venue_key="la_follia"
        )
        self.ballet_austin_scraper = BalletAustinScraper(
            config=self.config, venue_key="ballet_austin"
        )

        # Initialize recurring events generator
        self.recurring_events_generator = RecurringEventGenerator()

        self.existing_events_cache = set()  # Cache for duplicate detection
        self.last_updated = {}

    def scrape_all_venues(
        self, target_week: bool = False, days_ahead: int = None
    ) -> List[Dict]:
        """Scrape all venues sequentially"""
        start_time = datetime.now()

        all_events = []
        self.last_updated = {}

        # Define all venue scrapers with their configurations
        venue_configs = [
            ("AFS", self.afs_scraper, "Austin Movie Society", {}),
            ("Hyperreal", self.hyperreal_scraper, "Hyperreal Movie Club", {"days_ahead": days_ahead} if days_ahead else {}),
            # ("Paramount", self.paramount_scraper, "Paramount Theatre", {}),
            # ("AlienatedMajesty", self.alienated_majesty_scraper, "Alienated Majesty Books", {}),
            # ("FirstLight", self.first_light_scraper, "First Light Austin", {}),
            (
                "ArtsOnAlexander",
                self.arts_on_alexander_scraper,
                "Arts on Alexander",
                {},
            ),
            ("Symphony", self.austin_symphony_scraper, "Austin Symphony", {}),
            ("Opera", self.austin_opera_scraper, "Austin Opera", {}),
            (
                "Chamber Music",
                self.austin_chamber_music_scraper,
                "Austin Chamber Music",
                {},
            ),
            ("EarlyMusic", self.early_music_scraper, "Early Music Project", {}),
            ("LaFollia", self.la_follia_scraper, "La Follia", {}),
            ("BalletAustin", self.ballet_austin_scraper, "Ballet Austin", {}),
        ]

        # Execute all venue scrapers sequentially (no threading)
        start_time = datetime.now()
        all_events = []
        self.last_updated = {}

        completed_venues = 0
        total_venues = len(venue_configs)

        for venue_code, scraper, display_name, kwargs in venue_configs:
            completed_venues += 1
            try:
                events = scraper.scrape_events(**kwargs)

                # Format and validate events according to config
                formatted_events = []
                for event in events:
                    try:
                        # Format event according to config
                        formatted_event = scraper.format_event(event)
                        # Validate event
                        scraper.validate_event(formatted_event)
                        # Add venue information
                        formatted_event["venue"] = venue_code
                        formatted_events.append(formatted_event)
                    except ValueError as e:
                        print(f"  ⚠️  Event validation error for {venue_code}: {e}")
                        # Skip invalid events in Phase One
                        continue

                all_events.extend(formatted_events)

                print(
                    f"✅ [{completed_venues}/{total_venues}] {display_name}: {len(events)} events"
                )
                self.last_updated[venue_code] = datetime.now().isoformat()

            except Exception as e:
                print(
                    f"❌ [{completed_venues}/{total_venues}] {display_name}: Failed - {e}"
                )
                self.last_updated[venue_code] = None

        elapsed_time = (datetime.now() - start_time).total_seconds()
        print(
            f"🎯 SEQUENTIAL SCRAPING COMPLETE: {len(all_events)} events in {elapsed_time:.1f}s"
        )

        # Add recurring events
        all_events.extend(self._get_recurring_events(target_week))

        # No date filtering applied - all events preserved

        return all_events

    def _get_recurring_events(self, target_week: bool = False) -> List[Dict]:
        """Generate recurring events"""
        try:
            print("Generating recurring events...")
            weeks_ahead = 2 if target_week else 8
            recurring_events = (
                self.recurring_events_generator.generate_all_recurring_events(
                    weeks_ahead
                )
            )
            print(f"Generated {len(recurring_events)} recurring events")
            self.last_updated["RecurringEvents"] = datetime.now().isoformat()
            return recurring_events
        except Exception as e:
            print(f"Error generating recurring events: {e}")
            self.last_updated["RecurringEvents"] = None
            return []

    def load_existing_events(self, existing_data_path: str = None) -> None:
        """Load existing events to cache for duplicate detection"""
        # Original sequential implementation
        if not existing_data_path:
            existing_data_path = (
                "/Users/HCornier/Documents/Github/Culture-Calendar/docs/data.json"
            )

        try:
            if os.path.exists(existing_data_path):
                with open(existing_data_path, "r", encoding="utf-8") as f:
                    existing_data = json.load(f)

                # Create cache of event identifiers
                for event in existing_data:
                    if "screenings" in event:
                        for screening in event["screenings"]:
                            event_id = self._create_event_id(
                                event["title"],
                                screening["date"],
                                screening["time"],
                                event.get("venue", ""),
                            )
                            self.existing_events_cache.add(event_id)

                print(
                    f"Loaded {len(self.existing_events_cache)} existing events for duplicate detection"
                )
        except Exception as e:
            print(
                f"Warning: Could not load existing events for duplicate detection: {e}"
            )

    def _create_event_id(self, title: str, date: str, time: str, venue: str) -> str:
        """Create a unique identifier for an event"""
        # Normalize data for consistent comparison
        normalized_title = (title or "").strip().lower()
        normalized_venue = (venue or "").strip().lower()
        normalized_time = (time or "").strip().lower()
        return f"{normalized_title}_{date}_{normalized_time}_{normalized_venue}"

    def _is_duplicate_event(self, title: str, date: str, time: str, venue: str) -> bool:
        """Check if an event is a duplicate of an existing event"""
        event_id = self._create_event_id(title, date, time, venue)
        return event_id in self.existing_events_cache

    def scrape_new_events_only(
        self, target_week: bool = False, existing_data_path: str = None
    ) -> List[Dict]:
        """
        Scrape only new events that don't already exist
        """
        # Load existing events for duplicate detection
        self.load_existing_events(existing_data_path)

        # Get all events
        all_events = self.scrape_all_venues(target_week)

        # Filter out duplicates
        new_events = []
        duplicate_count = 0

        for event in all_events:
            # Handle both array and singular formats
            dates = event.get("dates", [])
            times = event.get("times", [])

            # Fallback to singular format
            if not dates and "date" in event:
                dates = [event["date"]]
            if not times and "time" in event:
                times = [event["time"]]

            # Check each date/time combination for duplicates
            is_duplicate = False
            for i, date in enumerate(dates):
                time = times[i] if i < len(times) else times[0] if times else "TBD"
                if self._is_duplicate_event(
                    event["title"], date, time, event.get("venue", "")
                ):
                    is_duplicate = True
                    break

            if not is_duplicate:
                new_events.append(event)
                # Add all date/time combinations to cache
                for i, date in enumerate(dates):
                    time = times[i] if i < len(times) else times[0] if times else "TBD"
                    event_id = self._create_event_id(
                        event["title"], date, time, event.get("venue", "")
                    )
                    self.existing_events_cache.add(event_id)
            else:
                duplicate_count += 1

        print(
            f"Found {len(new_events)} new events ({duplicate_count} duplicates filtered out)"
        )
        return new_events

    def get_event_details(self, event: Dict) -> Dict:
        """Get event details using appropriate scraper based on venue"""
        venue = event.get("venue", "AFS")

        # Recurring events already have all necessary details
        if event.get("is_recurring"):
            return {}

        if venue == "Hyperreal":
            return self.hyperreal_scraper.get_event_details(event["url"])
        elif venue == "Symphony":
            return self.symphony_scraper.get_event_details(event)
        elif venue == "EarlyMusic":
            return self.early_music_scraper.get_event_details(event)
        elif venue == "LaFollia":
            return self.la_follia_scraper.get_event_details(event)
        elif venue == "AlienatedMajesty":
            return self.alienated_majesty_scraper.get_event_details(event)
        elif venue == "FirstLight":
            return self.first_light_scraper.get_event_details(event)
        elif venue == "Paramount":
            return self.paramount_scraper.get_event_details(event)
        else:
            return self.afs_scraper.get_event_details(event["url"])
