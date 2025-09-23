#!/usr/bin/env python3
"""
Example script demonstrating Phase Two enrichment layer usage
"""

import os
import sys
import json
from datetime import datetime

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src.config_loader import ConfigLoader
from src.enrichment_layer import EnrichmentLayer
from src.scrapers.hyperreal_scraper import HyperrealScraper
from src.scrapers.paramount_scraper import ParamountScraper
from src.scrapers.alienated_majesty_scraper import AlienatedMajestyBooksScraper


def demo_direct_enrichment():
    """Demonstrate direct enrichment of a single event"""
    print("\n" + "="*60)
    print("DEMO: Direct Enrichment of Single Event")
    print("="*60)
    
    # Initialize components
    config = ConfigLoader()
    enrichment = EnrichmentLayer(config_loader=config)
    
    # Sample event from Phase One (normalized but not enriched)
    sample_event = {
        "title": "Dune: Part Two",
        "description": "Epic sci-fi sequel directed by Denis Villeneuve. Paul Atreides unites with the Fremen to fight the Harkonnens.",
        "dates": ["2025-10-15", "2025-10-16"],
        "times": ["19:00", "21:30"],
        "venue": "Hyperreal Film Club",
        "url": "https://example.com/dune-part-two"
    }
    
    print("\nOriginal Event (Phase One output):")
    print(json.dumps(sample_event, indent=2))
    
    # Apply enrichment for Hyperreal venue
    enriched_event = enrichment.run_enrichment(sample_event, "hyperreal")
    
    print("\nEnriched Event (Phase Two output):")
    print(json.dumps(enriched_event, indent=2))
    
    # Show telemetry
    print("\nEnrichment Telemetry:")
    print(json.dumps(enrichment.get_telemetry(), indent=2))


def demo_scraper_integration():
    """Demonstrate scraper integration with enrichment"""
    print("\n" + "="*60)
    print("DEMO: Scraper Integration with Enrichment")
    print("="*60)
    
    # Initialize config
    config = ConfigLoader()
    
    # Test with Hyperreal scraper (classification enabled)
    print("\n--- Hyperreal Scraper (Classification Enabled) ---")
    hyperreal_scraper = HyperrealScraper(config=config)
    
    # Mock some events for demo (normally would scrape from website)
    mock_events = [
        {
            "title": "The Zone of Interest",
            "description": "A chilling film about the commandant of Auschwitz and his family living next to the camp.",
            "dates": ["2025-10-20"],
            "times": ["19:30"],
            "venue": "Hyperreal Film Club"
        },
        {
            "title": "Experimental Sound Performance",
            "description": "An evening of experimental music and sound art.",
            "dates": ["2025-10-22"],
            "times": ["20:00"],
            "venue": "Hyperreal Film Club"
        }
    ]
    
    # Override scrape_events for demo
    hyperreal_scraper.scrape_events = lambda: mock_events
    
    # Run scraping with enrichment
    enriched_events = hyperreal_scraper.scrape_and_enrich()
    
    print("\nEnriched Events from Hyperreal:")
    for i, event in enumerate(enriched_events, 1):
        print(f"\nEvent {i}:")
        print(f"  Title: {event.get('title')}")
        print(f"  Category: {event.get('event_category', 'Not classified')}")
        print(f"  Enrichment Status: {event.get('enrichment_meta', {}).get('status', 'N/A')}")
        if event.get('director'):
            print(f"  Director: {event['director']}")
        if event.get('runtime_minutes'):
            print(f"  Runtime: {event['runtime_minutes']} minutes")
    
    # Test with AlienatedMajesty scraper (assumed category)
    print("\n--- Alienated Majesty Scraper (Assumed Category: book_club) ---")
    am_scraper = AlienatedMajestyBooksScraper(config=config)
    
    # Mock book club events
    mock_book_events = [
        {
            "title": "NYRB Book Club - The Leopard",
            "description": "Discussion of Giuseppe Tomasi di Lampedusa's The Leopard",
            "dates": ["2025-10-25"],
            "times": ["18:30"],
            "venue": "Alienated Majesty Books",
            "series": "NYRB Book Club"
        }
    ]
    
    am_scraper.scrape_events = lambda: mock_book_events
    enriched_book_events = am_scraper.scrape_and_enrich()
    
    print("\nEnriched Events from Alienated Majesty:")
    for event in enriched_book_events:
        print(f"\n  Title: {event.get('title')}")
        print(f"  Category: {event.get('event_category')}")
        print(f"  Series: {event.get('series')}")
        print(f"  Book: {event.get('book', 'Not extracted')}")
        print(f"  Author: {event.get('author', 'Not extracted')}")


