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
        self.preferences = self._load_preferences()
        # Separate preference list for literature events
        self.literature_preferences = self._load_literature_preferences()
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
                        "summary": event.get("description", ""),
                    }
                    event["preference_score"] = 0
                    event["final_rating"] = 7
                    event["rating_explanation"] = "Weekly recurring event"
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

                # Calculate personal preference score
                preference_score = self._calculate_preference_score(event, ai_rating)

                # Add enriched data
                event["ai_rating"] = ai_rating
                event["preference_score"] = preference_score
                event["final_rating"] = self._calculate_final_rating(
                    ai_rating, preference_score
                )
                event["rating_explanation"] = self._generate_rating_explanation(
                    event, ai_rating, preference_score
                )

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
                    except Exception as e:
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
                event["preference_score"] = 0
                event["final_rating"] = 5
                event["rating_explanation"] = "Rating unavailable"
                enriched_events.append(event)

        return enriched_events

    def _load_preferences(self) -> List[str]:
        """Load user preferences from file"""
        preferences = []
        try:
            with open("preferences.txt", "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        preferences.append(line.lower())
        except FileNotFoundError:
            print("Warning: preferences.txt not found")

        return preferences

    def _load_literature_preferences(self) -> List[str]:
        """Load literature-specific preferences from file"""
        preferences = []
        try:
            with open("literature_preferences.txt", "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        preferences.append(line.lower())
        except FileNotFoundError:
            print("Warning: literature_preferences.txt not found")

        return preferences

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
You are a ruthless movie critic grading with uncompromising academic standards. Assess the movie described below using a 0–10 scale where
0–4 = weak or derivative,
5–6 = competent but unremarkable,
7–8 = strong,
9–10 = exceptional masterpieces. Scores above 5 must be justified with specific evidence.

Movie Details:
{details}

Provide a concise report with these sections:
★ Rating: [X/10] (integer only)
🎬 Originality & Surprise – does the movie avoid clichés and deliver unpredictable storytelling?
🎥 Artistic Craft – evaluate narrative structure, character depth, cinematography, sound and pacing.
🎭 Thematic Depth – discuss universal human experiences explored with nuance.
🏛️ Comparative Excellence – compare against landmark works in its genre, referencing broad critical consensus if relevant.

Focus solely on artistic merit and complexity. Reward innovation and high entropy; ignore ideological framing. Ensure you are reviewing the specific movie described above and not a different work with a similar title.
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
You are a demanding classical music critic. Evaluate the concert below using a 0–10 scale where
0–4 = weak or derivative,
5–6 = adequate,
7–8 = strong,
9–10 = exceptional. Justify any score above 5 with concrete evidence.

Concert Details:
{concert_description}

Provide:
★ Rating: [X/10] (integer only)
🎼 Program & Interpretation – assess selection of works and interpretive originality; does it avoid predictable programming?
🎻 Performance Quality – evaluate technical execution, ensemble cohesion and expressive depth.
🎨 Thematic Depth – how effectively does the music convey universal emotions and ideas?
🏛️ Comparative Excellence – compare with landmark performances in the repertoire and note critical consensus when relevant.

Focus solely on musical artistry and surprise. Reward innovation and high entropy, not ideological framing.
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
You are a rigorous literary critic. Evaluate the following book club selection using a 0–10 scale where
0–4 = weak or derivative,
5–6 = competent,
7–8 = strong,
9–10 = exceptional. Scores above 5 must be justified with specific evidence.

Book Club Details:
{book_description}

Provide:
★ Rating: [X/10] (integer only)
📚 Literary Craft – assess narrative structure, prose quality and character complexity.
✨ Originality & Entropy – does the work subvert cliché and introduce surprising ideas?
🎭 Thematic Depth – which universal human experiences are explored with nuance?
🗣️ Discussion Value – how richly does the book support thoughtful conversation?
🏛️ Comparative Excellence – compare to seminal works in its genre, noting broad critical reception where relevant.

Focus on artistic merit and intellectual rigor. Reward complexity and innovation, not ideological framing.
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

    def _calculate_preference_score(self, event: Dict, ai_rating: Dict) -> int:
        """Calculate preference score based on user preferences"""
        score = 0

        # Check title, description, and AI summary for preferences
        text_to_check = (
            event.get("title", "")
            + " "
            + event.get("description", "")
            + " "
            + ai_rating.get("summary", "")
        ).lower()

        # Combine general preferences with literature-specific ones for book
        # clubs
        preferences_to_use = list(self.preferences)
        if event.get("type") == "book_club":
            preferences_to_use += self.literature_preferences

        # Add points for matching preferences
        for preference in preferences_to_use:
            if preference in text_to_check:
                score += 2

        # Bonus for special screenings
        if event.get("is_special_screening"):
            score += 3

        return score

    def _calculate_final_rating(self, ai_rating: Dict, preference_score: int) -> int:
        """Calculate final rating combining AI and preference scores"""
        base_rating = ai_rating.get("score", 5)

        # Apply preference boost (max +3 points)
        boost = min(3, preference_score // 2)

        final_rating = min(10, base_rating + boost)

        return final_rating

    def _generate_rating_explanation(
        self, event: Dict, ai_rating: Dict, preference_score: int
    ) -> str:
        """Generate explanation for the rating"""
        explanation_parts = []

        # AI rating part
        ai_score = ai_rating.get("score", 5)
        explanation_parts.append(f"AI Rating: {ai_score}/10")

        # Preference boost
        if preference_score > 0:
            boost = min(3, preference_score // 2)
            explanation_parts.append(f"Personal preference boost: +{boost}")

        # Special screening bonus
        if event.get("is_special_screening"):
            explanation_parts.append("✨ Special screening")

        # AI summary
        summary = ai_rating.get("summary", "").strip()
        if summary:
            explanation_parts.append(f"Summary: {summary}")

        return " | ".join(explanation_parts)
