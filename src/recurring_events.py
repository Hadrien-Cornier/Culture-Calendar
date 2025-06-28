"""
Recurring events generator for regular meetups and events
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional
import calendar


class RecurringEventGenerator:
    """Generate recurring events for regular meetups"""

    def __init__(self):
        self.timezone = "America/Chicago"  # Austin timezone

    def generate_new_yorker_meetup_events(self, weeks_ahead: int = 8) -> List[Dict]:
        """
        Generate The New Yorker Weekly Short Story Club events
        
        Args:
            weeks_ahead: Number of weeks to generate events for
            
        Returns:
            List of event dictionaries
        """
        events = []
        
        # Base event information
        base_event = {
            "title": "The New Yorker Weekly Short Story Club (Free Copies, First Hour for Reading)",
            "venue": "NewYorkerMeetup",
            "location": "Central Market, 4001 N Lamar Blvd, Austin, TX 78752",
            "time": "7:00 PM",
            "description": "Calling all literary fiction lovers of the greater Austin Area! Join our weekly discussion of The New Yorker's latest short story. We provide free copies and the first hour is for reading. Whether you're a longtime lover of literature or just curious about contemporary short fiction, you're welcome! This is an inclusive community space welcoming all backgrounds and identities.",
            "url": "https://www.meetup.com/atxstories/",
            "type": "book_club",
            "series": "The New Yorker Weekly Short Story Club",
            "host": "Nabeel K. and others",
            "organizer": "Austin: The New Yorker Magazine Short Story Readers Club",
            "category": "Literary Discussion",
            "tags": ["literature", "short stories", "book club", "weekly", "the new yorker", "discussion", "reading"],
            "is_recurring": True,
            "recurring_pattern": "weekly",
            "recurring_day": "Tuesday"
        }
        
        # Find next Tuesday
        today = datetime.now().date()
        days_until_tuesday = (1 - today.weekday()) % 7  # Tuesday is weekday 1
        if days_until_tuesday == 0 and datetime.now().hour >= 21:  # If it's Tuesday after 9 PM
            days_until_tuesday = 7  # Next Tuesday
        
        next_tuesday = today + timedelta(days=days_until_tuesday)
        
        # Generate events for the specified number of weeks
        for week in range(weeks_ahead):
            event_date = next_tuesday + timedelta(weeks=week)
            
            event = base_event.copy()
            event["date"] = event_date.strftime("%Y-%m-%d")
            
            # Add week-specific details if needed
            week_number = week + 1
            if week_number == 1:
                event["title"] = f"{base_event['title']} - This Week's Story"
            else:
                event["title"] = f"{base_event['title']} - Week {week_number}"
            
            events.append(event)
        
        return events

    def generate_all_recurring_events(self, weeks_ahead: int = 8) -> List[Dict]:
        """
        Generate all recurring events
        
        Args:
            weeks_ahead: Number of weeks to generate events for
            
        Returns:
            List of all recurring event dictionaries
        """
        all_events = []
        
        # Add The New Yorker meetup events
        new_yorker_events = self.generate_new_yorker_meetup_events(weeks_ahead)
        all_events.extend(new_yorker_events)
        
        # Future recurring events can be added here
        # For example:
        # book_club_events = self.generate_other_book_club_events(weeks_ahead)
        # all_events.extend(book_club_events)
        
        return all_events

    def add_custom_recurring_event(
        self, 
        title: str,
        venue: str,
        location: str,
        day_of_week: str,
        time: str,
        description: str,
        url: str,
        event_type: str = "event",
        weeks_ahead: int = 8,
        **kwargs
    ) -> List[Dict]:
        """
        Add a custom recurring event
        
        Args:
            title: Event title
            venue: Venue identifier
            location: Full location/address
            day_of_week: Day of week (Monday, Tuesday, etc.)
            time: Time in format like "7:00 PM"
            description: Event description
            url: Event URL
            event_type: Type of event (book_club, meetup, etc.)
            weeks_ahead: Number of weeks to generate
            **kwargs: Additional event properties
            
        Returns:
            List of event dictionaries
        """
        events = []
        
        # Map day names to weekday numbers (Monday=0, Sunday=6)
        day_mapping = {
            "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
            "friday": 4, "saturday": 5, "sunday": 6
        }
        
        target_weekday = day_mapping.get(day_of_week.lower())
        if target_weekday is None:
            raise ValueError(f"Invalid day_of_week: {day_of_week}")
        
        # Base event information
        base_event = {
            "title": title,
            "venue": venue,
            "location": location,
            "time": time,
            "description": description,
            "url": url,
            "type": event_type,
            "is_recurring": True,
            "recurring_pattern": "weekly",
            "recurring_day": day_of_week.title()
        }
        
        # Add any additional properties
        base_event.update(kwargs)
        
        # Find next occurrence of the target day
        today = datetime.now().date()
        days_until_target = (target_weekday - today.weekday()) % 7
        if days_until_target == 0:
            # If it's the target day, check if we should use today or next week
            current_time = datetime.now().time()
            event_time = datetime.strptime(time, "%I:%M %p").time()
            if current_time >= event_time:
                days_until_target = 7  # Next week
        
        next_occurrence = today + timedelta(days=days_until_target)
        
        # Generate events for the specified number of weeks
        for week in range(weeks_ahead):
            event_date = next_occurrence + timedelta(weeks=week)
            
            event = base_event.copy()
            event["date"] = event_date.strftime("%Y-%m-%d")
            
            events.append(event)
        
        return events 