def demo_validation_scenarios():
    """Demonstrate validation and error handling"""
    print("\n" + "="*60)
    print("DEMO: Validation and Error Handling")
    print("="*60)
    
    config = ConfigLoader()
    enrichment = EnrichmentLayer(config_loader=config)
    
    # Test event with validation errors
    invalid_event = {
        "title": "Test Movie",
        "dates": ["2025-10-01", "2025-10-02"],  # 2 dates
        "times": ["19:00"],  # 1 time - mismatch!
        "venue": "Test Cinema"
    }
    
    print("\nTesting event with mismatched dates/times:")
    print(json.dumps(invalid_event, indent=2))
    
    try:
        enriched = enrichment.run_enrichment(invalid_event, "paramount")
    except ValueError as e:
        print(f"\nValidation Error (as expected): {e}")
    
    # Test event with invalid date format
    invalid_date_event = {
        "title": "Test Movie",
        "dates": ["10/01/2025"],  # Wrong format
        "times": ["19:00"],
        "venue": "Test Cinema"
    }
    
    print("\nTesting event with invalid date format:")
    print(json.dumps(invalid_date_event, indent=2))
    
    try:
        enriched = enrichment.run_enrichment(invalid_date_event, "paramount")
    except ValueError as e:
        print(f"\nValidation Error (as expected): {e}")


def demo_telemetry_aggregation():
    """Demonstrate telemetry tracking across multiple enrichments"""
    print("\n" + "="*60)
    print("DEMO: Telemetry Aggregation")
    print("="*60)
    
    config = ConfigLoader()
    enrichment = EnrichmentLayer(config_loader=config)
    
    # Process multiple events to accumulate telemetry
    test_events = [
        {
            "title": "Inception",
            "description": "Christopher Nolan's mind-bending thriller",
            "dates": ["2025-10-01"],
            "times": ["20:00"],
            "venue": "Cinema"
        },
        {
            "title": "Book Club Meeting",
            "description": "Monthly book discussion",
            "dates": ["2025-10-05"],
            "times": ["18:00"],
            "venue": "Library"
        },
        {
            "title": "Symphony Concert",
            "description": "Classical music performance",
            "dates": ["2025-10-10"],
            "times": ["19:30"],
            "venue": "Concert Hall"
        }
    ]
    
    print("\nProcessing multiple events for classification...")
    for event in test_events:
        try:
            enrichment.run_enrichment(event, "hyperreal")
            print(f"  ✓ Processed: {event['title']}")
        except Exception as e:
            print(f"  ✗ Failed: {event['title']} - {e}")
    
    # Display final telemetry
    print("\nFinal Telemetry Report:")
    telemetry = enrichment.get_telemetry()
    print(f"  Total Classifications: {telemetry['total_classifications']}")
    print(f"  By Category:")
    for category, count in telemetry['classifications_by_label'].items():
        print(f"    - {category}: {count}")
    print(f"  Abstentions: {telemetry['abstentions']}")
    print(f"  Fields Accepted: {telemetry['fields_accepted']}")
    print(f"  Fields Rejected: {telemetry['fields_rejected']}")
    print(f"  Enrichment Failures: {telemetry['enrichment_failures']}")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("PHASE TWO ENRICHMENT LAYER DEMONSTRATION")
    print("="*60)
    
    # Check for API keys
    if not os.getenv("ANTHROPIC_API_KEY") and not os.getenv("PERPLEXITY_API_KEY"):
        print("\n⚠️  Warning: No LLM API keys found in environment")
        print("   Set ANTHROPIC_API_KEY or PERPLEXITY_API_KEY for full functionality")
        print("   Running in demo mode with mocked LLM responses...\n")
    
    # Run demonstrations
    try:
        demo_direct_enrichment()
    except Exception as e:
        print(f"\n❌ Direct enrichment demo failed: {e}")
    
    try:
        demo_scraper_integration()
    except Exception as e:
        print(f"\n❌ Scraper integration demo failed: {e}")
    
    try:
        demo_validation_scenarios()
    except Exception as e:
        print(f"\n❌ Validation demo failed: {e}")
    
    try:
        demo_telemetry_aggregation()
    except Exception as e:
        print(f"\n❌ Telemetry demo failed: {e}")
    
    print("\n" + "="*60)
    print("DEMONSTRATION COMPLETE")
    print("="*60)