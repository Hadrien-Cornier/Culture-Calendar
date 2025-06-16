#!/usr/bin/env python3
"""
Culture Calendar - Austin Film Society Event Aggregator
Phase 1: MVP implementation for AFS calendar to ICS conversion
"""

import sys
import os
from datetime import datetime
from src.scraper import AFSScraper
from src.processor import EventProcessor
from src.calendar_generator import CalendarGenerator

def main():
    print(f"Culture Calendar - Starting at {datetime.now()}")
    
    try:
        # Initialize components
        scraper = AFSScraper()
        processor = EventProcessor()
        calendar_gen = CalendarGenerator()
        
        # Scrape AFS calendar
        print("Fetching AFS calendar data...")
        events = scraper.scrape_calendar()
        print(f"Found {len(events)} events")
        
        # Get detailed information for each event
        print("Fetching event details...")
        for event in events:
            if event.get('type') == 'screening':
                details = scraper.get_event_details(event['url'])
                event.update(details)
        
        # Process and enrich events
        print("Processing and enriching events...")
        enriched_events = processor.process_events(events)
        print(f"Processed {len(enriched_events)} events")
        
        # Generate ICS file
        print("Generating ICS calendar file...")
        ics_filename = f"afs_calendar_{datetime.now().strftime('%Y%m%d_%H%M')}.ics"
        calendar_gen.generate_ics(enriched_events, ics_filename)
        print(f"Calendar saved as: {ics_filename}")
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()