#!/usr/bin/env python3
"""
Website data updater for Culture Calendar
Generates JSON data and calendar files for the GitHub Pages website
"""

import os
import json
from datetime import datetime, timedelta
from src.scraper import AFSScraper
from src.processor import EventProcessor
from src.calendar_generator import CalendarGenerator

def filter_work_hours(events):
    """Filter out events during work hours (9am-6pm weekdays)"""
    filtered_events = []
    
    for event in events:
        try:
            # Parse date
            date_str = event.get('date')
            if not date_str:
                continue
                
            event_date = datetime.strptime(date_str, '%Y-%m-%d')
            
            # Skip weekends (Saturday=5, Sunday=6)
            if event_date.weekday() >= 5:
                filtered_events.append(event)
                continue
            
            # Parse time
            time_str = event.get('time', '').strip()
            if not time_str:
                filtered_events.append(event)  # Include if no time specified
                continue
            
            # Extract hour from time string like "2:30 PM"
            import re
            time_match = re.search(r'(\d{1,2}):(\d{2})\s*([AP]M)', time_str.upper())
            if not time_match:
                filtered_events.append(event)  # Include if can't parse time
                continue
            
            hour, minute, ampm = time_match.groups()
            hour = int(hour)
            
            # Convert to 24-hour format
            if ampm == 'PM' and hour != 12:
                hour += 12
            elif ampm == 'AM' and hour == 12:
                hour = 0
            
            # Check if outside work hours (before 9am or after 6pm)
            if hour < 9 or hour >= 18:
                filtered_events.append(event)
                
        except Exception as e:
            print(f"Error filtering work hours for {event.get('title', 'Unknown')}: {e}")
            # Include event if there's an error parsing
            filtered_events.append(event)
    
    return filtered_events

def filter_upcoming_events(events, days_ahead=30):
    """Filter events to only include those in the next N days"""
    today = datetime.now().date()
    cutoff_date = today + timedelta(days=days_ahead)
    
    filtered_events = []
    for event in events:
        try:
            event_date = datetime.strptime(event['date'], '%Y-%m-%d').date()
            if today <= event_date <= cutoff_date:
                filtered_events.append(event)
        except (ValueError, KeyError):
            continue
    
    return filtered_events

def generate_website_data(events):
    """Generate JSON data for the website"""
    website_data = []
    
    for event in events:
        # Create a unique ID for each event
        event_id = f"{event['title'].lower().replace(' ', '-')}-{event['date']}-{event.get('time', '').replace(':', '').replace(' ', '')}"
        
        website_event = {
            'id': event_id,
            'title': event['title'],
            'rating': event.get('final_rating', 5),
            'date': event['date'],
            'time': event.get('time', 'TBD'),
            'description': event.get('ai_rating', {}).get('summary', 'No description available'),
            'url': event.get('url', ''),
            'isSpecialScreening': event.get('is_special_screening', False)
        }
        
        website_data.append(website_event)
    
    # Sort by rating (highest first), then by date
    website_data.sort(key=lambda x: (-x['rating'], x['date']))
    
    return website_data

def generate_calendar_files(events, output_dir):
    """Generate various filtered calendar files"""
    os.makedirs(output_dir, exist_ok=True)
    
    calendar_gen = CalendarGenerator()
    
    # Generate calendars for different rating thresholds
    rating_thresholds = [1, 5, 6, 7, 8, 9, 10]
    
    for min_rating in rating_thresholds:
        filtered_events = [e for e in events if e.get('final_rating', 5) >= min_rating]
        
        if filtered_events:
            filename = f"culture-calendar-{min_rating}plus.ics"
            filepath = os.path.join(output_dir, filename)
            calendar_gen.generate_ics(filtered_events, filepath)
            print(f"Generated {filename} with {len(filtered_events)} events")

def main():
    print(f"Culture Calendar Website Update - Starting at {datetime.now()}")
    
    try:
        # Initialize components
        scraper = AFSScraper()
        processor = EventProcessor()
        
        # Scrape AFS calendar
        print("Fetching AFS calendar data...")
        events = scraper.scrape_calendar()
        print(f"Found {len(events)} total events")
        
        # Get detailed information for each screening event
        print("Fetching event details...")
        screening_events = []
        for event in events:
            if event.get('type') == 'screening':
                try:
                    details = scraper.get_event_details(event['url'])
                    event.update(details)
                    screening_events.append(event)
                except Exception as e:
                    print(f"Error getting details for {event.get('title', 'Unknown')}: {e}")
        
        print(f"Processing {len(screening_events)} screening events")
        
        # Filter to upcoming events only (next 30 days)
        upcoming_events = filter_upcoming_events(screening_events, days_ahead=30)
        print(f"Found {len(upcoming_events)} upcoming events")
        
        # Filter out work-hour events
        filtered_events = filter_work_hours(upcoming_events)
        print(f"After filtering work hours: {len(filtered_events)} events")
        
        # Process and enrich events (limit to avoid API overuse)
        print("Processing and enriching events...")
        max_events = min(20, len(filtered_events))  # Limit to 20 events to avoid API costs
        events_to_process = filtered_events[:max_events]
        
        enriched_events = processor.process_events(events_to_process)
        print(f"Processed {len(enriched_events)} events")
        
        # Generate website JSON data
        print("Generating website data...")
        website_data = generate_website_data(enriched_events)
        
        # Save JSON data
        with open('docs/data.json', 'w') as f:
            json.dump(website_data, f, indent=2)
        
        print(f"Generated docs/data.json with {len(website_data)} movies")
        
        # Generate calendar files
        print("Generating calendar files...")
        generate_calendar_files(enriched_events, 'docs/calendars')
        
        print("Website update completed successfully!")
        
    except Exception as e:
        print(f"Error during website update: {e}")
        raise

if __name__ == "__main__":
    main()