"""
One-line summary generator for Culture Calendar events
Uses Anthropic's Claude API to generate concise event summaries
"""

import os
import json
import time
from typing import Dict, Optional
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()


class SummaryGenerator:
    def __init__(self):
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        if not self.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY not found in environment variables")

        self.client = Anthropic(api_key=self.anthropic_api_key)
        self.summary_cache = {}
        self._load_cache()

    def _load_cache(self):
        """Load cached summaries from disk"""
        cache_path = "cache/summary_cache.json"
        try:
            if os.path.exists(cache_path):
                with open(cache_path, "r") as f:
                    self.summary_cache = json.load(f)
                print(f"Loaded {len(self.summary_cache)} cached summaries")
        except Exception as e:
            print(f"Could not load summary cache: {e}")
            self.summary_cache = {}

    def _save_cache(self):
        """Save summaries to disk cache"""
        cache_path = "cache/summary_cache.json"
        try:
            os.makedirs("cache", exist_ok=True)
            with open(cache_path, "w") as f:
                json.dump(self.summary_cache, f, indent=2)
            print(f"Saved {len(self.summary_cache)} summaries to cache")
        except Exception as e:
            print(f"Could not save summary cache: {e}")

    def generate_summary(
        self, event: Dict, force_regenerate: bool = False
    ) -> Optional[str]:
        """
        Generate a one-line summary for an event

        Args:
            event: Event dictionary with title, description, type, etc.
            force_regenerate: If True, ignore cache and generate new summary

        Returns:
            One-line summary string or None if generation fails
        """
        # Validate event data
        if not self._validate_event_data(event):
            print(
                f"  Insufficient data for summary generation: {event.get('title', 'Unknown')}"
            )
            return None

        cache_key = (
            f"{event.get('title', '').upper().strip()}_{event.get('type', 'unknown')}"
        )

        # Check cache first (unless forcing regeneration)
        if not force_regenerate and cache_key in self.summary_cache:
            print(f"  Using cached summary for {event.get('title')}")
            return self.summary_cache[cache_key]

        try:
            summary = self._call_claude_api(event)
            if summary:
                self.summary_cache[cache_key] = summary
                self._save_cache()
            return summary
        except Exception as e:
            print(f"Error generating summary for {event.get('title')}: {e}")
            return None

    def _validate_event_data(self, event: Dict) -> bool:
        """Validate that event has sufficient data for summary generation"""
        # Must have a title
        if not event.get("title", "").strip():
            return False

        # Should have either a description or basic metadata
        has_description = bool(event.get("description", "").strip())
        has_basic_metadata = bool(
            event.get("director") or event.get("venue") or event.get("type")
        )

        if not (has_description or has_basic_metadata):
            return False

        return True

    def _call_claude_api(self, event: Dict) -> Optional[str]:
        """Call Claude API to generate one-line summary"""

        # Build context for the event
        event_type = event.get("type", "unknown")
        title = event.get("title", "Unknown")
        description = event.get("description", "")
        venue = event.get("venue", "")

        # Craft prompt based on event type
        if event_type == "screening" or event.get("isMovie", False):
            prompt = self._build_movie_prompt(title, description, event)
        elif event_type == "concert":
            prompt = self._build_concert_prompt(title, description, event)
        elif event_type == "book_club":
            prompt = self._build_book_prompt(title, description, event)
        else:
            prompt = self._build_generic_prompt(title, description, event)

        try:
            # Add rate limiting
            time.sleep(0.5)

            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=100,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}],
            )

            summary = response.content[0].text.strip()

            # Clean up the response - remove quotes and ensure it's one line
            summary = summary.strip("\"'").replace("\n", " ").strip()

            # Remove common introductory phrases
            prefixes_to_remove = [
                "Based on this analysis",
                "Based on the analysis",
                "I apologize, but",
                "I notice that",
                "Here's a summary:",
                "Summary:",
                "The summary is:",
                "This is a",
                "This film is",
            ]

            for prefix in prefixes_to_remove:
                if summary.lower().startswith(prefix.lower()):
                    # Remove prefix and everything up to a colon or comma
                    remaining = summary[len(prefix) :].strip()
                    if remaining.startswith(":") or remaining.startswith(","):
                        summary = remaining[1:].strip().strip("\"'")
                    else:
                        summary = remaining.strip("\"'")
                    break

            # Ensure it's not too long (max ~100 characters for good UI)
            if len(summary) > 100:
                summary = summary[:97] + "..."

            print(f"  Generated summary: {summary}")
            return summary

        except Exception as e:
            print(f"Claude API error: {e}")
            return None

    def _build_movie_prompt(self, title: str, description: str, event: Dict) -> str:
        """Build prompt for movie events"""
        director = event.get("director", "")
        country = event.get("country", "")
        year = event.get("year", "")

        # Extract key information from the AI description if available
        if description and len(description) > 100:
            prompt = f"""Create a compelling one-line summary (8-12 words) that captures this film's essence.

Title: {title}
Director: {director}
Country: {country}
Year: {year}

Analysis:
{description}

Based on this analysis, provide ONLY a concise summary that captures the film's mood, genre, and key themes. No explanations or introductions - just the summary.

Examples:
- "Bleak UK road film about obsession and loneliness"
- "Haunting Japanese adaptation exploring ambition and betrayal"
- "Surreal Lynch thriller diving into Hollywood's dark underbelly"

Summary:"""
        else:
            # Fallback for events without rich descriptions
            prompt = f"""Generate a one-line summary for this film screening based on available information.

Title: {title}
Director: {director}
Country: {country}
Year: {year}

Write a compelling summary (8-12 words) that captures what viewers can expect. Examples:
- "Classic Kurosawa samurai epic with stunning cinematography"
- "French New Wave romance set in 1960s Paris"
- "Contemporary indie drama exploring family dynamics"

Your one-line summary (8-12 words):"""

        return prompt

    def _build_concert_prompt(self, title: str, description: str, event: Dict) -> str:
        """Build prompt for concert events"""
        venue = event.get("venue", "")
        composers = event.get("composers", [])
        featured_artist = event.get("featured_artist", "")

        if description and len(description) > 100:
            return f"""Based on this detailed concert analysis, create a compelling one-line summary that captures the concert's essence in 8-12 words.

Title: {title}
Venue: {venue}
Composers: {', '.join(composers) if composers else 'Various'}
Featured Artist: {featured_artist}

Detailed Analysis:
{description}

Extract the core musical style, period, and atmosphere from this analysis. Examples:
- "Intimate chamber music featuring Baroque masters in candlelit setting"
- "Powerful symphonic works showcasing romantic-era orchestration"
- "Haunting medieval chants performed by virtuoso ensemble"

Your one-line summary (8-12 words):"""
        else:
            return f"""Generate a one-line summary for this classical music concert.

Title: {title}
Venue: {venue}
Composers: {', '.join(composers) if composers else 'Various'}
Featured Artist: {featured_artist}

Write a compelling summary (8-12 words) that captures the musical experience. Examples:
- "Symphony orchestra performing Beethoven's most beloved works"
- "Chamber ensemble exploring Bach's intricate counterpoint"
- "Contemporary classical featuring innovative string arrangements"

Your one-line summary (8-12 words):"""

    def _build_book_prompt(self, title: str, description: str, event: Dict) -> str:
        """Build prompt for book club events"""
        venue = event.get("venue", "")

        if description and len(description) > 100:
            return f"""Based on this detailed book analysis, create a compelling one-line summary that captures the book's essence in 8-12 words.

Event: {title}
Venue: {venue}

Detailed Analysis:
{description}

Extract the core themes, genre, and literary significance from this analysis. Examples:
- "Literary fiction exploring family secrets and generational trauma"
- "Haunting sci-fi meditation on consciousness and memory"
- "Powerful memoir chronicling immigration and cultural identity"

Your one-line summary (8-12 words):"""
        else:
            return f"""Generate a one-line summary for this book club discussion.

Event: {title}
Venue: {venue}

Write a compelling summary (8-12 words) that captures the book's appeal. Examples:
- "Contemporary novel examining modern relationships and technology"
- "Classic literature exploring themes of justice and morality"
- "Thought-provoking nonfiction about social change"

Your one-line summary (8-12 words):"""

    def _build_generic_prompt(self, title: str, description: str, event: Dict) -> str:
        """Build prompt for other event types"""
        venue = event.get("venue", "")
        event_type = event.get("type", "event")

        return f"""Generate a one-line summary for this cultural event that captures its essence and appeal.

Title: {title}
Type: {event_type}
Venue: {venue}
Description: {description[:500]}...

Write a single, concise sentence (max 12 words) that captures the event's character, themes, and atmosphere.

Your one-line summary:"""
