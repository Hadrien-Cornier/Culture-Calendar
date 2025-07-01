"""
Unified multi-venue scraper using the new LLM-powered architecture
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List

# Import all new LLM-powered scrapers
from .scrapers import (
    AFSScraper,
    AlienatedMajestyBooksScraper,
    AustinSymphonyScraper,
    EarlyMusicAustinScraper,
    FirstLightAustinScraper,
    HyperrealScraper,
    LaFolliaAustinScraper,
)
from .recurring_events import RecurringEventGenerator


class MultiVenueScraper:
    """Unified scraper for all supported venues using new LLM-powered architecture"""

    def __init__(self):
        # Initialize all new scrapers
        self.afs_scraper = AFSScraper()
        self.hyperreal_scraper = HyperrealScraper()
        self.alienated_majesty_scraper = AlienatedMajestyBooksScraper()
        self.first_light_scraper = FirstLightAustinScraper()
        self.symphony_scraper = AustinSymphonyScraper()
        self.early_music_scraper = EarlyMusicAustinScraper()
        self.la_follia_scraper = LaFolliaAustinScraper()

        # Initialize recurring events generator
        self.recurring_events_generator = RecurringEventGenerator()

        self.existing_events_cache = set()  # Cache for duplicate detection
        self.last_updated = {}

    def scrape_all_venues(
        self, target_week: bool = False, days_ahead: int = None
    ) -> List[Dict]:
        """Scrape events from all supported venues using new architecture"""
        all_events = []
        self.last_updated = {}

        # Scrape AFS
        print("Scraping Austin Movie Society...")
        try:
            afs_events = self.afs_scraper.scrape_events()
            for event in afs_events:
                event["venue"] = "AFS"
                all_events.append(event)
            print(f"Found {len(afs_events)} AFS events")
            self.last_updated["AFS"] = datetime.now().isoformat()
        except Exception as e:
            print(f"Error scraping AFS: {e}")
            self.last_updated["AFS"] = None

        # Scrape Hyperreal
        print("Scraping Hyperreal Movie Club...")
        try:
            hyperreal_events = self.hyperreal_scraper.scrape_events(
                days_ahead=days_ahead
            )
            for event in hyperreal_events:
                event["venue"] = "Hyperreal"
                all_events.append(event)
            print(f"Found {len(hyperreal_events)} Hyperreal events")
            self.last_updated["Hyperreal"] = datetime.now().isoformat()
        except Exception as e:
            print(f"Error scraping Hyperreal: {e}")
            self.last_updated["Hyperreal"] = None

        # Scrape Austin Symphony
        print("Loading Austin Symphony season...")
        try:
            symphony_events = self.symphony_scraper.scrape_events()
            for event in symphony_events:
                event["venue"] = "Symphony"
                all_events.append(event)
            print(f"Found {len(symphony_events)} Symphony events")
            self.last_updated["Symphony"] = datetime.now().isoformat()
        except Exception as e:
            print(f"Error loading Symphony events: {e}")
            self.last_updated["Symphony"] = None

        # Scrape Texas Early Music Project
        print("Loading Early Music Austin season...")
        try:
            early_music_events = self.early_music_scraper.scrape_events()
            for event in early_music_events:
                event["venue"] = "EarlyMusic"
                all_events.append(event)
            print(f"Found {len(early_music_events)} Early Music events")
            self.last_updated["EarlyMusic"] = datetime.now().isoformat()
        except Exception as e:
            print(f"Error loading Early Music events: {e}")
            self.last_updated["EarlyMusic"] = None

        # Scrape La Follia Austin
        print("Loading La Follia Austin events...")
        try:
            la_follia_events = self.la_follia_scraper.scrape_events()
            for event in la_follia_events:
                event["venue"] = "LaFollia"
                all_events.append(event)
            print(f"Found {len(la_follia_events)} La Follia events")
            self.last_updated["LaFollia"] = datetime.now().isoformat()
        except Exception as e:
            print(f"Error loading La Follia events: {e}")
            self.last_updated["LaFollia"] = None

        # Scrape Alienated Majesty Books
        print("Loading Alienated Majesty Books club...")
        try:
            alienated_majesty_events = self.alienated_majesty_scraper.scrape_events()
            for event in alienated_majesty_events:
                event["venue"] = "AlienatedMajesty"
                all_events.append(event)
            print(f"Found {len(alienated_majesty_events)} Alienated Majesty events")
            self.last_updated["AlienatedMajesty"] = datetime.now().isoformat()
        except Exception as e:
            print(f"Error loading Alienated Majesty events: {e}")
            self.last_updated["AlienatedMajesty"] = None

        # Scrape First Light Austin
        print("Loading First Light Austin book clubs...")
        try:
            first_light_events = self.first_light_scraper.scrape_events()
            for event in first_light_events:
                event["venue"] = "FirstLight"
                all_events.append(event)
            print(f"Found {len(first_light_events)} First Light events")
            self.last_updated["FirstLight"] = datetime.now().isoformat()
        except Exception as e:
            print(f"Error loading First Light events: {e}")
            self.last_updated["FirstLight"] = None

        # Generate recurring events
        print("Generating recurring events...")
        try:
            # Generate events for next 8 weeks by default, or 2 weeks for target_week mode
            weeks_ahead = 2 if target_week else 8
            recurring_events = (
                self.recurring_events_generator.generate_all_recurring_events(
                    weeks_ahead
                )
            )
            all_events.extend(recurring_events)
            print(f"Generated {len(recurring_events)} recurring events")
            self.last_updated["RecurringEvents"] = datetime.now().isoformat()
        except Exception as e:
            print(f"Error generating recurring events: {e}")
            self.last_updated["RecurringEvents"] = None

        # Filter to current week if requested
        if target_week:
            all_events = self._filter_to_current_week(all_events)
            print(f"Filtered to {len(all_events)} events for current week")

        return all_events

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
        """Scrape only new events that don't already exist"""
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
        else:
            return self.afs_scraper.get_event_details(event["url"])
