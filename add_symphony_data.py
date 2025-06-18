#!/usr/bin/env python3
"""
Quick script to add Symphony events to data.json
"""

import json
import sys
import os
sys.path.append('.')
from src.scraper import AustinSymphonyScraper

def main():
    # Load existing data
    with open('docs/data.json', 'r') as f:
        existing_data = json.load(f)
    
    print(f"Loaded {len(existing_data)} existing events")
    
    # Get Symphony events
    scraper = AustinSymphonyScraper()
    symphony_events = scraper.scrape_calendar()
    
    print(f"Found {len(symphony_events)} symphony events")
    
    # Convert Symphony events to data.json format
    symphony_data = []
    for event in symphony_events:
        details = scraper.get_event_details(event)
        
        # Create basic Symphony event data structure
        event_data = {
            "title": event['title'],
            "rating": 8,  # Default rating for now
            "description": f"**Rating: 8/10**\n\n{details['description']}\n\n🎼 **Series:** {event.get('series', 'N/A')}\n\n👨‍🎼 **Featured Artist:** {event.get('featured_artist', 'N/A')}\n\n🎵 **Composers:** {', '.join(event.get('composers', []))}\n\n🎶 **Program:** {event.get('program', 'N/A')}",
            "url": event['url'],
            "isSpecialScreening": False,
            "isMovie": False,
            "duration": details['duration'],
            "director": None,
            "country": details['country'],
            "year": details['year'],
            "language": None,
            "venue": "Symphony",
            "id": f"symphony-{event['date']}-{event['title'].lower().replace(' ', '-').replace(':', '').replace(',', '')}",
            "screenings": [
                {
                    "date": event['date'],
                    "time": event['time'],
                    "url": event['url']
                }
            ],
            "series": event.get('series'),
            "composers": event.get('composers', []),
            "works": event.get('works', []),
            "featured_artist": event.get('featured_artist')
        }
        
        symphony_data.append(event_data)
    
    # Combine existing data with Symphony data
    combined_data = existing_data + symphony_data
    
    print(f"Total events after adding Symphony: {len(combined_data)}")
    
    # Save updated data
    with open('docs/data.json', 'w') as f:
        json.dump(combined_data, f, indent=2)
    
    print("✅ Updated data.json with Symphony events")

if __name__ == '__main__':
    main()