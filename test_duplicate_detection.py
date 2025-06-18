#!/usr/bin/env python3
"""
Test script for the duplicate detection system
"""

import sys
from src.scraper import MultiVenueScraper

def main():
    print("🧪 Testing duplicate detection system...")
    
    # Initialize scraper
    scraper = MultiVenueScraper()
    
    # Test regular scraping (should find duplicates)
    print("\n1. Testing regular scraping (with potential duplicates):")
    all_events = scraper.scrape_all_venues()
    print(f"Found {len(all_events)} total events")
    
    # Test duplicate detection
    print("\n2. Testing duplicate detection:")
    new_events = scraper.scrape_new_events_only()
    print(f"Found {len(new_events)} new events after duplicate filtering")
    
    # Show difference
    duplicates_filtered = len(all_events) - len(new_events)
    print(f"\n📊 Summary:")
    print(f"   Total events scraped: {len(all_events)}")
    print(f"   New events only: {len(new_events)}")
    print(f"   Duplicates filtered: {duplicates_filtered}")
    
    if duplicates_filtered > 0:
        print("✅ Duplicate detection is working!")
    else:
        print("ℹ️ No duplicates found (this is normal for first run)")

if __name__ == "__main__":
    main()