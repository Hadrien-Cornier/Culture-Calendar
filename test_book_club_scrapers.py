#!/usr/bin/env python3

import sys
sys.path.append('src')

from scraper import AlienatedMajestyBooksScraper, FirstLightAustinScraper

def test_scrapers():
    """Test the book club scrapers"""
    
    print("Testing Alienated Majesty Books scraper...")
    alienated_scraper = AlienatedMajestyBooksScraper()
    alienated_events = alienated_scraper.scrape_calendar()
    
    print(f"Found {len(alienated_events)} Alienated Majesty events:")
    for event in alienated_events:
        print(f"  - {event['title']} on {event['date']} at {event['time']}")
        print(f"    Book: {event.get('book', 'N/A')} by {event.get('author', 'N/A')}")
    
    print("\n" + "="*50 + "\n")
    
    print("Testing First Light Austin scraper...")
    firstlight_scraper = FirstLightAustinScraper()
    firstlight_events = firstlight_scraper.scrape_calendar()
    
    print(f"Found {len(firstlight_events)} First Light events:")
    for event in firstlight_events:
        print(f"  - {event['title']} on {event['date']} at {event['time']}")
        print(f"    Book: {event.get('book', 'N/A')} by {event.get('author', 'N/A')}")
        if event.get('host'):
            print(f"    Host: {event.get('host')}")
    
    print("\n" + "="*50 + "\n")
    print(f"Total book club events: {len(alienated_events) + len(firstlight_events)}")

if __name__ == "__main__":
    test_scrapers()