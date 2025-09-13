"""
Event processor for enriching and rating events
"""

import os
import time
from datetime import datetime
from typing import Dict, List

import requests
from dotenv import load_dotenv

from .summary_generator import SummaryGenerator

load_dotenv()


class EventProcessor:
    def __init__(self, force_reprocess: bool = False):
        self.perplexity_api_key = os.getenv("PERPLEXITY_API_KEY")
        self.movie_cache = {}  # Cache AI ratings to avoid reprocessing
        self.force_reprocess = force_reprocess
        self.reprocessed_titles = set()  # Track titles already reprocessed in this run

        # Initialize summary generator
        try:
            self.summary_generator = SummaryGenerator()
        except ValueError as e:
            print(f"Warning: Could not initialize summary generator: {e}")
            self.summary_generator = None

    def process_events(self, events: List[Dict]) -> List[Dict]:
        """Process and enrich all events"""
        enriched_events = []
        len(events)
        processed_count = 0

        for i, event in enumerate(events, 1):
            try:
                # Process screenings, movies, concerts, and book clubs
                if event.get("type") not in ["screening", "movie", "concert", "book_club"]:
                    continue

                # Preserve work hours marking if it exists
                if "isWorkHours" in event:
                    # Keep the field as-is from the input
                    pass

                processed_count += 1
                print(f"Processing ({processed_count}): {event['title']}")

                # Skip AI processing for recurring events - they have predefined content
                if event.get("is_recurring"):
                    print(f"  Skipping AI processing for recurring event")
                    # Set simple defaults for recurring events
                    event["ai_rating"] = {
                        "score": 7,
                        "summary": event.get("description", "Weekly recurring event"),
                    }
                    event["oneLinerSummary"] = "Weekly literary discussion group"
                    enriched_events.append(event)
                    continue

                # Get AI rating (with caching)
                event_title = event["title"].upper().strip()
                
                # Check if we need to process this title
                should_process = False
                is_first_time_reprocessing = False
                if event_title not in self.movie_cache:
                    # Not in cache, need to process
                    should_process = True
                elif self.force_reprocess and event_title not in self.reprocessed_titles:
                    # Force reprocess enabled and we haven't reprocessed this title yet
                    should_process = True
                    is_first_time_reprocessing = True
                    print(f"  Force re-processing {event_title} (ignoring cache)")
                
                if should_process:
                    # Process the event
                    if event.get("type") == "concert":
                        ai_rating = self._get_classical_rating(event)
                    elif event.get("type") == "book_club":
                        ai_rating = self._get_book_club_rating(event)
                    else:
                        ai_rating = self._get_ai_rating(event)
                    self.movie_cache[event_title] = ai_rating
                else:
                    # Use cached rating
                    print(f"  Using cached rating for {event_title}")
                    ai_rating = self.movie_cache[event_title]

                # Add enriched data
                event["ai_rating"] = ai_rating

                # Add the AI-generated description to the event for summary
                # generation
                event["description"] = ai_rating.get("summary", "")

                # Generate one-line summary using Claude API (AFTER AI
                # description is available)
                one_liner_summary = None
                if self.summary_generator:
                    try:
                        # Force regenerate summary only if this is the first time reprocessing
                        one_liner_summary = self.summary_generator.generate_summary(
                            event, force_regenerate=is_first_time_reprocessing
                        )
                    except RuntimeError as e:
                        # Critical validation failure - this should stop processing
                        print(f"CRITICAL: Summary generation failed for '{event.get('title', 'Unknown')}': {e}")
                        raise
                    except Exception as e:
                        # Other errors (API failures, etc.) - log but continue
                        print(f"  Error generating summary: {e}")
                        one_liner_summary = None

                event["oneLinerSummary"] = one_liner_summary

                # Mark as reprocessed AFTER both AI rating and summary are done
                if is_first_time_reprocessing:
                    self.reprocessed_titles.add(event_title)

                enriched_events.append(event)

                # Rate limiting for API calls
                time.sleep(1)

            except Exception as e:
                print(f"Error processing event '{event.get( 'title','Unknown')}': {e}")
                # Add event with minimal data
                event["ai_rating"] = {"score": 5, "summary": "Unable to rate"}
                enriched_events.append(event)

        return enriched_events


    def _get_ai_rating(self, event: Dict) -> Dict:
        """Get movie rating and info from Perplexity API using detailed metadata"""
        if not self.perplexity_api_key:
            return {"score": 5, "summary": "No API key provided"}

        try:
            headers = {
                "Authorization": f"Bearer {self.perplexity_api_key}",
                "Content-Type": "application/json",
            }
            movie_title = event.get("title", "")
            year = event.get("year", "unknown")
            duration = event.get("duration", "unknown")
            director = event.get("director", "unknown")
            country = event.get("country", "unknown")
            language = event.get("language", "unknown")

            details = (
                f"Title: {movie_title}\n"
                f"Year: {year}\n"
                f"Director: {director}\n"
                f"Duration: {duration}\n"
                f"Country: {country}\n"
                f"Language: {language}"
            )

            prompt = f"""
You are a rigorous cultural critic evaluating with uncompromising academic standards. Assess the movie described below using a 0–10 scale where
0–4 = weak or derivative,
5–6 = competent but unremarkable,
7–8 = strong,
9–10 = exceptional masterpieces. Scores above 5 must be justified with specific evidence.

Movie Details:
{details}

Provide a concise report with these standardized sections:
★ Rating: [X/10] (integer only)
🎭 Artistic Merit – evaluate craft, execution, technical mastery and aesthetic achievement
✨ Originality – assess innovation, unpredictability, and avoidance of cliché
📚 Cultural Significance – discuss relevance, impact, and contribution to the art form
💡 Intellectual Depth – examine complexity of ideas, themes, and universal human experiences explored

Focus solely on artistic merit and complexity. Reward innovation and high entropy. Ensure you are reviewing the specific work described above.
"""

            data = {
                "model": "sonar",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 2000,
            }

            response = requests.post(
                "https://api.perplexity.ai/chat/completions",
                headers=headers,
                json=data,
                timeout=30,
            )

            if response.status_code == 200:
                result = response.json()
                content = result["choices"][0]["message"]["content"]
                return self._parse_ai_response(content)
            else:
                print(f"Perplexity API error: {response.status_code}")
                return {"score": 5, "summary": "API error"}

        except Exception as e:
            print(f"Error calling Perplexity API: {e}")
            return {"score": 5, "summary": "Unable to get rating"}

    def _get_classical_rating(self, event: Dict) -> Dict:
        """Get classical music concert rating and analysis from Perplexity API"""
        if not self.perplexity_api_key:
            return {"score": 5, "summary": "No API key provided"}

        try:
            headers = {
                "Authorization": f"Bearer {self.perplexity_api_key}",
                "Content-Type": "application/json",
            }

            # Extract key information from the event
            concert_title = event.get("title", "")
            program = event.get("program", "")
            event.get("composers", [])
            event.get("works", [])
            featured_artist = event.get("featured_artist", "")
            series = event.get("series", "")

            # Create detailed concert description for analysis
            concert_description = f"Concert: {concert_title}\nSeries: {series}\nProgram: {program}\nFeatured Artist: {featured_artist}"

            prompt = f"""
You are a rigorous cultural critic evaluating with uncompromising academic standards. Assess the concert described below using a 0–10 scale where
0–4 = weak or derivative,
5–6 = competent but unremarkable,
7–8 = strong,
9–10 = exceptional masterpieces. Scores above 5 must be justified with specific evidence.

Concert Details:
{concert_description}

Provide a concise report with these standardized sections:
★ Rating: [X/10] (integer only)
🎭 Artistic Merit – evaluate performance quality, technical execution, and interpretive depth
✨ Originality – assess programming choices, interpretive freshness, and avoidance of predictable repertoire
📚 Cultural Significance – discuss the concert's contribution to the classical music tradition
💡 Intellectual Depth – examine how effectively the music conveys complex emotions and ideas

Focus solely on artistic merit and complexity. Reward innovation and high entropy. Ensure you are reviewing the specific concert described above.
"""

            data = {
                "model": "sonar",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 2000,
            }

            response = requests.post(
                "https://api.perplexity.ai/chat/completions",
                headers=headers,
                json=data,
                timeout=30,
            )

            if response.status_code == 200:
                result = response.json()
                content = result["choices"][0]["message"]["content"]
                return self._parse_ai_response(content)
            else:
                print(f"Perplexity API error: {response.status_code}")
                return {"score": 5, "summary": "API error"}

        except Exception as e:
            print(f"Error calling Perplexity API for classical music: {e}")
            return {"score": 5, "summary": "Unable to get rating"}

    def _get_book_club_rating(self, event: Dict) -> Dict:
        """Get book club discussion rating and analysis from Perplexity API"""
        if not self.perplexity_api_key:
            return {"score": 5, "summary": "No API key provided"}

        try:
            headers = {
                "Authorization": f"Bearer {self.perplexity_api_key}",
                "Content-Type": "application/json",
            }

            # Extract key information from the event
            book_title = event.get("book", "")
            author = event.get("author", "")
            host = event.get("host", "")
            venue = event.get("venue", "")
            description = event.get("description", "")

            # Create detailed book description for analysis
            book_description = f"Book: {book_title} by {author}\nHost: {host}\nVenue: {venue}\nDescription: {description}"

            prompt = f"""
You are a rigorous cultural critic evaluating with uncompromising academic standards. Assess the book club selection described below using a 0–10 scale where
0–4 = weak or derivative,
5–6 = competent but unremarkable,
7–8 = strong,
9–10 = exceptional masterpieces. Scores above 5 must be justified with specific evidence.

Book Club Details:
{book_description}

Provide a concise report with these standardized sections:
★ Rating: [X/10] (integer only)
🎭 Artistic Merit – evaluate literary craft, prose quality, narrative structure and character development
✨ Originality – assess innovation in form or content, subversion of genre expectations
📚 Cultural Significance – discuss the work's place in literary tradition and contemporary relevance
💡 Intellectual Depth – examine complexity of themes, ideas, and human experiences explored

Focus solely on artistic merit and complexity. Reward innovation and high entropy. Ensure you are reviewing the specific book described above.
"""

            data = {
                "model": "sonar",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 2000,
            }

            response = requests.post(
                "https://api.perplexity.ai/chat/completions",
                headers=headers,
                json=data,
                timeout=30,
            )

            if response.status_code == 200:
                result = response.json()
                content = result["choices"][0]["message"]["content"]
                return self._parse_ai_response(content)
            else:
                print(f"Perplexity API error: {response.status_code}")
                return {"score": 5, "summary": "API error"}

        except Exception as e:
            print(f"Error calling Perplexity API for book club: {e}")
            return {"score": 5, "summary": "Unable to get rating"}

    def _parse_ai_response(self, content: str) -> Dict:
        """Parse AI response to extract rating and summary"""
        try:
            import re

            # Look for rating pattern like "★ Rating: 8/10" or "[8/10]" or
            # "3.6/10"
            rating_patterns = [
                r"★\s*Rating:\s*\[?(\d+(?:\.\d+)?)/10\]?",
                r"\[(\d+(?:\.\d+)?)/10\]",
                r"RATING:\s*(\d+(?:\.\d+)?)/10",
                r"(\d+(?:\.\d+)?)/10",
            ]

            score = 5  # Default score
            for pattern in rating_patterns:
                rating_match = re.search(pattern, content, re.IGNORECASE)
                if rating_match:
                    score = round(float(rating_match.group(1)))
                    break

            # Remove Perplexity citation numbers like [1]
            content = re.sub(r"\[\d+\]", "", content)
            # Use the cleaned content as summary for the French cinéaste style
            summary = content.strip()

            return {
                "score": max(0, min(10, score)),  # Clamp to 0-10
                "summary": summary,  # Keep full summary
            }

        except Exception as e:
            print(f"Error parsing AI response: {e}")
            return {"score": 5, "summary": content[:2000]}

