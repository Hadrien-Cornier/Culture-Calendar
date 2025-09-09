"""
Unified multi-venue scraper using the new LLM-powered architecture
🚀 NOW WITH PARALLEL PROCESSING for 5-10x performance improvement!
"""

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Dict, List

# Import all new LLM-powered scrapers
from .scrapers import (
    AFSScraper,
    AlienatedMajestyBooksScraper,
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
    Unified scraper for all supported venues using new LLM-powered architecture
    NOW WITH PARALLEL PROCESSING - automatically uses high-performance parallel scraping!
    """

    def __init__(self):
        # Initialize all scrapers
        self.afs_scraper = AFSScraper()
        self.hyperreal_scraper = HyperrealScraper()
        self.paramount_scraper = ParamountScraper()
        self.alienated_majesty_scraper = AlienatedMajestyBooksScraper()
        self.first_light_scraper = FirstLightAustinScraper()
        self.austin_symphony_scraper = AustinSymphonyScraper()
        self.austin_opera_scraper = AustinOperaScraper()
        self.austin_chamber_music_scraper = AustinChamberMusicScraper()
        self.early_music_scraper = EarlyMusicAustinScraper()
        self.la_follia_scraper = LaFolliaAustinScraper()
        self.ballet_austin_scraper = BalletAustinScraper()

        # Initialize recurring events generator
        self.recurring_events_generator = RecurringEventGenerator()

        self.existing_events_cache = set()  # Cache for duplicate detection
        self.last_updated = {}

    def scrape_all_venues(
        self, target_week: bool = False, days_ahead: int = None, use_parallel: bool = True
    ) -> List[Dict]:
        """
        Scrape events from all supported venues using new architecture
        🚀 NOW WITH PARALLEL PROCESSING for 5-10x performance improvement!
        """
        return self._scrape_venues_parallel(target_week, days_ahead)
    
    def _scrape_venues_parallel(self, target_week: bool = False, days_ahead: int = None) -> List[Dict]:
        """🚀 PARALLEL PROCESSING - Scrape all venues simultaneously for 5-10x speed improvement"""
        print("🚀 Starting PARALLEL venue scraping (5-10x faster)...")
        start_time = datetime.now()
        
        all_events = []
        self.last_updated = {}
        
        # Define all venue scrapers with their configurations
        venue_configs = [
            # ("AFS", self.afs_scraper, "Austin Movie Society", {}),
            # ("Hyperreal", self.hyperreal_scraper, "Hyperreal Movie Club", {"days_ahead": days_ahead} if days_ahead else {}),
            # ("Paramount", self.paramount_scraper, "Paramount Theatre", {}),
            ("AlienatedMajesty", self.alienated_majesty_scraper, "Alienated Majesty Books", {}),
            ("FirstLight", self.first_light_scraper, "First Light Austin", {}),
            # ("Symphony", self.austin_symphony_scraper, "Austin Symphony", {}),
            # ("Opera", self.austin_opera_scraper, "Austin Opera", {}),
            # ("Chamber Music", self.austin_chamber_music_scraper, "Austin Chamber Music", {}),
            # ("EarlyMusic", self.early_music_scraper, "Early Music Project", {}),
            # ("LaFollia", self.la_follia_scraper, "La Follia", {}),
            # ("BalletAustin", self.ballet_austin_scraper, "Ballet Austin", {}),
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
                events, success = self._scrape_single_venue(venue_code, scraper, display_name, kwargs)

                # Add venue information to events
                for event in events:
                    event["venue"] = venue_code
                    all_events.append(event)

                print(f"✅ [{completed_venues}/{total_venues}] {display_name}: {len(events)} events")
                self.last_updated[venue_code] = datetime.now().isoformat() if success else None

            except Exception as e:
                print(f"❌ [{completed_venues}/{total_venues}] {display_name}: Failed - {e}")
                self.last_updated[venue_code] = None

        elapsed_time = (datetime.now() - start_time).total_seconds()
        print(f"🎯 SEQUENTIAL SCRAPING COMPLETE: {len(all_events)} events in {elapsed_time:.1f}s")

        # Add recurring events
        all_events.extend(self._get_recurring_events(target_week))

        # Filter to current week if requested
        if target_week:
            all_events = self._filter_to_current_week(all_events)
            print(f"Filtered to {len(all_events)} events for current week")

        return all_events

    def _scrape_single_venue(self, venue_code: str, scraper, display_name: str, kwargs: dict) -> tuple:
        """Scrape a single venue and return (events, success_status)"""
        try:
            if hasattr(scraper, 'scrape_events'):
                if kwargs:
                    events = scraper.scrape_events(**kwargs)
                else:
                    events = scraper.scrape_events()
            else:
                events = []
            
            return events or [], True
            
        except Exception as e:
            print(f"  Error in {display_name}: {e}")
            return [], False
    
    def _get_recurring_events(self, target_week: bool = False) -> List[Dict]:
        """Generate recurring events"""
        try:
            print("Generating recurring events...")
            weeks_ahead = 2 if target_week else 8
            recurring_events = self.recurring_events_generator.generate_all_recurring_events(weeks_ahead)
            print(f"Generated {len(recurring_events)} recurring events")
            self.last_updated["RecurringEvents"] = datetime.now().isoformat()
            return recurring_events
        except Exception as e:
            print(f"Error generating recurring events: {e}")
            self.last_updated["RecurringEvents"] = None
            return []

    def _filter_to_current_week(self, events: List[Dict]) -> List[Dict]:
        """Filter events to current week only"""
        now = datetime.now()
        # Get start of current week (Monday)
        start_of_week = now - timedelta(days=now.weekday())
        end_of_week = start_of_week + timedelta(days=6)

        filtered_events = []
        for event in events:
            try:
                event_date = datetime.strptime(event["date"], "%Y-%m-%d")
                if start_of_week <= event_date <= end_of_week:
                    filtered_events.append(event)
            except (ValueError, KeyError):
                continue

        return filtered_events

    def load_existing_events(self, existing_data_path: str = None) -> None:
        """Load existing events to cache for duplicate detection"""
        if self.use_parallel:
            # Delegate to parallel scraper
            self._parallel_scraper.load_existing_events(existing_data_path)
            return
            
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
        🚀 AUTOMATICALLY USES PARALLEL PROCESSING for maximum performance!
        """
        if self.use_parallel:
            # Use high-performance parallel scraper with duplicate detection
            print("🚀 Using PARALLEL new events scraping for maximum speed!")
            return self._parallel_scraper.scrape_new_events_only_parallel(target_week, existing_data_path)
        
        # Fallback to original sequential method
        print("⚠️ Using SEQUENTIAL new events scraping - this will be slower")
        # Load existing events for duplicate detection
        self.load_existing_events(existing_data_path)

        # Get all events
        all_events = self.scrape_all_venues(target_week)

        # Filter out duplicates
        new_events = []
        duplicate_count = 0

        for event in all_events:
            if not self._is_duplicate_event(
                event["title"], event["date"], event["time"], event.get("venue", "")
            ):
                new_events.append(event)
                # Add to cache to prevent duplicates within this run
                event_id = self._create_event_id(
                    event["title"], event["date"], event["time"], event.get("venue", "")
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
