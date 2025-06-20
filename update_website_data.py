#!/usr/bin/env python3
"""
Website data updater for Culture Calendar
Generates JSON data for the GitHub Pages website
Supports multiple venues: AFS, Hyperreal Film Club, and others
"""

import os
import json
import sys
from datetime import datetime, timedelta
from src.scraper import MultiVenueScraper
from src.processor import EventProcessor

def save_update_info(info: dict, path: str = 'docs/source_update_times.json') -> None:
    """Save per-source last update times to JSON"""
    try:
        with open(path, 'w') as f:
            json.dump(info, f, indent=2)
        print(f"Saved update info to {path}")
    except Exception as e:
        print(f"Error saving update info: {e}")

def load_classical_music_events() -> list:
    """Load classical music events from static JSON file"""
    classical_events = []
    classical_data_path = 'docs/classical_data.json'
    
    try:
        with open(classical_data_path, 'r') as f:
            classical_data = json.load(f)
        
        # Process Austin Symphony events
        for concert in classical_data.get('austinSymphony', []):
            for i, date in enumerate(concert['dates']):
                time = concert['times'][i] if i < len(concert['times']) else concert['times'][0]
                event = {
                    'title': concert['title'],
                    'url': f"https://austinsymphony.org/concerts/{concert['title'].lower().replace(' ', '-').replace(':', '').replace(',', '')}",
                    'date': date,
                    'time': time,
                    'type': 'concert',
                    'location': concert['venue_name'],
                    'venue': 'Symphony',
                    'series': concert['series'],
                    'program': concert['program'],
                    'featured_artist': concert['featured_artist'],
                    'composers': concert['composers'],
                    'works': concert['works']
                }
                classical_events.append(event)
        
        # Process Early Music Austin events
        for concert in classical_data.get('earlyMusicAustin', []):
            for i, date in enumerate(concert['dates']):
                time = concert['times'][i] if i < len(concert['times']) else concert['times'][0]
                event = {
                    'title': concert['title'],
                    'url': f"https://earlymusicaustin.org/events/{concert['title'].lower().replace(' ', '-')}",
                    'date': date,
                    'time': time,
                    'type': 'concert',
                    'location': concert['venue_name'],
                    'venue': 'EarlyMusic',
                    'series': concert['series'],
                    'program': concert['program'],
                    'featured_artist': concert['featured_artist'],
                    'composers': concert['composers'],
                    'works': concert['works']
                }
                classical_events.append(event)
        
        # Process La Follia Austin events
        for concert in classical_data.get('laFolliaAustin', []):
            for i, date in enumerate(concert['dates']):
                time = concert['times'][i] if i < len(concert['times']) else concert['times'][0]
                event = {
                    'title': concert['title'],
                    'url': f"https://lafollia.com/events/{concert['title'].lower().replace(' ', '-')}",
                    'date': date,
                    'time': time,
                    'type': 'concert',
                    'location': concert['venue_name'],
                    'venue': 'LaFollia',
                    'series': concert['series'],
                    'program': concert['program'],
                    'featured_artist': concert['featured_artist'],
                    'composers': concert['composers'],
                    'works': concert['works']
                }
                classical_events.append(event)
        
        print(f"Loaded {len(classical_events)} classical music events from static data")
        return classical_events
        
    except FileNotFoundError:
        print(f"Classical data file {classical_data_path} not found")
        return []
    except Exception as e:
        print(f"Error loading classical music data: {e}")
        return []

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

