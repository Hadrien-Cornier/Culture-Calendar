"""
Simple base scraper class for adhoc venue scrapers
"""

import os
import re
import requests
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from datetime import datetime

from dotenv import load_dotenv
from src.llm_service import LLMService

load_dotenv()


class BaseScraper(ABC):
    """
    Simple base scraper class.
    Each venue scraper implements its own adhoc scraping logic.
    """

    def __init__(
        self,
        base_url: str,
        venue_name: str,
        venue_key: str = None,
        config: Optional[Any] = None,
    ):
        self.base_url = base_url
        self.venue_name = venue_name
        self.venue_key = venue_key
        self.config = config

        # Initialize HTTP session
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Cache-Control": "max-age=0",
            }
        )

        # Initialize LLM service
        self.llm_service = LLMService()

        print(f"Initialized {self.__class__.__name__} for {venue_name}")
        if not self.llm_service.anthropic:
            print(
                "  Warning: LLM service not configured - Smart extraction unavailable"
            )

    def get_project_path(self, *path_components: str) -> str:
        """
        Get a path relative to the project root directory.

        Args:
            *path_components: Path components to join with the project root

        Returns:
            Absolute path to the requested file/directory

        Example:
            self.get_project_path("docs", "classical_data.json")
            # Returns: /path/to/project/docs/classical_data.json
        """
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(project_root, *path_components)

    @abstractmethod
    def scrape_events(self) -> List[Dict]:
        """
        Each scraper implements its own adhoc scraping logic.
        Returns list of events in standard format.
        """
        pass

    def format_event(self, raw_event: Dict) -> Dict:
        """
        Format an event according to master_config.yaml specifications

        Args:
            raw_event: Raw event data from scraper

        Returns:
            Formatted event with snake_case fields and proper date/time format
        """
        # If no config, return raw event (backwards compatibility)
        if not self.config or not self.venue_key:
            return raw_event

        # Get date/time spec
        date_spec = self.config.get_date_time_spec()

        # Initialize formatted event
        formatted = {}

        # Convert field names to snake_case and handle date/time formatting
        for key, value in raw_event.items():
            # Convert to snake_case
            snake_key = self._to_snake_case(key)

            # Handle date/time fields specially
            if key in ["date", "dates"]:
                formatted["dates"] = self._format_dates(value)
            elif key in ["time", "times"]:
                formatted["times"] = self._format_times(value)
            else:
                formatted[snake_key] = value

        # Ensure dates and times are arrays with equal length
        if "dates" in formatted and "times" in formatted:
            dates = (
                formatted["dates"]
                if isinstance(formatted["dates"], list)
                else [formatted["dates"]]
            )
            times = (
                formatted["times"]
                if isinstance(formatted["times"], list)
                else [formatted["times"]]
            )

            # If single date/time, duplicate to match length requirement
            if len(dates) == 1 and len(times) == 1:
                formatted["dates"] = dates
                formatted["times"] = times
            elif len(dates) != len(times):
                # This is an error according to spec
                raise ValueError(
                    f"Mismatched dates/times length: {len(dates)} dates vs {len(times)} times"
                )
            else:
                formatted["dates"] = dates
                formatted["times"] = times

        # Set event_category based on venue policy
        if not self.config.is_classification_enabled(self.venue_key):
            assumed_category = self.config.get_assumed_event_category(self.venue_key)
            if assumed_category:
                formatted["event_category"] = assumed_category
        else:
            # Classification enabled - leave event_category unset/null for Phase One
            formatted["event_category"] = None

        # Add raw_metadata for debugging (optional)
        if any(k not in formatted for k in raw_event.keys()):
            formatted["raw_metadata"] = {
                k: v
                for k, v in raw_event.items()
                if self._to_snake_case(k) not in formatted
            }

        return formatted

    def _to_snake_case(self, name: str) -> str:
        """Convert a string to snake_case"""
        # Handle common cases
        if name.lower() == name:
            return name.replace(" ", "_").replace("-", "_")

        # Convert camelCase or PascalCase to snake_case
        s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
        s2 = re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1)
        return s2.lower().replace(" ", "_").replace("-", "_")

    def _format_dates(self, dates: Any) -> List[str]:
        """Format dates to YYYY-MM-DD format"""
        if not dates:
            return []

        if not isinstance(dates, list):
            dates = [dates]

        formatted_dates = []
        for date in dates:
            if isinstance(date, str):
                # Try to parse and reformat
                try:
                    # Already in correct format?
                    if re.match(r"^\d{4}-\d{2}-\d{2}$", date):
                        formatted_dates.append(date)
                    else:
                        # Try to parse various formats
                        for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d"]:
                            try:
                                dt = datetime.strptime(date, fmt)
                                formatted_dates.append(dt.strftime("%Y-%m-%d"))
                                break
                            except ValueError:
                                continue
                except Exception:
                    # If all parsing fails, keep original
                    formatted_dates.append(date)
            else:
                formatted_dates.append(str(date))

        return formatted_dates

    def _format_times(self, times: Any) -> List[str]:
        """Format times to HH:mm format (24-hour)"""
        if not times:
            return []

        if not isinstance(times, list):
            times = [times]

        formatted_times = []
        for time in times:
            if isinstance(time, str):
                # Try to parse and reformat
                try:
                    # Already in correct format?
                    if re.match(r"^\d{2}:\d{2}$", time):
                        formatted_times.append(time)
                    else:
                        # Try to parse various formats
                        for fmt in ["%H:%M", "%I:%M %p", "%I:%M%p", "%H:%M:%S"]:
                            try:
                                dt = datetime.strptime(time.upper(), fmt)
                                formatted_times.append(dt.strftime("%H:%M"))
                                break
                            except ValueError:
                                continue
                        else:
                            # If no format worked, try simple conversion
                            time_clean = time.upper().strip()
                            if "PM" in time_clean or "AM" in time_clean:
                                # Handle 12-hour format
                                time_clean = time_clean.replace("PM", " PM").replace(
                                    "AM", " AM"
                                )
                                time_clean = re.sub(r"\s+", " ", time_clean).strip()
                                try:
                                    dt = datetime.strptime(time_clean, "%I:%M %p")
                                    formatted_times.append(dt.strftime("%H:%M"))
                                except:
                                    formatted_times.append(time)
                            else:
                                formatted_times.append(time)
                except Exception:
                    formatted_times.append(time)
            else:
                formatted_times.append(str(time))

        return formatted_times

    def validate_event(self, event: Dict) -> None:
        """
        Validate an event according to master_config.yaml rules

        Args:
            event: Event to validate

        Raises:
            ValueError: If validation fails
        """
        if not self.config:
            return

        validation_rules = self.config.get_validation_rules()

        # Check snake_case fields
        for key in event.keys():
            if key != key.lower() or " " in key:
                if validation_rules.get("fail_fast", True):
                    raise ValueError(f"Field '{key}' is not in snake_case format")

        # Check dates/times pairing
        if "dates" in event and "times" in event:
            dates = (
                event["dates"] if isinstance(event["dates"], list) else [event["dates"]]
            )
            times = (
                event["times"] if isinstance(event["times"], list) else [event["times"]]
            )

            if len(dates) != len(times):
                if validation_rules.get("error_on_mismatched_dates_times_length", True):
                    raise ValueError(
                        f"Mismatched dates/times length: {len(dates)} vs {len(times)}"
                    )

        # Check date/time formats
        date_spec = self.config.get_date_time_spec()
        if "dates" in event:
            dates = (
                event["dates"] if isinstance(event["dates"], list) else [event["dates"]]
            )
            for date in dates:
                if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(date)):
                    if validation_rules.get("fail_fast", True):
                        raise ValueError(
                            f"Invalid date format: {date} (expected YYYY-MM-DD)"
                        )

        if "times" in event:
            times = (
                event["times"] if isinstance(event["times"], list) else [event["times"]]
            )
            for time in times:
                if not re.match(r"^\d{2}:\d{2}$", str(time)):
                    if validation_rules.get("fail_fast", True):
                        raise ValueError(
                            f"Invalid time format: {time} (expected HH:mm)"
                        )

        # Check event_category if set
        if "event_category" in event and event["event_category"]:
            allowed_categories = self.config.get_allowed_event_categories()
            if event["event_category"] not in allowed_categories:
                if validation_rules.get("fail_fast", True):
                    raise ValueError(
                        f"Invalid event_category: {event['event_category']}"
                    )
