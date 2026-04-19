#!/usr/bin/env python3
"""
Website data updater for Culture Calendar
Generates JSON data for the GitHub Pages website
Supports multiple venues: AFS, Hyperreal Movie Club, Paramount Theatre, and others
"""

import argparse
import json
import os
import re
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


BANNED_PHRASES = (
    "haunting",
    "profound",
    "profound meditation",
    "resonates",
    "resonates deeply",
    "masterfully",
    "masterfully crafted",
    "breathtaking",
    "visceral",
    "lush",
    "luminous",
    "poignant",
    "exquisite",
    "meditation on",
    "in this film we see",
    "in this work we see",
    "tour de force",
    "transcendent",
)

BANNED_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(p) for p in BANNED_PHRASES) + r")\b",
    re.IGNORECASE,
)


def strip_banned_phrases(text: str) -> str:
    """Remove banned phrases from text, replacing with generic alternatives."""
    if not text:
        return text
    replacements = {
        "profound": "deep",
        "profound meditation": "deep exploration",
        "haunting": "memorable",
        "visceral": "intense",
        "resonates": "connects",
        "resonates deeply": "deeply connects",
        "masterfully": "skillfully",
        "masterfully crafted": "skillfully crafted",
        "breathtaking": "striking",
        "lush": "rich",
        "luminous": "bright",
        "poignant": "moving",
        "exquisite": "refined",
        "meditation on": "reflection on",
        "in this film we see": "the film shows",
        "in this work we see": "the work shows",
        "tour de force": "showcase",
        "transcendent": "elevated",
    }
    for phrase, replacement in replacements.items():
        text = re.sub(
            r"\b" + re.escape(phrase) + r"\b",
            replacement,
            text,
            flags=re.IGNORECASE,
        )
    return text


def strip_banned_from_events(events: list) -> list:
    """Remove banned phrases from event descriptions and summaries."""
    for event in events:
        if "description" in event and event["description"]:
            event["description"] = strip_banned_phrases(event["description"])
        if "one_liner_summary" in event and event["one_liner_summary"]:
            event["one_liner_summary"] = strip_banned_phrases(event["one_liner_summary"])
    return events


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
    """Determine event type from event data, with robust normalization.

    - Map common variants (screening/film/movie_screening) to 'movie'
    - Infer 'movie' by venue heuristics (AFS/Hyperreal) when type is missing
    - Infer 'movie' if film-centric fields are present
    - Fallback to provided type or 'other'
    """
    raw_type = (event.get("type") or "").strip().lower()
    venue = (event.get("venue") or "").strip().lower()

    # Normalize common movie variants
    movie_aliases = {"screening", "film", "movie_screening", "movie-showing", "showing"}
    if raw_type in movie_aliases:
        return "movie"

    # Venue-based inference for movie houses
    movie_venues = {"afs", "austin film society", "hyperreal", "hyperreal movie club"}
    if not raw_type and venue in movie_venues:
        return "movie"

    # Field-based inference (typical film metadata)
    if any(k in event for k in ("director", "runtime", "runtime_minutes", "release_year")):
        # Don't overwrite explicit non-movie types
        if raw_type in ("", "other"):
            return "movie"

    # Default
    return raw_type or event.get("type", "other") or "other"


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
        elif field == "review_confidence":
            # Pull AI-derived confidence so the UI can route low-confidence
            # reviews into the "pending more research" bucket.
            output[field] = ai_rating.get("review_confidence", "unknown")
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