def filter_upcoming_events(events, mode='month'):
    """Filter events based on mode: 'month' for upcoming month, or number of days"""
    today = datetime.now().date()
    
    if mode == 'month':
        # Get events for the current month and next month
        current_month_start = today.replace(day=1)
        
        # Calculate next month
        if today.month == 12:
            next_month = today.replace(year=today.year + 1, month=1, day=1)
        else:
            next_month = today.replace(month=today.month + 1, day=1)
        
        # End of next month
        if next_month.month == 12:
            end_of_next_month = next_month.replace(year=next_month.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end_of_next_month = next_month.replace(month=next_month.month + 1, day=1) - timedelta(days=1)
        
        start_date = current_month_start
        end_date = end_of_next_month
        
        print(f"Filtering events from {start_date} to {end_date} (upcoming month)")
    else:
        # Legacy mode: use days_ahead
        days_ahead = mode if isinstance(mode, int) else 30
        start_date = today
        end_date = today + timedelta(days=days_ahead)
        
        print(f"Filtering events from {start_date} to {end_date} ({days_ahead} days)")
    
    filtered_events = []
    for event in events:
        try:
            event_date = datetime.strptime(event['date'], '%Y-%m-%d').date()
            if start_date <= event_date <= end_date:
                filtered_events.append(event)
        except (ValueError, KeyError):
            continue
    
    return filtered_events

def clean_markdown_text(text):
    """Clean markdown syntax from text for better display"""
    import re
    
    # Remove hashtag headers but keep the text
    text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)
    
    # Convert **bold** to HTML
    text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', text)
    
    # Convert *italic* to HTML
    text = re.sub(r'\*(.*?)\*', r'<em>\1</em>', text)
    
    # Convert line breaks to proper HTML
    text = text.replace('\n\n', '</p><p>').replace('\n', '<br>')
    
    # Wrap in paragraph tags if not already wrapped
    if not text.startswith('<p>'):
        text = f'<p>{text}</p>'
    
    return text

def is_movie_event(title, description=""):
    """Determine if an event is a movie screening vs festival/discussion/other event"""
    # Non-movie event indicators
    non_movie_indicators = [
        'film festival', 'festival', 'symposium', 'conference', 'workshop',
        'discussion', 'panel', 'conversation', 'talk', 'seminar', 'masterclass',
        'awards', 'ceremony', 'gala', 'fundraiser', 'benefit', 'market',
        'networking', 'party', 'reception', 'opening night', 'closing night',
        'black auteur', 'pan african', 'auteur festival', 'series'
    ]
    
    title_lower = title.lower()
    desc_lower = description.lower()
    
    # Check if title contains non-movie indicators
    for indicator in non_movie_indicators:
        if indicator in title_lower:
            print(f"Filtering out non-movie: '{title}' (contains '{indicator}')")
            return False
    
    # Additional checks in description
    for indicator in non_movie_indicators:
        if indicator in desc_lower:
            print(f"Filtering out non-movie: '{title}' (description contains '{indicator}')")
            return False
    
    # If it contains "premiere" but also "world premiere" or "us premiere", it's likely a movie
    if 'premiere' in title_lower and any(phrase in title_lower for phrase in [
        'world premiere', 'us premiere', 'american premiere', 'texas premiere'
    ]):
        return True
    
    return True

