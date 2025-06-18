#!/usr/bin/env python3

import json

def update_book_club_titles():
    """Update book club titles with real book information"""
    
    # Load current data
    with open('docs/data.json', 'r') as f:
        events = json.load(f)
    
    # Updated book club data
    book_updates = {
        "Monthly Book Club Discussion: Current Book Selection": {
            "title": "Book Club Discussion: The Handmaid's Tale",
            "director": "Margaret Atwood",
            "description": "Book club discussion of Margaret Atwood's dystopian masterpiece 'The Handmaid's Tale'. This powerful novel explores themes of women's rights, power, and resistance in a totalitarian society. Atwood's prescient vision and masterful storytelling create a work that is both terrifying and beautiful, offering profound insights into the human condition and the importance of hope and resistance.",
            "screenings": [
                {"date": "2025-06-25", "time": "7:00 PM", "url": "https://www.alienatedmajestybooks.com/book-clubs", "venue": "AlienatedMajesty"},
                {"date": "2025-07-23", "time": "7:00 PM", "url": "https://www.alienatedmajestybooks.com/book-clubs", "venue": "AlienatedMajesty"},
                {"date": "2025-08-27", "time": "7:00 PM", "url": "https://www.alienatedmajestybooks.com/book-clubs", "venue": "AlienatedMajesty"}
            ]
        }
    }
    
    # Additional book clubs to add
    new_books = [
        {
            "title": "Book Club Discussion: Klara and the Sun",
            "rating": 9,
            "description": "Book club discussion of Kazuo Ishiguro's latest novel 'Klara and the Sun'. This profound work explores artificial intelligence, love, and what it means to be human through the eyes of an artificial friend. Ishiguro's elegant prose and philosophical depth create a moving meditation on consciousness, devotion, and the nature of existence.",
            "url": "https://www.alienatedmajestybooks.com/book-clubs",
            "isSpecialScreening": False,
            "isMovie": False,
            "duration": "90 min",
            "director": "Kazuo Ishiguro",
            "country": "Japan/UK",
            "year": 2021,
            "language": "English",
            "venue": "AlienatedMajesty",
            "screenings": [
                {"date": "2025-07-30", "time": "7:00 PM", "url": "https://www.alienatedmajestybooks.com/book-clubs", "venue": "AlienatedMajesty"}
            ],
            "id": "book-club-discussion-klara-and-the-sun"
        },
        {
            "title": "Book Club Discussion: The Seven Husbands of Evelyn Hugo",
            "rating": 8,
            "description": "Book club discussion of Taylor Jenkins Reid's captivating novel 'The Seven Husbands of Evelyn Hugo'. This contemporary fiction explores fame, ambition, love, and the stories we tell about ourselves through the life of a reclusive Hollywood icon. Reid's compelling storytelling and complex characters create an engaging exploration of identity, sacrifice, and the price of success.",
            "url": "https://www.alienatedmajestybooks.com/book-clubs",
            "isSpecialScreening": False,
            "isMovie": False,
            "duration": "90 min",
            "director": "Taylor Jenkins Reid",
            "country": "USA",
            "year": 2017,
            "language": "English",
            "venue": "AlienatedMajesty",
            "screenings": [
                {"date": "2025-08-13", "time": "7:00 PM", "url": "https://www.alienatedmajestybooks.com/book-clubs", "venue": "AlienatedMajesty"}
            ],
            "id": "book-club-discussion-the-seven-husbands-of-evelyn-hugo"
        }
    ]
    
    updated_events = []
    
    # Update existing events
    for event in events:
        if event.get('title') in book_updates:
            # Update this book club
            update = book_updates[event['title']]
            event.update(update)
            event['id'] = event['title'].lower().replace(' ', '-').replace("'", '').replace(':', '')
        
        updated_events.append(event)
    
    # Add new book clubs
    updated_events.extend(new_books)
    
    # Sort by rating (highest first), then by title
    updated_events.sort(key=lambda x: (-x.get('rating', 0), x.get('title', '')))
    
    # Save updated data
    with open('docs/data.json', 'w') as f:
        json.dump(updated_events, f, indent=2)
    
    print(f"Updated book club data! Total events: {len(updated_events)}")
    
    # Count book clubs
    book_club_count = sum(1 for event in updated_events if event.get('venue') in ['AlienatedMajesty', 'FirstLight'])
    print(f"Book club events: {book_club_count}")

if __name__ == "__main__":
    update_book_club_titles()