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

def main(debug=False, limit=None):
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
        if debug:
            # In debug mode, only process the first event
            events = events[:1]
            print(f"DEBUG MODE: Processing only first event")
        elif limit:
            # Limit number of events to process
            events = events[:limit]
            print(f"LIMIT MODE: Processing first {limit} events")
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
    # Check for debug mode and limit
    debug_mode = len(sys.argv) > 1 and sys.argv[1] == '--debug'
    limit = None
    
    # Check for limit parameter like --limit=10
    for arg in sys.argv[1:]:
        if arg.startswith('--limit='):
            limit = int(arg.split('=')[1])
    
    main(debug=debug_mode, limit=limit)