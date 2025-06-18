#!/usr/bin/env python3
"""
Configurable website data updater for Culture Calendar
Supports different time ranges for event collection
"""

import sys
import os
from update_website_data import main as update_main, filter_upcoming_events

def main():
    # Get mode from command line argument or default to 'month'
    mode = sys.argv[1] if len(sys.argv) > 1 else 'month'
    
    print(f"Culture Calendar Update - Mode: {mode}")
    
    # Temporarily patch the filter function for different modes
    full_update = False
    if mode == 'week':
        # Override the filter function to use 7 days
        import update_website_data
        original_filter = update_website_data.filter_upcoming_events
        update_website_data.filter_upcoming_events = lambda events, mode='week': original_filter(events, 7)
        print("Using 7-day window for weekly update")
    elif mode == 'month':
        print("Using current month + next month window for monthly update")
    elif mode == 'full':
        full_update = True
        print("Using full event range for update")
    else:
        print(f"Unknown mode '{mode}', defaulting to monthly update")
    
    # Run the main update function
    update_main(full=full_update)

if __name__ == "__main__":
    main()
