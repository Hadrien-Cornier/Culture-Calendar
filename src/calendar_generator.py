"""
ICS calendar file generator
"""

from datetime import datetime, timedelta
from typing import Dict, List

import pytz
from icalendar import Calendar, Event, Timezone


class CalendarGenerator:
    def __init__(self):
        self.timezone = pytz.timezone("America/Chicago")  # Austin timezone

    def generate_ics(self, events: List[Dict], filename: str) -> None:
        """Generate ICS calendar file from events"""
        cal = Calendar()

        # Set calendar properties
        cal.add("prodid", "-//Culture Calendar//Austin Movie Society Events//EN")
        cal.add("version", "2.0")
        cal.add("calscale", "GREGORIAN")
        cal.add("method", "PUBLISH")
        cal.add("x-wr-calname", "Austin Movie Society Events")
        cal.add("x-wr-caldesc", "Curated movie screenings from Austin Movie Society")

        # Add timezone component
        cal.add_component(self._create_timezone())

        for event_data in events:
            try:
                event = self._create_event(event_data)
                if event:
                    cal.add_component(event)
            except Exception as e:
                print(
                    f"Error creating calendar event for '{event_data.get( 'title','Unknown')}': {e}"
                )

        # Write to file
        with open(filename, "wb") as f:
            f.write(cal.to_ical())

        print(f"Calendar saved with {len(cal.subcomponents)} events")

    def _create_event(self, event_data: Dict) -> Event:
        """Create a calendar event from event data"""
        event = Event()

        # Required fields
        event.add("uid", self._generate_uid(event_data))
        event.add("dtstamp", datetime.now(self.timezone))

        # Event title with rating
        title = event_data["title"]
        final_rating = event_data.get("final_rating", 0)
        if final_rating > 0:
            title = f"⭐{final_rating}/10 - {title}"

        event.add("summary", title)

        # Date and time
        start_datetime = self._parse_datetime(event_data)
        if start_datetime:
            event.add("dtstart", start_datetime)
            # Assume 2 hour duration
            event.add("dtend", start_datetime + timedelta(hours=2))
        else:
            # All-day event if we can't parse time
            event_date = self._parse_date_only(event_data)
            if event_date:
                event.add("dtstart", event_date.date())

        # Location - use event-specific location if available, otherwise default to AFS
        location = event_data.get("location")
        if not location:
            if event_data.get("venue") == "NewYorkerMeetup":
                location = "Central Market, 4001 N Lamar Blvd, Austin, TX 78752"
            else:
                location = "Austin Movie Society Cinema, 6226 Middle Fiskville Rd, Austin, TX 78752"
        event.add("location", location)

        # Description
        description = self._build_description(event_data)
        event.add("description", description)

        # URL
        if event_data.get("url"):
            event.add("url", event_data["url"])

        # Categories - set based on event type
        if event_data.get("type") == "book_club":
            categories = ["Book Club", "Literature", "Discussion"]
        elif event_data.get("type") == "concert":
            categories = ["Concert", "Music", "Classical"]
        else:
            categories = ["Movie", "Entertainment"]

        if event_data.get("is_special_screening"):
            categories.append("Special Event")
        if event_data.get("is_recurring"):
            categories.append("Recurring Event")

        event.add("categories", categories)

        return event

    def _generate_uid(self, event_data: Dict) -> str:
        """Generate unique identifier for event"""
        # Create unique UID based on URL + date + time to handle multiple
        # showings
        if event_data.get("url"):
            base_uid = event_data["url"]
        else:
            title_clean = "".join(c for c in event_data["title"] if c.isalnum())
            base_uid = f"event-{title_clean}"

        # Add date and time to make each showing unique
        date_str = event_data.get("date", "nodate")
        time_str = event_data.get("time", "notime").replace(":", "").replace(" ", "")

        return f"{base_uid}-{date_str}-{time_str}@culturecalendar.local"

    def _parse_datetime(self, event_data: Dict) -> datetime:
        """Parse date and time into datetime object"""
        try:
            date_str = event_data.get("date")
            time_str = event_data.get("time")

            if not date_str:
                return None

            # Parse date
            event_date = datetime.strptime(date_str, "%Y-%m-%d")

            # Parse time if available
            if time_str:
                # Handle formats like "8:00 PM", "3:30 PM"
                time_str_clean = time_str.replace(" ", "").upper()

                if "PM" in time_str_clean:
                    time_part = time_str_clean.replace("PM", "")
                    hour, minute = map(int, time_part.split(":"))
                    if hour != 12:
                        hour += 12
                elif "AM" in time_str_clean:
                    time_part = time_str_clean.replace("AM", "")
                    hour, minute = map(int, time_part.split(":"))
                    if hour == 12:
                        hour = 0
                else:
                    # Assume 24-hour format
                    hour, minute = map(int, time_str.split(":"))

                event_datetime = event_date.replace(hour=hour, minute=minute)
            else:
                # Default to 7:00 PM if no time specified
                event_datetime = event_date.replace(hour=19, minute=0)

            # Localize to Austin timezone
            return self.timezone.localize(event_datetime)

        except Exception as e:
            print(f"Error parsing datetime: {e}")
            return None

    def _parse_date_only(self, event_data: Dict) -> datetime:
        """Parse just the date for all-day events"""
        try:
            date_str = event_data.get("date")
            if date_str:
                return datetime.strptime(date_str, "%Y-%m-%d")
        except Exception as e:
            print(f"Error parsing date: {e}")
        return None

    def _build_description(self, event_data: Dict) -> str:
        """Build event description with rating and details"""
        description_parts = []

        # Rating explanation (this already includes AI summary)
        rating_explanation = event_data.get("rating_explanation", "")
        if rating_explanation:
            description_parts.append(f"🎬 {rating_explanation}")

        # Special screening indicator
        if event_data.get("is_special_screening"):
            description_parts.append("✨ Special Screening")

        # Event details from page (avoid duplication with AI summary)
        page_description = event_data.get("description", "").strip()
        if page_description and len(page_description) > 10:
            description_parts.append(f"Event Details: {page_description}")

        # Event URL
        if event_data.get("url"):
            description_parts.append(f"More info: {event_data['url']}")

        # Venue info
        description_parts.append("📍 Austin Movie Society Cinema")
        description_parts.append("🎟️ Tickets: https://www.austinfilm.org/")

        return "\n\n".join(description_parts)

    def _create_timezone(self) -> Timezone:
        """Create VTIMEZONE component for America/Chicago"""
        from icalendar import TimezoneDaylight, TimezoneStandard

        tz = Timezone()
        tz.add("tzid", "America/Chicago")

        # Standard time (CST) - First Sunday in November
        standard = TimezoneStandard()
        standard.add("dtstart", datetime(1970, 11, 1, 2, 0, 0))
        standard.add("rrule", {"freq": "yearly", "bymonth": 11, "byday": "1su"})
        standard.add("tzoffsetfrom", timedelta(hours=-5))
        standard.add("tzoffsetto", timedelta(hours=-6))
        standard.add("tzname", "CST")

        # Daylight time (CDT) - Second Sunday in March
        daylight = TimezoneDaylight()
        daylight.add("dtstart", datetime(1970, 3, 8, 2, 0, 0))
        daylight.add("rrule", {"freq": "yearly", "bymonth": 3, "byday": "2su"})
        daylight.add("tzoffsetfrom", timedelta(hours=-6))
        daylight.add("tzoffsetto", timedelta(hours=-5))
        daylight.add("tzname", "CDT")

        tz.add_component(standard)
        tz.add_component(daylight)

        return tz
