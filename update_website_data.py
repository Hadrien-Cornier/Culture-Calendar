#!/usr/bin/env python3
"""
Website data updater for Culture Calendar
Generates JSON data and calendar files for the GitHub Pages website
Supports multiple venues: AFS, Hyperreal Film Club, and others
"""

import os
import json
import sys
from datetime import datetime, timedelta
from src.scraper import MultiVenueScraper
from src.processor import EventProcessor
from src.calendar_generator import CalendarGenerator

def save_update_info(info: dict, path: str = 'docs/source_update_times.json') -> None:
    """Save per-source last update times to JSON"""
    try:
        with open(path, 'w') as f:
            json.dump(info, f, indent=2)
        print(f"Saved update info to {path}")
    except Exception as e:
        print(f"Error saving update info: {e}")

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
    # Filter out non-movie events using the scraper's detection
    movie_events = [event for event in events if event.get('is_movie', True)]
    print(f"Filtered to {len(movie_events)} movie events from {len(events)} total events")
    
    # Group events by movie title
    movies_dict = {}
    
    for event in movie_events:
        title = event['title']
        
        if title not in movies_dict:
            # Create new movie entry
            ai_rating = event.get('ai_rating', {})
            movies_dict[title] = {
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
        existing_screenings = movies_dict[title]['screenings']
        screening_exists = any(
            s['date'] == screening['date'] and 
            s['time'] == screening['time'] and 
            s['url'] == screening['url']
            for s in existing_screenings
        )
        
        if not screening_exists:
            movies_dict[title]['screenings'].append(screening)
    
    # Convert to list and add unique IDs
    website_data = []
    for title, movie_data in movies_dict.items():
        movie_id = title.lower().replace(' ', '-').replace("'", '').replace('"', '')
        movie_data['id'] = movie_id
        
        # Sort screenings by date and time
        movie_data['screenings'].sort(key=lambda x: (x['date'], x['time']))
        
        website_data.append(movie_data)
    
    # Sort by rating (highest first), then by title
    website_data.sort(key=lambda x: (-x['rating'], x['title']))
    
    return website_data

def generate_calendar_files(events, output_dir):
    """Generate various filtered calendar files"""
    os.makedirs(output_dir, exist_ok=True)
    
    calendar_gen = CalendarGenerator()
    
    # Generate calendars for different rating thresholds
    rating_thresholds = [1, 5, 6, 7, 8, 9, 10]
    
    for min_rating in rating_thresholds:
        filtered_events = [e for e in events if e.get('final_rating', 5) >= min_rating]
        
        if filtered_events:
            filename = f"culture-calendar-{min_rating}plus.ics"
            filepath = os.path.join(output_dir, filename)
            calendar_gen.generate_ics(filtered_events, filepath)
            print(f"Generated {filename} with {len(filtered_events)} events")

def main(test_week=False):
    print(f"Culture Calendar Website Update - Starting at {datetime.now()}")
    
    try:
        # Initialize components
        scraper = MultiVenueScraper()
        processor = EventProcessor()
        
        # Scrape all venues
        print("Fetching calendar data from all venues...")
        events = scraper.scrape_all_venues(target_week=test_week)
        print(f"Found {len(events)} total events")
        
        # Get detailed information for each screening event
        print("Fetching event details...")
        detailed_events = []
        for event in events:
            if event.get('type') in ['screening', 'concert', 'book_club']:
                try:
                    details = scraper.get_event_details(event)
                    event.update(details)
                    detailed_events.append(event)
                except Exception as e:
                    print(f"Error getting details for {event.get('title', 'Unknown')}: {e}")

        print(f"Processing {len(detailed_events)} events")
        
        # Filter to upcoming events
        if test_week:
            # For testing, use all events from current week
            upcoming_events = detailed_events
            print(f"Using all {len(upcoming_events)} events for test week")
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
        
        # Generate calendar files
        print("Generating calendar files...")
        generate_calendar_files(enriched_events, 'docs/calendars')

        # Save per-source update timestamps
        save_update_info(scraper.last_updated)

        print("Website update completed successfully!")
        
    except Exception as e:
        print(f"Error during website update: {e}")
        raise

if __name__ == "__main__":
    # Check for test week flag
    test_week = '--test-week' in sys.argv
    main(test_week=test_week)