def generate_website_data(events):
    """Generate JSON data for the website with movie aggregation and venue tags"""
    # Include movies, classical music events, and book club events for the website
    website_events = []
    movie_events = []
    classical_events = []
    book_club_events = []
    
    for event in events:
        if event.get('type') == 'concert':
            classical_events.append(event)
            website_events.append(event)
        elif event.get('type') == 'book_club':
            book_club_events.append(event)
            website_events.append(event)
        elif event.get('is_movie', True):
            movie_events.append(event)
            website_events.append(event)
    
    print(f"Generating website data: {len(movie_events)} movies, {len(classical_events)} classical events, {len(book_club_events)} book clubs, {len(website_events)} total")
    
    # Group movie events by title, add classical events directly
    combined_data = {}
    
    # Process movies (group by title)
    for event in movie_events:
        title = event['title']
        
        if title not in combined_data:
            # Create new movie entry
            ai_rating = event.get('ai_rating', {})
            combined_data[title] = {
                'title': title,
                'rating': ai_rating.get('score', 5),  # Use base AI rating for consistency
                'description': clean_markdown_text(ai_rating.get('summary', 'No description available')),
                'url': event.get('url', ''),
                'isSpecialScreening': event.get('is_special_screening', False),
                'isMovie': event.get('is_movie', True),  # From scraper detection
                'duration': event.get('duration'),
                'director': event.get('director'),
                'country': event.get('country') if event.get('country') else 'Unknown',
                'year': event.get('year'),
                'language': event.get('language'),
                'venue': event.get('venue', 'AFS'),  # Venue tag
                'screenings': []
            }
        
        # Add screening info (avoid duplicates)
        screening = {
            'date': event['date'],
            'time': event.get('time', 'TBD'),
            'url': event.get('url', ''),
            'venue': event.get('venue', 'AFS')  # Add venue to each screening
        }
        
        # Check if this exact screening already exists
        existing_screenings = combined_data[title]['screenings']
        screening_exists = any(
            s['date'] == screening['date'] and 
            s['time'] == screening['time'] and 
            s['url'] == screening['url']
            for s in existing_screenings
        )
        
        if not screening_exists:
            combined_data[title]['screenings'].append(screening)
    
    # Process classical music events (each event is unique)
    for event in classical_events:
        # Create unique key for each classical event
        event_key = f"{event['title']} - {event['date']} {event['time']}"
        
        ai_rating = event.get('ai_rating', {})
        combined_data[event_key] = {
            'title': event['title'],
            'rating': ai_rating.get('score', 5),
            'description': clean_markdown_text(ai_rating.get('summary', 'No description available')),
            'url': event.get('url', ''),
            'isSpecialScreening': False,  # Classical events aren't "screenings"
            'isMovie': False,  # Classical events are concerts
            'duration': event.get('duration'),
            'director': None,  # Not applicable to concerts
            'country': event.get('country', 'USA'),
            'year': event.get('year'),
            'language': None,  # Not applicable to instrumental music
            'venue': event.get('venue'),
            'series': event.get('series'),
            'composers': event.get('composers', []),
            'works': event.get('works', []),
            'featured_artist': event.get('featured_artist'),
            'program': event.get('program'),
            'screenings': [{  # Using "screenings" terminology for consistency with website
                'date': event['date'],
                'time': event.get('time', 'TBD'),
                'url': event.get('url', ''),
                'venue': event.get('venue')
            }]
        }
    
    # Process book club events (each event is unique)
    for event in book_club_events:
        # Create unique key for each book club event  
        event_key = f"{event['title']} - {event['date']} {event['time']}"
        
        ai_rating = event.get('ai_rating', {})
        combined_data[event_key] = {
            'title': event['title'],
            'rating': ai_rating.get('score', 5),
            'description': clean_markdown_text(ai_rating.get('summary', 'No description available')),
            'url': event.get('url', ''),
            'isSpecialScreening': False,  # Book clubs aren't "screenings"
            'isMovie': False,  # Book clubs are discussions
            'duration': event.get('duration'),
            'director': None,  # Not applicable to book clubs
            'country': event.get('country', 'USA'),
            'year': event.get('year'),
            'language': event.get('language', 'English'),
            'venue': event.get('venue'),
            'series': event.get('series'),
            'book': event.get('book'),
            'author': event.get('author'),
            'host': event.get('host'),
            'screenings': [{  # Using "screenings" terminology for consistency with website
                'date': event['date'],
                'time': event.get('time', 'TBD'),
                'url': event.get('url', ''),
                'venue': event.get('venue')
            }]
        }
    
    # Convert to list and add unique IDs
    website_data = []
    for title, event_data in combined_data.items():
        event_id = title.lower().replace(' ', '-').replace("'", '').replace('"', '').replace(':', '').replace(',', '')
        event_data['id'] = event_id
        
        # Sort screenings by date and time
        event_data['screenings'].sort(key=lambda x: (x['date'], x['time']))
        
        website_data.append(event_data)
    
    # Sort by the earliest screening date/time so upcoming events appear first
    def first_screening_key(item):
        screenings = item.get('screenings', [])
        if not screenings:
            return ('9999-12-31', '23:59')
        first = min(screenings, key=lambda s: (s['date'], s.get('time', '')))
        return (first['date'], first.get('time', ''))

    website_data.sort(key=first_screening_key)
    
    return website_data


