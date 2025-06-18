#!/usr/bin/env python3
"""
Incremental website data updater for Culture Calendar
Only processes new events that don't already exist in the database
Prevents duplicates and allows for efficient incremental updates
"""

import os
import json
import sys
from datetime import datetime, timedelta
from src.scraper import MultiVenueScraper
from src.processor import EventProcessor
from update_website_data import save_update_info

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
            
            # Filter work hours (9 AM to 6 PM) on weekdays
            if 9 <= hour < 18:
                print(f"Filtering work-hour event: {event.get('title', 'Unknown')} at {time_str}")
                continue
            
            filtered_events.append(event)
            
        except Exception as e:
            print(f"Error filtering event: {e}")
            filtered_events.append(event)  # Include on error to be safe
    
    return filtered_events

def load_existing_data():
    """Load existing processed data"""
    data_file = "docs/data.json"
    if os.path.exists(data_file):
        try:
            with open(data_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading existing data: {e}")
            return []
    return []

def merge_events_data(existing_data, new_processed_events):
    """Merge new events into existing data structure"""
    # Create a lookup for existing events by title and venue
    existing_lookup = {}
    for event in existing_data:
        key = f"{event['title']}_{event.get('venue', '')}"
        existing_lookup[key] = event
    
    merged_data = list(existing_data)  # Start with existing data
    new_movies_added = 0
    
    for new_event in new_processed_events:
        key = f"{new_event['title']}_{new_event.get('venue', '')}"
        
        if key in existing_lookup:
            # Movie exists, check if we need to add new screenings
            existing_event = existing_lookup[key]
            existing_screenings = {f"{s['date']}_{s['time']}" for s in existing_event.get('screenings', [])}
            
            new_screenings = []
            for screening in new_event.get('screenings', []):
                screening_key = f"{screening['date']}_{screening['time']}"
                if screening_key not in existing_screenings:
                    new_screenings.append(screening)
            
            if new_screenings:
                existing_event['screenings'].extend(new_screenings)
                print(f"Added {len(new_screenings)} new screenings to '{new_event['title']}'")
        else:
            # New movie
            merged_data.append(new_event)
            new_movies_added += 1
            print(f"Added new movie: '{new_event['title']}' ({new_event.get('venue', 'Unknown venue')})")
    
    print(f"Added {new_movies_added} new movies to the database")
    return merged_data

def main():
    try:
        print("🎬 Starting incremental Culture Calendar update...")
        
        # Check for target week mode
        target_week = len(sys.argv) > 1 and sys.argv[1].lower() == 'week'
        if target_week:
            print("📅 Running in target week mode (current week only)")
        
        # Initialize scraper with duplicate detection
        scraper = MultiVenueScraper()
        
        # Scrape only new events
        print("🔍 Scraping for new events...")
        if target_week:
            raw_events = scraper.scrape_new_events_only(target_week=True)
        else:
            raw_events = scraper.scrape_new_events_only()
        
        if not raw_events:
            print("✅ No new events found. Database is up to date!")
            return
        
        print(f"📝 Found {len(raw_events)} new events to process")
        
        # Filter work hours
        print("⏰ Filtering work-hour events...")
        filtered_events = filter_work_hours(raw_events)
        print(f"📝 {len(filtered_events)} events after work-hour filtering")
        
        if not filtered_events:
            print("✅ No new events after filtering. Database is up to date!")
            return
        
        # Process events
        print("🤖 Processing events with AI analysis...")
        processor = EventProcessor()
        processed_events = processor.process_events(filtered_events)
        print(f"✅ Processed {len(processed_events)} new events")
        
        # Load existing data and merge
        print("🔄 Merging with existing data...")
        existing_data = load_existing_data()
        merged_data = merge_events_data(existing_data, processed_events)
        
        # Sort by rating (highest first)
        merged_data.sort(key=lambda x: x.get('rating', 0), reverse=True)
        
        # Save updated data
        os.makedirs('docs', exist_ok=True)
        with open('docs/data.json', 'w', encoding='utf-8') as f:
            json.dump(merged_data, f, indent=2, ensure_ascii=False)
        
        print(f"💾 Saved {len(merged_data)} total events to docs/data.json")
        # Save per-source update timestamps
        save_update_info(scraper.last_updated)

        print("✅ Incremental update completed successfully!")
        print(f"📊 Total events in database: {len(merged_data)}")
        
    except KeyboardInterrupt:
        print("\\n⏹️ Update cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error during update: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()