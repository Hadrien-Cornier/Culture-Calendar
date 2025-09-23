#!/usr/bin/env python3
"""
Website data updater for Culture Calendar
Generates JSON data for the GitHub Pages website
Supports multiple venues: AFS, Hyperreal Movie Club, Paramount Theatre, and others
"""

import json
import sys
from datetime import datetime, timedelta

from src.config_loader import ConfigLoader
from src.processor import EventProcessor
from src.scraper import MultiVenueScraper
from src.validation_service import EventValidationService


def apply_field_defaults(event: dict, config_defaults: dict) -> dict:
    """Apply field defaults from config to event data following fail-fast principle"""
    result = {}
    for field, default_value in config_defaults.items():
        if field in event and event[field] is not None:
            result[field] = event[field]
        else:
            result[field] = default_value
    return result


def save_update_info(info: dict, path: str = "docs/source_update_times.json") -> None:
    """Save per-source last update times to JSON"""
    try:
        with open(path, "w") as f:
            json.dump(info, f, indent=2)
        print(f"Saved update info to {path}")
    except Exception as e:
        print(f"Error saving update info: {e}")


# Classical music events are now loaded directly by the individual
# scrapers from docs/classical_data.json


def mark_work_hours(events):
    """Mark events that occur during work hours (9am-6pm weekdays) with isWorkHours field"""
    marked_events = []

    for event in events:
        # Create a copy to avoid modifying the original
        event_copy = event.copy()

        try:
            # Parse date
            date_str = event.get("date")
            if not date_str:
                event_copy["isWorkHours"] = False  # No date, assume not work hours
                marked_events.append(event_copy)
                continue

            event_date = datetime.strptime(date_str, "%Y-%m-%d")

            # Skip weekends (Saturday=5, Sunday=6)
            if event_date.weekday() >= 5:
                event_copy["isWorkHours"] = False
                marked_events.append(event_copy)
                continue

            # Parse time
            time_str = event.get("time", "").strip()
            if not time_str:
                event_copy["isWorkHours"] = (
                    False  # No time specified, assume not work hours
                )
                marked_events.append(event_copy)
                continue

            # Extract hour from time string like "2:30 PM"
            import re

            time_match = re.search(r"(\d{1,2}):(\d{2})\s*([AP]M)", time_str.upper())
            if not time_match:
                event_copy["isWorkHours"] = (
                    False  # Can't parse time, assume not work hours
                )
                marked_events.append(event_copy)
                continue

            hour, minute, ampm = time_match.groups()
            hour = int(hour)

            # Convert to 24-hour format
            if ampm == "PM" and hour != 12:
                hour += 12
            elif ampm == "AM" and hour == 12:
                hour = 0

            # Check if during work hours (9am to 6pm)
            if hour >= 9 and hour < 18:
                event_copy["isWorkHours"] = True
                print(
                    f"[WORK HOURS MARKED] Marked as work hours: '{event.get('title', 'Unknown')}' | Venue: '{event.get('venue', 'Unknown')}' | Date: '{event.get('date', 'Unknown')}' | Time: '{event.get('time', 'Unknown')}' (hour: {hour})"
                )
            else:
                event_copy["isWorkHours"] = False

            marked_events.append(event_copy)

        except Exception as e:
            print(f"Error checking work hours for {event.get('title', 'Unknown')}: {e}")
            # If there's an error parsing, assume not work hours
            event_copy["isWorkHours"] = False
            marked_events.append(event_copy)

    return marked_events


def clean_markdown_text(text):
    """Clean markdown syntax from text for better display"""
    import re

    # Remove hashtag headers but keep the text
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)

    # Convert **bold** to HTML
    text = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", text)

    # Convert *italic* to HTML
    text = re.sub(r"\*(.*?)\*", r"<em>\1</em>", text)

    # Convert line breaks to proper HTML
    text = text.replace("\n\n", "</p><p>").replace("\n", "<br>")

    # Wrap in paragraph tags if not already wrapped
    if not text.startswith("<p>"):
        text = f"<p>{text}</p>"

    return text