def create_screenings_from_arrays(event: dict, date_time_spec: dict) -> list:
    """Create screenings array from date/time arrays with validation"""
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

    # Create screenings based on zip_rule
    screenings = []
    zip_rule = date_time_spec.get("zip_rule", "pairwise_equal_length")

    if zip_rule == "pairwise_equal_length":
        # Pair dates and times by index
        for i, date in enumerate(dates):
            time = times[i] if i < len(times) else times[0] if times else "TBD"
            screenings.append(
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
            screenings.append(
                {
                    "date": date,
                    "time": default_time,
                    "url": event.get("url", ""),
                    "venue": event.get("venue", ""),
                }
            )

    return screenings


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

        # Sort screenings by date and time (handle None values)
        event_data["screenings"].sort(
            key=lambda x: (x.get("date") or "9999-12-31", x.get("time") or "23:59")
        )

        # Hoist dates/times from screenings so they always match
        screening_dates = sorted({s["date"] for s in event_data["screenings"] if s.get("date")})
        screening_times = sorted({s["time"] for s in event_data["screenings"] if s.get("time")})
        event_data["dates"] = screening_dates
        event_data["times"] = screening_times

        website_data.append(event_data)

    # Merge companion events (e.g. Paper Cuts pop-up bookshop) INTO the
    # matching film event so the site shows one card per theatrical outing
    # rather than two separate listings for the same showtime.
    website_data = _merge_companion_events(website_data)

    # Sort by the earliest occurrence date/time so upcoming events appear first
    def first_occurrence_key(item):
        screenings = item.get("screenings", [])
        if not screenings:
            return ("9999-12-31", "23:59")
        first = min(
            screenings,
            key=lambda s: (s.get("date") or "9999-12-31", s.get("time") or "23:59"),
        )
        return (first.get("date") or "9999-12-31", first.get("time") or "23:59")

    website_data.sort(key=first_occurrence_key)

    return website_data


def _merge_companion_events(events: list) -> list:
    """Fold Paper-Cuts-style companion events into their paired film event.

    A companion carries `companion_of = {"title": <paired_film>, "date": <iso>}`
    set by the scraper. We find the film event whose title contains the
    paired film title (case-insensitive) AND whose screenings share the
    date, attach it under `companion_events`, and drop the companion from
    the top-level list. If no match is found the companion survives
    unchanged so it still surfaces on the site.
    """
    # Index film events by (lowered title, date) for fast lookup.
    film_index: dict[tuple[str, str], int] = {}
    for idx, ev in enumerate(events):
        if ev.get("type") in ("movie", "screening"):
            title_key = (ev.get("title") or "").lower()
            for s in ev.get("screenings", []):
                d = s.get("date")
                if d:
                    film_index[(title_key, d)] = idx

    remaining: list = []
    for ev in events:
        companion_hint = ev.get("companion_of")
        if not companion_hint:
            remaining.append(ev)
            continue

        paired_title = (companion_hint.get("title") or "").lower().strip()
        paired_date = companion_hint.get("date")
        target_idx = None
        for (film_title, film_date), film_idx in film_index.items():
            if (
                film_date == paired_date
                and paired_title
                and paired_title in film_title
            ):
                target_idx = film_idx
                break

        if target_idx is None:
            # No matching film event; keep the companion standalone so it
            # still surfaces on the site.
            remaining.append(ev)
            continue

        events[target_idx].setdefault("companion_events", []).append(
            {
                "title": ev.get("title") or "",
                "venue": ev.get("venue") or "",
                "time": (ev.get("times") or [""])[0] if ev.get("times") else "",
                "description": ev.get("description") or "",
                "source_url": ev.get("url") or "",
            }
        )
        # Dropping the companion from the top-level list — it lives inside
        # the film event now.

    return remaining


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

    counts = {k: len(v) for k, v in events_by_type.items()}
    print(f"Processing events by type: {counts}")
    if counts.get("movie", 0) == 0 and any(e.get("venue") in {"AFS", "Hyperreal"} for e in events):
        print("WARNING: 0 'movie' events after typing, but AFS/Hyperreal events exist → check type normalization/templates")

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
            if config.should_group_by_title(event_type):
                # Group movies by title
                group_key = event["title"]
                if group_key not in combined_data:
                    combined_data[group_key] = output_event
                    combined_data[group_key]["screenings"] = []
                # Add occurrence
                combined_data[group_key]["screenings"].extend(
                    create_screenings_from_arrays(event, date_time_spec)
                )
            else:
                # Unique event (concert, book_club, etc.)
                unique_key = create_unique_key(event)
                combined_data[unique_key] = output_event
                combined_data[unique_key]["screenings"] = (
                    create_screenings_from_arrays(event, date_time_spec)
                )

    # Finalize and return website data
    return finalize_website_data(combined_data)


def main(
    test_week: bool = False,
    force_reprocess: bool = False,
    validate: bool = False,
    pilot: bool = False,
):
    """Generate website data.

    Args:
        test_week: If True, limit recurring-event generation to ~2 weeks
            ahead instead of ~8. Does not affect venue scraping — each
            venue's `scrape_events()` always pulls its full calendar.
        force_reprocess: If True, force re-processing of all events (ignore cache).
        validate: If True, enable smart validation with fail-fast mechanisms.
        pilot: If True, restrict to 5 hardcoded pilot titles and output to data-pilot.json.
    """
    if pilot:
        os.environ["PILOT_UPLIFT"] = "1"
        # Pilot implies force_reprocess so the dossier injection produces fresh output
        # rather than returning cached reviews from the non-pilot run.
        force_reprocess = True

    print(f"Culture Calendar Website Update - Starting at {datetime.now()}")

    try:
        # Initialize components
        scraper = MultiVenueScraper()
        processor = EventProcessor(force_reprocess=force_reprocess, pilot_mode=pilot)

        # Scrape all venues (including classical music from JSON)
        print("Fetching calendar data from all venues...")
        events = scraper.scrape_all_venues(target_week=test_week)
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
        dropped_on_details = 0
        for event in events:
            etype = event.get("type")
            if etype in ["screening", "book_club"]:
                try:
                    details = scraper.get_event_details(event)
                    if isinstance(details, dict):
                        event.update(details)
                    detailed_events.append(event)
                except Exception as e:
                    # Do NOT drop the event; keep minimal data so movies still publish
                    print(
                        f"Warning: details fetch failed for {event.get('title','Unknown')} ({etype}): {e} — keeping list-level data"
                    )
                    detailed_events.append(event)
            elif etype in ["concert", "movie"]:
                # Classical events and normalized movie events already have sufficient details
                detailed_events.append(event)
            else:
                # Keep other types too (e.g., if typing happens later)
                detailed_events.append(event)
        if dropped_on_details:
            print(f"Note: {dropped_on_details} events lost during details stage (should be 0)")

        # Keep all events - no date filtering applied
        upcoming_events = detailed_events
        print(f"Processing {len(upcoming_events)} total events")

        # Filter to pilot titles if --pilot flag is set
        if pilot:
            pilot_titles = {
                "THE STRANGER (L\u2019ETRANGER)",
                "LANCELOT DU LAC",
                "PALESTINE \u201936",
                "A SERIOUS MAN",
                "SHIFTING BASELINES",
            }
            upcoming_events = [
                e for e in upcoming_events
                if e.get("title", "") in pilot_titles
            ]
            print(f"Filtered to {len(upcoming_events)} pilot events")

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

        # Strip banned phrases from descriptions and summaries
        website_data = strip_banned_from_events(website_data)

        # Save JSON data
        output_file = "docs/data-pilot.json" if pilot else "docs/data.json"
        with open(output_file, "w") as f:
            json.dump(website_data, f, indent=2)

        print(f"Generated {output_file} with {len(website_data)} events")
        # Save per-source update timestamps
        save_update_info(scraper.last_updated)

        print("Website update completed successfully!")

    except Exception as e:
        print(f"Error during website update: {e}")
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate website data for Culture Calendar"
    )
    parser.add_argument(
        "--test-week",
        action="store_true",
        help="Limit recurring-event generation to ~2 weeks ahead instead of ~8",
    )
    parser.add_argument(
        "--force-reprocess",
        action="store_true",
        help="Force re-processing of all events (ignore cache)",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Enable smart validation with fail-fast mechanisms",
    )
    parser.add_argument(
        "--pilot",
        action="store_true",
        help="Restrict to 5 hardcoded pilot titles and output to data-pilot.json",
    )
    args = parser.parse_args()
    main(
        test_week=args.test_week,
        force_reprocess=args.force_reprocess,
        validate=args.validate,
        pilot=args.pilot,
    )