def main(test_week: bool = False, full: bool = False, force_reprocess: bool = False, days: int = None):
    """Generate website data.

    Args:
        test_week: If True, limit scraping to current week for testing.
        full: If True, include all events without date filtering.
        force_reprocess: If True, force re-processing of all events (ignore cache).
        days: If specified, collect events for this many days from today.
    """
    print(f"Culture Calendar Website Update - Starting at {datetime.now()}")
    
    try:
        # Initialize components
        scraper = MultiVenueScraper()
        processor = EventProcessor(force_reprocess=force_reprocess)
        
        # Scrape all venues
        print("Fetching calendar data from all venues...")
        events = scraper.scrape_all_venues(target_week=test_week)
        print(f"Found {len(events)} total events from live scraping")
        
        # Add classical music events from static data
        print("Loading classical music events...")
        classical_events = load_classical_music_events()
        events.extend(classical_events)
        print(f"Found {len(events)} total events including classical music")
        
        # Get detailed information for screening and book club events
        print("Fetching event details...")
        detailed_events = []
        for event in events:
            if event.get('type') in ['screening', 'book_club']:
                try:
                    details = scraper.get_event_details(event)
                    event.update(details)
                    detailed_events.append(event)
                except Exception as e:
                    print(f"Error getting details for {event.get('title', 'Unknown')}: {e}")
            elif event.get('type') == 'concert':
                # Classical events already have complete details from JSON
                detailed_events.append(event)
        
        print(f"Processing {len(detailed_events)} total events")
        
        # Filter to desired time range
        if full:
            # No date filtering - include all events
            upcoming_events = detailed_events
            print(f"Using all {len(upcoming_events)} events for full update")
        elif test_week:
            # For testing, use all events from current week
            upcoming_events = detailed_events
            print(f"Using all {len(upcoming_events)} events for test week")
        elif days:
            # Filter to specific number of days
            upcoming_events = filter_upcoming_events(detailed_events, mode=days)
            print(f"Found {len(upcoming_events)} events for next {days} days")
        else:
            # Filter to upcoming events (current month + next month)
            upcoming_events = filter_upcoming_events(detailed_events, mode='month')
            print(f"Found {len(upcoming_events)} upcoming events")
        
        # Filter out work-hour events
        filtered_events = filter_work_hours(upcoming_events)
        print(f"After filtering work hours: {len(filtered_events)} events")
        
        # Process and enrich events
        print("Processing and enriching events...")
        enriched_events = processor.process_events(filtered_events)
        print(f"Processed {len(enriched_events)} events")
        
        # Generate website JSON data
        print("Generating website data...")
        website_data = generate_website_data(enriched_events)
        
        # Save JSON data
        with open('docs/data.json', 'w') as f:
            json.dump(website_data, f, indent=2)
        
        print(f"Generated docs/data.json with {len(website_data)} movies")
        # Save per-source update timestamps
        save_update_info(scraper.last_updated)

        print("Website update completed successfully!")
        
    except Exception as e:
        print(f"Error during website update: {e}")
        raise

if __name__ == "__main__":
    # Parse command line flags
    test_week = '--test-week' in sys.argv
    full_update = '--full' in sys.argv
    force_reprocess = '--force-reprocess' in sys.argv
    
    # Parse --days parameter
    days_param = None
    for i, arg in enumerate(sys.argv):
        if arg == '--days' and i + 1 < len(sys.argv):
            try:
                days_param = int(sys.argv[i + 1])
            except ValueError:
                print(f"Error: --days parameter must be a number, got '{sys.argv[i + 1]}'")
                sys.exit(1)
            break
    
    main(test_week=test_week, full=full_update, force_reprocess=force_reprocess, days=days_param)
