import os
import pytest
import json
from dotenv import load_dotenv
from src.scraper import AlienatedMajestyBooksScraper, FirstLightAustinScraper

# Load environment variables from .env file for local testing
load_dotenv()

# Check if the Firecrawl API key is available
firecrawl_api_key = os.getenv('FIRECRAWL_API_KEY')
is_firecrawl_configured = firecrawl_api_key is not None

# Define a reason for skipping tests if the API key is not configured
skip_reason = "Firecrawl API key is not configured. Set FIRECRAWL_API_KEY in your .env file."

def handle_no_events(scraper):
    """
    Handles the case where no events are found by a scraper during a test.
    It fetches, prints, and saves the raw HTML, Markdown, and content for debugging.
    """
    scraper_name = scraper.__class__.__name__
    url = f"{scraper.base_url}/book-club"
    print(f"\\n[DEBUG] No events found by {scraper_name}. Fetching raw page content for inspection...")
    
    try:
        # Request both HTML and Markdown from Firecrawl
        scrape_result = scraper.firecrawl.scrape_url(url, params={'formats': ['html', 'markdown']})
        
        html_content = scrape_result.get('html', 'No HTML content returned.')
        markdown_content = scrape_result.get('markdown', 'No Markdown content returned.')
        # The 'content' key is sometimes available as a fallback to the raw text
        raw_content = scrape_result.get('content', 'No raw content returned.')

        # --- Print all content forms to the console ---
        print("\\n" + "="*35 + " RAW HTML " + "="*35)
        print(html_content)
        print("="*80 + "\\n")
        
        print("\\n" + "="*32 + " FIRECRAWL MARKDOWN " + "="*32)
        print(markdown_content)
        print("="*80 + "\\n")
        
        # --- Save content to files for easier review ---
        html_output_file = f"debug_{scraper_name}_output.html"
        md_output_file = f"debug_{scraper_name}_output.md"

        with open(html_output_file, "w", encoding="utf-8") as f:
            f.write(html_content)
        with open(md_output_file, "w", encoding="utf-8") as f:
            f.write(markdown_content)

        # Also save the raw 'content' if it's different from markdown
        if raw_content != markdown_content and raw_content != 'No raw content returned.':
            content_output_file = f"debug_{scraper_name}_output.txt"
            with open(content_output_file, "w", encoding="utf-8") as f:
                f.write(raw_content)
            print(f"NOTE: Raw content differs from Markdown. Also saved to '{content_output_file}'\\n")

        pytest.fail(
            f"{scraper_name} returned no events. "
            f"The raw HTML and Markdown have been printed above and saved to '{html_output_file}' and '{md_output_file}'. "
            f"Please inspect them to see if this is expected."
        )

    except Exception as e:
        pytest.fail(f"An error occurred during debug fetch for {scraper_name}: {e}")


@pytest.mark.skipif(not is_firecrawl_configured, reason=skip_reason)
def test_alienated_majesty_scraper():
    """
    Tests the AlienatedMajestyBooksScraper to ensure it can fetch and parse events.
    If no events are found, it provides debugging output.
    """
    print("\\n--- Testing AlienatedMajestyBooksScraper ---")
    scraper = AlienatedMajestyBooksScraper()
    assert scraper.firecrawl is not None, "Firecrawl client should be initialized."

    events = scraper.scrape_calendar()

    assert isinstance(events, list), f"Expected a list of events, but got {type(events)}"

    if not events:
        handle_no_events(scraper)
    else:
        print(f"Found {len(events)} event(s).")
        first_event = events[0]
        print("Sample event:")
        print(json.dumps(first_event, indent=2))

        # Validate the structure of the event
        assert 'title' in first_event
        assert 'date' in first_event
        assert 'book' in first_event
        assert 'author' in first_event
        print("Sample event structure looks correct.")

@pytest.mark.skipif(not is_firecrawl_configured, reason=skip_reason)
def test_first_light_scraper():
    """
    Tests the FirstLightAustinScraper to ensure it can fetch and parse events.
    If no events are found, it provides debugging output.
    """
    print("\\n--- Testing FirstLightAustinScraper ---")
    scraper = FirstLightAustinScraper()
    assert scraper.firecrawl is not None, "Firecrawl client should be initialized."

    events = scraper.scrape_calendar()

    assert isinstance(events, list), f"Expected a list of events, but got {type(events)}"

    if not events:
        handle_no_events(scraper)
    else:
        print(f"Found {len(events)} event(s).")
        first_event = events[0]
        print("Sample event:")
        print(json.dumps(first_event, indent=2))

        # Validate the structure of the event
        assert 'title' in first_event
        assert 'date' in first_event
        assert 'book' in first_event
        assert 'author' in first_event
        print("Sample event structure looks correct.") 