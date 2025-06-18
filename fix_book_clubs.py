#!/usr/bin/env python3

import json
import re

def load_and_fix_data():
    """Load data.json and fix book club events to proper format"""
    
    # Load current data
    with open('docs/data.json', 'r') as f:
        events = json.load(f)
    
    # Create movies dictionary for aggregation
    movies_dict = {}
    fixed_events = []
    
    # Process each event
    for event in events:
        # Check if this is a book club event that needs fixing
        if event.get('type') == 'book_club' and 'screenings' not in event:
            # This is a raw book club event, convert to aggregated format
            title = event.get('title', '')
            
            if title not in movies_dict:
                # Create new aggregated entry
                movies_dict[title] = {
                    'title': title,
                    'rating': event.get('final_rating', event.get('ai_rating', {}).get('score', 5)),
                    'description': event.get('rating_explanation', event.get('ai_rating', {}).get('summary', '')),
                    'url': event.get('url', ''),
                    'isSpecialScreening': event.get('is_special_screening', False),
                    'isMovie': False,  # Book clubs are not movies
                    'duration': event.get('duration'),
                    'director': event.get('author'),  # Use author as director for book clubs
                    'country': event.get('country', 'USA'),
                    'year': event.get('year'),
                    'language': event.get('language', 'English'),
                    'venue': event.get('venue', 'AlienatedMajesty'),
                    'screenings': []
                }
            
            # Add screening info
            screening = {
                'date': event.get('date'),
                'time': event.get('time', '7:00 PM'),
                'url': event.get('url', ''),
                'venue': event.get('venue', 'AlienatedMajesty')
            }
            
            # Check if this screening already exists
            existing_screenings = movies_dict[title]['screenings']
            screening_exists = any(
                s['date'] == screening['date'] and 
                s['time'] == screening['time'] and 
                s['url'] == screening['url']
                for s in existing_screenings
            )
            
            if not screening_exists:
                movies_dict[title]['screenings'].append(screening)
        
        elif 'screenings' in event:
            # This is already in the correct format
            fixed_events.append(event)
        else:
            # This is some other type of event, keep as is
            fixed_events.append(event)
    
    # Add the aggregated book club events
    for title, movie_data in movies_dict.items():
        movie_id = title.lower().replace(' ', '-').replace("'", '').replace('"', '').replace(':', '')
        movie_data['id'] = movie_id
        
        # Sort screenings by date and time
        movie_data['screenings'].sort(key=lambda x: (x['date'], x['time']))
        
        fixed_events.append(movie_data)
    
    return fixed_events

def main():
    """Fix book club events and save to data.json"""
    print("Fixing book club events...")
    
    fixed_events = load_and_fix_data()
    
    # Remove duplicates
    seen_titles = set()
    unique_events = []
    
    for event in fixed_events:
        title = event.get('title', '')
        if title not in seen_titles:
            seen_titles.add(title)
            unique_events.append(event)
        else:
            print(f"Removing duplicate: {title}")
    
    # Sort by rating (highest first), then by title
    unique_events.sort(key=lambda x: (-x.get('rating', 0), x.get('title', '')))
    
    # Save fixed data
    with open('docs/data.json', 'w') as f:
        json.dump(unique_events, f, indent=2)
    
    # Count book clubs
    book_club_count = sum(1 for event in unique_events if event.get('venue') in ['AlienatedMajesty', 'FirstLight'])
    
    print(f"Fixed data saved! Total events: {len(unique_events)}")
    print(f"Book club events: {book_club_count}")

if __name__ == "__main__":
    main()