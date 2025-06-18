#!/usr/bin/env python3
"""
Culture Calendar - Multi-Venue Event Aggregator
Supports AFS, Hyperreal Film Club, and other Austin venues
"""

import sys
import os
from datetime import datetime
from src.scraper import MultiVenueScraper
from src.processor import EventProcessor
from src.calendar_generator import CalendarGenerator

def main(debug=False, limit=None, test_week=False):
    print(f"Culture Calendar - Starting at {datetime.now()}")
    
    try:
        # Initialize components
        scraper = MultiVenueScraper()
        processor = EventProcessor()
        calendar_gen = CalendarGenerator()
        
        # Scrape all venues
        print("Fetching calendar data from all venues...")
        events = scraper.scrape_all_venues(target_week=test_week)
        print(f"Found {len(events)} total events")
        
        # Get detailed information for each event
        print("Fetching event details...")
        for event in events:
            if event.get('type') == 'screening':
                details = scraper.get_event_details(event)
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
        suffix = "_test_week" if test_week else ""
        ics_filename = f"culture_calendar_{datetime.now().strftime('%Y%m%d_%H%M')}{suffix}.ics"
        calendar_gen.generate_ics(enriched_events, ics_filename)
        print(f"Calendar saved as: {ics_filename}")
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    # Parse command line arguments
    debug_mode = '--debug' in sys.argv
    test_week = '--test-week' in sys.argv
    limit = None
    
    # Check for limit parameter like --limit=10
    for arg in sys.argv[1:]:
        if arg.startswith('--limit='):
            limit = int(arg.split('=')[1])
    
    main(debug=debug_mode, limit=limit, test_week=test_week)