def is_movie_event(title, description=""):
    """Determine if an event is a movie screening vs festival/discussion/other event"""
    # Non-movie event indicators
    non_movie_indicators = [
        "movie festival",
        "festival",
        "symposium",
        "conference",
        "workshop",
        "discussion",
        "panel",
        "conversation",
        "talk",
        "seminar",
        "masterclass",
        "awards",
        "ceremony",
        "gala",
        "fundraiser",
        "benefit",
        "market",
        "networking",
        "party",
        "reception",
        "opening night",
        "closing night",
        "black auteur",
        "pan african",
        "auteur festival",
        "series",
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
            print(
                f"Filtering out non-movie: '{title}' (description contains '{indicator}')"
            )
            return False

    # If it contains "premiere" but also "world premiere" or "us premiere",
    # it's likely a movie
    if "premiere" in title_lower and any(
        phrase in title_lower
        for phrase in [
            "world premiere",
            "us premiere",
            "american premiere",
            "texas premiere",
        ]
    ):
        return True

    return True


def generate_website_data(events):
    """Generate JSON data for the website with movie aggregation and venue tags"""
    # Load configuration defaults
    config = ConfigLoader()
    field_defaults = config.get_field_defaults()

    # Include movies, classical music events, and book club events for the
    # website
    website_events = []
    movie_events = []
    classical_events = []
    book_club_events = []

    for event in events:
        if event.get("type") == "concert":
            classical_events.append(event)
            website_events.append(event)
        elif event.get("type") == "book_club":
            book_club_events.append(event)
            website_events.append(event)
        elif event.get("type") == "movie" or event.get("is_movie", True):
            movie_events.append(event)
            website_events.append(event)

    print(
        f"Generating website data: { len(movie_events)} movies, {len(classical_events)} classical events, { len(book_club_events)} book clubs, {len(website_events)} total"
    )

    # Group movie events by title, add classical events directly
    combined_data = {}

    # Process movies (group by title)
    for event in movie_events:
        title = event["title"]

        if title not in combined_data:
            # Create new movie entry using config defaults
            ai_rating = event.get("ai_rating", {})

            # Apply config defaults for basic fields
            defaults_applied = apply_field_defaults(event, field_defaults)

            combined_data[title] = {
                "title": title,
                "rating": ai_rating.get(
                    "score", field_defaults.get("rating", -1)
                ),  # Use base AI rating for consistency
                "description": clean_markdown_text(
                    ai_rating.get(
                        "summary",
                        field_defaults.get("description", "No description available"),
                    )
                ),
                "oneLinerSummary": event.get(
                    "oneLinerSummary"
                ),  # Preserve AI-generated summary
                "url": defaults_applied["url"],
                "isSpecialScreening": event.get("is_special_screening", False),
                "isMovie": event.get("is_movie", True),  # From scraper detection
                "isWorkHours": event.get("isWorkHours", False),  # Work hours marking
                "duration": event.get("duration"),
                "director": event.get("director"),
                "country": defaults_applied["country"],
                "year": event.get("year"),
                "language": defaults_applied["language"],
                "venue": defaults_applied.get("venue")
                or event.get("venue"),  # Use config default or event venue
                "type": event.get("type", "screening"),  # Preserve event type
                "screenings": [],
            }

        # Add screening info (avoid duplicates)
        defaults_for_screening = apply_field_defaults(event, field_defaults)
        screening = {
            "date": event["date"],
            "time": event.get("time", "TBD"),
            "url": defaults_for_screening["url"],
            "venue": defaults_for_screening.get("venue")
            or event.get("venue"),  # Use config default or event venue
        }

        # Check if this exact screening already exists
        existing_screenings = combined_data[title]["screenings"]
        screening_exists = any(
            s["date"] == screening["date"]
            and s["time"] == screening["time"]
            and s["url"] == screening["url"]
            for s in existing_screenings
        )

        if not screening_exists:
            combined_data[title]["screenings"].append(screening)

    # Process classical music events (each event is unique)
    for event in classical_events:
        # Create unique key for each classical event
        event_key = f"{event['title']} - {event['date']} {event['time']}"

        ai_rating = event.get("ai_rating", {})
        defaults_applied = apply_field_defaults(event, field_defaults)

        combined_data[event_key] = {
            "title": event["title"],
            "rating": ai_rating.get("score", field_defaults.get("rating", -1)),
            "description": clean_markdown_text(
                ai_rating.get(
                    "summary",
                    field_defaults.get("description", "No description available"),
                )
            ),
            "oneLinerSummary": event.get(
                "oneLinerSummary"
            ),  # Preserve AI-generated summary
            "url": defaults_applied["url"],
            "isSpecialScreening": False,  # Classical events aren't "screenings"
            "isMovie": False,  # Classical events are concerts
            "isWorkHours": event.get("isWorkHours", False),  # Work hours marking
            "duration": event.get("duration"),
            "director": None,  # Not applicable to concerts
            "country": defaults_applied["country"],
            "year": event.get("year"),
            "language": None,  # Not applicable to instrumental music
            "venue": event.get("venue"),
            "series": event.get("series"),
            "composers": event.get("composers", []),
            "works": event.get("works", []),
            "featured_artist": event.get("featured_artist"),
            "program": event.get("program"),
            "type": event.get("type", "concert"),  # Preserve event type
            "screenings": [
                {  # Using "screenings" terminology for consistency with website
                    "date": event["date"],
                    "time": event.get("time", "TBD"),
                    "url": defaults_applied["url"],
                    "venue": event.get("venue"),
                }
            ],
        }

    # Process book club events (each event is unique)
    for event in book_club_events:
        # Create unique key for each book club event
        event_key = f"{event['title']} - {event['date']} {event['time']}"

        ai_rating = event.get("ai_rating", {})
        defaults_applied = apply_field_defaults(event, field_defaults)

        combined_data[event_key] = {
            "title": event["title"],
            "rating": ai_rating.get("score", field_defaults.get("rating", -1)),
            "description": clean_markdown_text(
                ai_rating.get(
                    "summary",
                    field_defaults.get("description", "No description available"),
                )
            ),
            "oneLinerSummary": event.get(
                "oneLinerSummary"
            ),  # Preserve AI-generated summary
            "url": defaults_applied["url"],
            "isSpecialScreening": False,  # Book clubs aren't "screenings"
            "isMovie": False,  # Book clubs are discussions
            "isWorkHours": event.get("isWorkHours", False),  # Work hours marking
            "duration": event.get("duration"),
            "director": None,  # Not applicable to book clubs
            "country": defaults_applied["country"],
            "year": event.get("year"),
            "language": defaults_applied["language"],
            "venue": event.get("venue"),
            "series": event.get("series"),
            "book": event.get("book"),
            "author": event.get("author"),
            "host": event.get("host"),
            "type": event.get("type", "book_club"),  # Preserve event type
            "screenings": [
                {  # Using "screenings" terminology for consistency with website
                    "date": event["date"],
                    "time": event.get("time", "TBD"),
                    "url": defaults_applied["url"],
                    "venue": event.get("venue"),
                }
            ],
        }

    # Convert to list and add unique IDs
    website_data = []
    for title, event_data in combined_data.items():
        event_id = (
            title.lower()
            .replace(" ", "-")
            .replace("'", "")
            .replace('"', "")
            .replace(":", "")
            .replace(",", "")
        )
        event_data["id"] = event_id

        # Sort screenings by date and time (handle None values)
        event_data["screenings"].sort(
            key=lambda x: (x.get("date") or "9999-12-31", x.get("time") or "23:59")
        )

        website_data.append(event_data)

    # Sort by the earliest screening date/time so upcoming events appear first
    def first_screening_key(item):
        screenings = item.get("screenings", [])
        if not screenings:
            return ("9999-12-31", "23:59")
        first = min(
            screenings,
            key=lambda s: (s.get("date") or "9999-12-31", s.get("time") or "23:59"),
        )
        return (first.get("date") or "9999-12-31", first.get("time") or "23:59")

    website_data.sort(key=first_screening_key)

    return website_data


def main(
    test_week: bool = False,
    full: bool = False,
    force_reprocess: bool = False,
    days: int = None,
    validate: bool = False,
):
    """Generate website data.

    Args:
        test_week: If True, limit scraping to current week for testing.
        full: Deprecated parameter (no longer used - all events are always included).
        force_reprocess: If True, force re-processing of all events (ignore cache).
        days: Deprecated parameter (no longer used - all events are always included).
        validate: If True, enable smart validation with fail-fast mechanisms.
    """
    print(f"Culture Calendar Website Update - Starting at {datetime.now()}")

    try:
        # Initialize components
        scraper = MultiVenueScraper()
        processor = EventProcessor(force_reprocess=force_reprocess)

        # Scrape all venues (including classical music from JSON)
        print("Fetching calendar data from all venues...")
        events = scraper.scrape_all_venues(target_week=test_week, days_ahead=days)
        print(f"Found {len(events)} total events from all venues")
        print(
            "NOTE: Classical music venues load their events from docs/classical_data.json"
        )

        # Smart validation if enabled
        if validate:
            print("\n🔍 Starting smart validation of scraped events...")
            validator = EventValidationService()

            # Group events by scraper for validation
            scraper_events = {
                "AFS": [e for e in events if e.get("venue") == "AFS"],
                "Hyperreal": [e for e in events if e.get("venue") == "Hyperreal"],
                "AlienatedMajesty": [
                    e for e in events if e.get("venue") == "AlienatedMajesty"
                ],
                "FirstLight": [e for e in events if e.get("venue") == "FirstLight"],
                "Symphony": [e for e in events if e.get("venue") == "Symphony"],
                "Opera": [e for e in events if e.get("venue") == "Opera"],
                "Chamber Music": [
                    e for e in events if e.get("venue") == "Chamber Music"
                ],
                "EarlyMusic": [e for e in events if e.get("venue") == "EarlyMusic"],
                "LaFollia": [e for e in events if e.get("venue") == "LaFollia"],
                "Paramount": [e for e in events if e.get("venue") == "Paramount"],
            }

            # Validate all scrapers
            should_continue, health_checks = validator.validate_all_scrapers(
                scraper_events
            )

            # Generate detailed report
            validator.log_validation_report(health_checks)

            if not should_continue:
                print("\n❌ VALIDATION FAILURE - Pipeline stopped!")
                print("Reason: Too many scrapers failed validation checks")
                print("This indicates potential issues with:")
                print("  - Website structure changes")
                print("  - Network connectivity problems")
                print("  - LLM extraction failures")
                print("  - Schema validation errors")
                print(
                    "\nPlease review the validation report above and fix issues before retrying."
                )
                sys.exit(1)

            print("✅ Validation passed - continuing with data processing...")
        else:
            print("⚠️ Smart validation disabled - continuing without checks")

        # Get detailed information for screening and book club events
        print("Fetching event details...")
        detailed_events = []
        for event in events:
            if event.get("type") in ["screening", "book_club"]:
                try:
                    details = scraper.get_event_details(event)
                    event.update(details)
                    detailed_events.append(event)
                except Exception as e:
                    print(
                        f"Error getting details for {event.get( 'title','Unknown')}: {e}"
                    )
            elif event.get("type") in ["concert", "movie"]:
                # Classical events and movie events already have complete details
                detailed_events.append(event)

        # Keep all events - no date filtering applied
        upcoming_events = detailed_events
        print(f"Processing {len(upcoming_events)} total events")

        # Mark work-hour events
        marked_events = mark_work_hours(upcoming_events)
        print(
            f"Marked {len([e for e in marked_events if e.get('isWorkHours')])} work hour events out of {len(marked_events)} total events"
        )

        # Process and enrich events
        print("Processing and enriching events...")
        enriched_events = processor.process_events(marked_events)
        print(f"Processed {len(enriched_events)} events")

        # Generate one-line summaries for events
        print("\nGenerating one-line summaries...")
        # Use the summary generator from the processor to maintain cache consistency
        summary_generator = processor.summary_generator
        if summary_generator:
            for event in enriched_events:
                if not event.get("oneLinerSummary"):
                    try:
                        summary = summary_generator.generate_summary(event)
                        if summary:
                            event["oneLinerSummary"] = summary
                            print(
                                f"  Generated summary for: {event.get('title', 'Unknown')}"
                            )
                    except RuntimeError as e:
                        # Critical validation failure - this should stop the entire process
                        print(
                            f"CRITICAL ERROR: Cannot generate summary for '{event.get('title', 'Unknown')}': {e}"
                        )
                        raise
                    except Exception as e:
                        # Other errors (API failures, etc.) - log but continue
                        print(
                            f"  Warning: Failed to generate summary for '{event.get('title', 'Unknown')}': {e}"
                        )
            print("Completed summary generation")
        else:
            print(
                "Warning: Summary generator not available, skipping summary generation"
            )

        # Generate website JSON data
        print("Generating website data...")
        website_data = generate_website_data(enriched_events)

        # Save JSON data
        with open("docs/data.json", "w") as f:
            json.dump(website_data, f, indent=2)

        print(f"Generated docs/data.json with {len(website_data)} events")
        # Save per-source update timestamps
        save_update_info(scraper.last_updated)

        print("Website update completed successfully!")

    except Exception as e:
        print(f"Error during website update: {e}")
        raise


if __name__ == "__main__":
    # Parse command line flags
    test_week = "--test-week" in sys.argv
    full_update = "--full" in sys.argv
    force_reprocess = "--force-reprocess" in sys.argv
    validate = "--validate" in sys.argv

    # Parse --days parameter
    days_param = None
    for i, arg in enumerate(sys.argv):
        if arg == "--days" and i + 1 < len(sys.argv):
            try:
                days_param = int(sys.argv[i + 1])
            except ValueError:
                print(
                    f"Error: --days parameter must be a number, got '{sys.argv[i + 1]}'"
                )
                sys.exit(1)
            break

    main(
        test_week=test_week,
        full=full_update,
        force_reprocess=force_reprocess,
        days=days_param,
        validate=validate,
    )
