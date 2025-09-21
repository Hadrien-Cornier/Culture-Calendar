#!/usr/bin/env python3
"""
Website data updater for Culture Calendar
Generates JSON data for the GitHub Pages website
Supports multiple venues: AFS, Hyperreal Movie Club, Paramount Theatre, and others
"""

import json
import sys
from datetime import datetime, timedelta

from src.processor import EventProcessor
from src.scraper import MultiVenueScraper
from src.validation_service import EventValidationService
from src.config_loader import ConfigLoader


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


def determine_event_type(event: dict) -> str:
    """Determine event type from event data, defaulting to 'other'"""
    return event.get("type", "other")


def build_event_from_template(
    event: dict, template: dict, config: ConfigLoader
) -> dict:
    """Build event output using template configuration"""
    output = {}

    # Get template fields
    template_fields = template.get("fields", [])

    # Get AI rating for special processing
    ai_rating = event.get("ai_rating", {})

    # Process only fields defined in template
    for field in template_fields:
        if field == "description":
            # Special handling for description - prefer AI rating summary
            if ai_rating.get("summary"):
                output[field] = clean_markdown_text(ai_rating.get("summary", ""))
            elif field in event:
                output[field] = clean_markdown_text(event[field])
            else:
                output[field] = config.get_field_defaults().get(
                    "description", "No description available"
                )
        elif field == "rating":
            # Special handling for rating - use AI rating score
            output[field] = ai_rating.get("score", -1)
        elif field == "one_liner_summary":
            # Special handling for one_liner_summary - prefer AI-generated version
            if event.get("oneLinerSummary"):
                output[field] = event.get("oneLinerSummary")
            else:
                output[field] = ""
        elif field in event:
            # Use event value if present
            output[field] = event[field]
        else:
            # Apply config-defined defaults
            output[field] = get_default_value(field, config)

    # Ensure type field is preserved
    if "type" not in output:
        output["type"] = event.get("type", "other")

    return output


def get_default_value(field_name: str, config: ConfigLoader):
    """Get default value for a field from configuration"""
    defaults = config.get_field_defaults()

    # Map template field names to config field names
    field_mapping = {
        "one_liner_summary": "description",
        "runtime_minutes": "duration",
        "release_year": "year",
        "publication_year": "year",
    }

    config_field = field_mapping.get(field_name, field_name)
    return defaults.get(config_field, "")


def create_occurrences_from_arrays(event: dict, date_time_spec: dict) -> list:
    """Create occurrences array from date/time arrays with validation"""
    dates = event.get(date_time_spec["date_field"], [])
    times = event.get(date_time_spec["time_field"], [])

    # Handle legacy singular format
    if not dates and "date" in event:
        dates = [event["date"]]
    if not times and "time" in event:
        times = [event["time"]]

    # Fail fast per config validation rules
    if not dates:
        raise ValueError(
            f"Event missing required '{date_time_spec['date_field']}' field: {event.get('title', 'Unknown')}"
        )

    # Create occurrences based on zip_rule
    occurrences = []
    zip_rule = date_time_spec.get("zip_rule", "pairwise_equal_length")

    if zip_rule == "pairwise_equal_length":
        # Pair dates and times by index
        for i, date in enumerate(dates):
            time = times[i] if i < len(times) else times[0] if times else "TBD"
            occurrences.append(
                {
                    "date": date,
                    "time": time,
                    "url": event.get("url", ""),
                    "venue": event.get("venue", ""),
                }
            )
    else:
        # Use first time for all dates
        default_time = times[0] if times else "TBD"
        for date in dates:
            occurrences.append(
                {
                    "date": date,
                    "time": default_time,
                    "url": event.get("url", ""),
                    "venue": event.get("venue", ""),
                }
            )

    return occurrences


def should_group_by_title(event_type: str) -> bool:
    """Determine if events of this type should be grouped by title (movies)"""
    return event_type == "movie"


def create_unique_key(event: dict) -> str:
    """Create unique key for non-movie events to avoid duplicates"""
    dates = event.get("dates", [])
    times = event.get("times", [])

    dates_str = ",".join(dates) if dates else "TBD"
    times_str = ",".join(times) if times else "TBD"

    return f"{event.get('title', 'Unknown')} - {dates_str} {times_str}"


def finalize_website_data(combined_data: dict) -> list:
    """Convert combined data dict to final website list with IDs and sorting"""
    website_data = []

    for title, event_data in combined_data.items():
        # Create ID from title
        event_id = (
            title.lower()
            .replace(" ", "-")
            .replace("'", "")
            .replace('"', "")
            .replace(":", "")
            .replace(",", "")
        )
        event_data["id"] = event_id

        # Sort occurrences by date and time (handle None values)
        event_data["occurrences"].sort(
            key=lambda x: (x.get("date") or "9999-12-31", x.get("time") or "23:59")
        )

        website_data.append(event_data)

    # Sort by the earliest occurrence date/time so upcoming events appear first
    def first_occurrence_key(item):
        occurrences = item.get("occurrences", [])
        if not occurrences:
            return ("9999-12-31", "23:59")
        first = min(
            occurrences,
            key=lambda s: (s.get("date") or "9999-12-31", s.get("time") or "23:59"),
        )
        return (first.get("date") or "9999-12-31", first.get("time") or "23:59")

    website_data.sort(key=first_occurrence_key)

    return website_data


def generate_website_data(events):
    """Generate JSON data for the website using master_config.yaml templates"""
    print("Generating website data using config-driven approach...")

    # Load configuration
    config = ConfigLoader()
    templates = config._config.get("templates", {})
    date_time_spec = config.get_date_time_spec()

    # Group events by type using ontology
    events_by_type = {}
    for event in events:
        event_type = determine_event_type(event)
        if event_type not in events_by_type:
            events_by_type[event_type] = []
        events_by_type[event_type].append(event)

    print(
        f"Processing events by type: { {k: len(v) for k, v in events_by_type.items()} }"
    )

    # Process events using templates
    combined_data = {}

    for event_type, type_events in events_by_type.items():
        template = templates.get(event_type, templates.get("other", {}))
        print(
            f"Processing {len(type_events)} {event_type} events with template: {template.get('fields', [])}"
        )

        for event in type_events:
            # Build output using template
            output_event = build_event_from_template(event, template, config)

            # Handle grouping (movies vs unique events)
            if should_group_by_title(event_type):
                # Group movies by title
                group_key = event["title"]
                if group_key not in combined_data:
                    combined_data[group_key] = output_event
                    combined_data[group_key]["occurrences"] = []
                # Add occurrence
                combined_data[group_key]["occurrences"].extend(
                    create_occurrences_from_arrays(event, date_time_spec)
                )
            else:
                # Unique event (concert, book_club, etc.)
                unique_key = create_unique_key(event)
                combined_data[unique_key] = output_event
                combined_data[unique_key]["occurrences"] = (
                    create_occurrences_from_arrays(event, date_time_spec)
                )

    # Finalize and return website data
    return finalize_website_data(combined_data)


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

        # Process and enrich events
        print("Processing and enriching events...")
        enriched_events = processor.process_events(upcoming_events)
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
