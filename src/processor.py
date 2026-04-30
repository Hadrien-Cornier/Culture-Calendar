"""Event processor — AI ratings, critic-style reviews, refusal handling.

:class:`EventProcessor` takes normalized events (output of
:class:`src.scraper.MultiVenueScraper`) and attaches two AI-generated
fields:

- ``rating`` — integer 0–10 (or ``-1`` when ungraded) reflecting
  artistic merit, driven by per-category rubrics.
- ``description`` — long-form critic-style review text. French
  cinéaste tone for movies, distinguished-criticism tone for
  music/dance, accessible literary framing for book clubs.

**Rating prompt cascade** (:meth:`_get_ai_rating` and its
``_get_<category>_rating`` helpers):

1. Strict rubric prompt via Perplexity (uncompromising academic
   standards).
2. Permissive retry ("DO NOT refuse"; use training data if web sources
   are sparse).
3. General-knowledge retry (pure training-data path).
4. Claude fallback for events Perplexity declines.
5. Default sentinel ``{"score": 5, "summary": "Unable to evaluate..."}``
   which is then filtered out by :mod:`src.refusal` when it matches
   refusal-shaped text.

**Review confidence** — :meth:`_parse_ai_response` tags the returned
dict with ``review_confidence: low | medium | high`` based on refusal
detection + explicit-insufficient phrases (``"insufficient evidence"``
etc.). The frontend's "Pending more research" section renders events
whose confidence is ``low``, so uncertain ratings don't visually
compete with genuine low scores backed by evidence.

**Cache** — ``docs/data.json`` doubles as the rating cache via
:meth:`_load_existing_data`; refusal-shaped summaries are re-rated
automatically (commit ``65bf010``), legitimate low scores are served
from cache. ``cache/llm_cache.json`` (gitignored) mirrors raw LLM
responses for offline testing.

This module is high-impact: every d=1 caller of
:meth:`_parse_ai_response` or :meth:`_get_ai_rating` is downstream of
an event's public rating, so run ``gitnexus_impact`` on any changes.
"""

import os
import re
import time
import json
from datetime import datetime
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed

import requests
from dotenv import load_dotenv

from .summary_generator import SummaryGenerator
from .sources import wikipedia, letterboxd
from .refusal import (
    REFUSAL_PATTERNS,
    REFUSAL_STUB,
    _REFUSAL_RE,
    filter_refusal,
    is_refusal_response,
)

# Phrases an LLM tends to emit when it delivered a review but wants to flag
# that the underlying evidence was thin. These do not trigger the refusal
# substitution (the review is still usable), but they should surface as a
# `low` review_confidence so the UI can route the event to the "pending more
# research" bucket.
INSUFFICIENT_EVIDENCE_PHRASES: tuple[str, ...] = (
    "insufficient evidence",
    "insufficient information",
    "could not verify",
    "limited information",
    "cannot confirm",
    "unable to find reliable",
)


def compute_confidence(text: str) -> str:
    """Return ``"low"`` or ``"high"`` confidence for an LLM review.

    Low iff the text matches the refusal regex OR contains any explicit
    insufficient-evidence phrase (case-insensitive). Never keys off raw
    length — a terse but substantive review ("A masterpiece...") must
    score high, and a long evasive answer must score low.
    """
    if not text:
        return "low"
    if is_refusal_response(text):
        return "low"
    lowered = text.lower()
    for phrase in INSUFFICIENT_EVIDENCE_PHRASES:
        if phrase in lowered:
            return "low"
    return "high"

load_dotenv()

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


def _style_rubric() -> str:
    """Return the style rubric and banned-phrase list injected into every LLM review prompt.

    Phrased as preferences rather than forbidden rules to avoid LLM refusal mode
    on sparse-source events (Opera/Paramount); still pushes output away from AI-smell.
    """
    banned = ", ".join(BANNED_PHRASES)
    return (
        "STYLE REQUIREMENTS:\n"
        "- Write like a newspaper critic on deadline: direct, concrete, specific.\n"
        "- Use only commas, periods, or semicolons—do not use em-dashes (\u2014).\n"
        "- If sources are thin, write a brief honest note (2-3 sentences) "
        "about what you can and cannot say. Do not refuse; produce the review.\n"
        f"- CRITICAL: Do not use these overused words/phrases: {banned}. Find specific alternatives.\n"
        "- Commit to a judgment; reserve hedging for genuine uncertainty.\n"
        "- Cite specific scenes, passages, movements, or performances when possible.\n"
        "- Replace clichés with concrete details (instead of 'haunting', name what haunts; "
        "instead of 'profound', describe the specific insight)."
    )


def _fact_dossier(event: Dict) -> str:
    """Fetch factual dossier from Wikipedia and Letterboxd (for movies) or Wikipedia (for concerts/opera).

    Uses ThreadPoolExecutor to fetch in parallel with 5s timeout each.
    Returns markdown block or empty string if all sources returned None.
    """
    event_type = event.get("event_category") or event.get("type", "").lower()
    dossier_parts = []

    if event_type in ("movie", "screening"):
        title = event.get("title", "")
        director = event.get("director", "")
        year = event.get("release_year") or event.get("year")

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {}
            if director:
                futures["wikipedia_director"] = executor.submit(wikipedia.fetch_wikipedia, director)
            if title and year:
                futures["letterboxd"] = executor.submit(letterboxd.fetch_letterboxd_film, title, int(year))

            for name, future in futures.items():
                try:
                    result = future.result(timeout=5)
                    if result:
                        if name == "wikipedia_director":
                            if result.get("extract"):
                                dossier_parts.append(f"**Director:** {result['extract'][:300]}…")
                        elif name == "letterboxd":
                            if result.get("rating"):
                                dossier_parts.append(f"**Letterboxd Rating:** {result['rating']}/5")
                            if result.get("review_excerpt"):
                                dossier_parts.append(f"**Popular Review:** {result['review_excerpt'][:200]}…")
                except TimeoutError:
                    pass
                except Exception:
                    pass

    elif event_type in ("concert", "opera"):
        composers = event.get("composers", [])
        featured_artist = event.get("featured_artist", "")

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {}
            for composer in (composers[:2] if isinstance(composers, list) else []):
                futures[f"composer_{composer}"] = executor.submit(wikipedia.fetch_wikipedia, composer)
            if featured_artist:
                futures["featured_artist"] = executor.submit(wikipedia.fetch_wikipedia, featured_artist)

            for name, future in futures.items():
                try:
                    result = future.result(timeout=5)
                    if result and result.get("extract"):
                        dossier_parts.append(f"**{name.replace('_', ' ').title()}:** {result['extract'][:300]}…")
                except TimeoutError:
                    pass
                except Exception:
                    pass

    if dossier_parts:
        return "## Factual Dossier\n" + "\n".join(dossier_parts)
    return ""


class EventProcessor:
    def __init__(self, force_reprocess: bool = False, pilot_mode: bool = False):
        self.perplexity_api_key = os.getenv("PERPLEXITY_API_KEY")
        self.movie_cache = {}  # Cache AI ratings to avoid reprocessing
        self.force_reprocess = force_reprocess
        self.pilot_mode = pilot_mode or os.getenv("PILOT_UPLIFT", "").lower() in ("1", "true")
        self.reprocessed_titles = set()  # Track titles already reprocessed in this run

        # Load existing data into cache
        self._load_existing_data()

        # Initialize summary generator
        try:
            self.summary_generator = SummaryGenerator()
        except ValueError as e:
            print(f"Warning: Could not initialize summary generator: {e}")
            self.summary_generator = None

    def _load_existing_data(self):
        """Load existing event data from docs/data.json into movie cache"""
        try:
            # Get the project root directory (assuming this file is in src/)
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(current_dir)
            data_file_path = os.path.join(project_root, "docs", "data.json")

            if not os.path.exists(data_file_path):
                print(f"Warning: data.json not found at {data_file_path}")
                return

            with open(data_file_path, "r", encoding="utf-8") as f:
                events_data = json.load(f)

            # Load data into cache
            loaded_count = 0
            for event in events_data:
                title = event.get("title", "").upper().strip()
                rating = event.get("rating")
                description = event.get("description", "")

                if title and rating is not None:
                    self.movie_cache[title] = {"score": rating, "summary": description}
                    loaded_count += 1

            print(f"Loaded {loaded_count} cached event ratings from data.json")

        except Exception as e:
            print(f"Warning: Could not load existing data from data.json: {e}")

    def process_events(self, events: List[Dict]) -> List[Dict]:
        """Process and enrich all events"""
        enriched_events = []
        len(events)
        processed_count = 0

        MOVIE_VENUES = {
            "afs", "hyperreal", "paramount",
            "austin film society", "austin movie society",
            "hyperreal movie club", "hyperreal film club",
        }
        for i, event in enumerate(events, 1):
            try:
                etype = event.get("type")
                if not etype:
                    venue = (event.get("venue") or "").strip().lower()
                    if venue in MOVIE_VENUES:
                        etype = "movie"
                        event["type"] = "movie"
                if etype not in ("screening", "movie", "concert", "book_club", "opera", "dance", "visual_arts", "other"):
                    if etype:
                        print(f"  Skipping unsupported type={etype} for '{event.get('title','?')}'")
                    else:
                        print(f"  Skipping untyped event '{event.get('title','?')}' (venue={event.get('venue','?')})")
                    continue

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

                # Skip LLM enrichment for type=other events that already carry
                # a scraper-authored factual description (e.g. Paper Cuts pop-up
                # bookshop). We must not overwrite those pre-filled blurbs.
                if etype == "other" and (event.get("description") or "").strip():
                    print(f"  Skipping LLM enrichment for type=other with pre-filled description")
                    event["ai_rating"] = {
                        "score": None,
                        "summary": event["description"],
                    }
                    if not event.get("oneLinerSummary"):
                        event["oneLinerSummary"] = event.get("one_liner_summary") or ""
                    enriched_events.append(event)
                    continue

                # Get AI rating (with caching)
                event_title = event["title"].upper().strip()

                # Check if we need to process this title
                should_process = False
                is_first_time_reprocessing = False
                made_ai_api_call = False

                if event_title not in self.movie_cache:
                    should_process = True
                elif (
                    self.force_reprocess and event_title not in self.reprocessed_titles
                ):
                    should_process = True
                    is_first_time_reprocessing = True
                    print(f"  Force re-processing {event_title} (ignoring cache)")
                elif is_refusal_response(self.movie_cache[event_title].get("summary", "")):
                    # Stale refusal in cache — treat as miss so the new retry chain
                    # can rescue it without forcing a full --force-reprocess.
                    should_process = True
                    print(f"  Cached entry for {event_title} is a refusal; re-rating.")

                if should_process:
                    # Process the event
                    made_ai_api_call = True
                    if event.get("type") == "concert":
                        ai_rating = self._get_classical_rating(event)
                    elif event.get("type") == "book_club":
                        ai_rating = self._get_book_club_rating(event)
                    elif event.get("type") == "visual_arts":
                        ai_rating = self._get_visual_arts_rating(event)
                    elif event.get("type") == "dance":
                        ai_rating = self._get_dance_rating(event)
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
                made_summary_api_call = False

                if self.summary_generator:
                    try:
                        # Force regenerate summary only if this is the first time reprocessing
                        one_liner_summary, summary_was_generated = (
                            self.summary_generator.generate_summary_with_cache_info(
                                event, force_regenerate=is_first_time_reprocessing
                            )
                        )
                        made_summary_api_call = summary_was_generated
                    except RuntimeError as e:
                        # Critical validation failure - this should stop processing
                        print(
                            f"CRITICAL: Summary generation failed for '{event.get('title', 'Unknown')}': {e}"
                        )
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

                # Rate limiting ONLY when API calls were made
                if made_ai_api_call or made_summary_api_call:
                    time.sleep(1)
                    print(
                        f"  Applied rate limiting (AI API: {made_ai_api_call}, Summary API: {made_summary_api_call})"
                    )
                else:
                    print(f"  Using cached data for {event_title}")

            except Exception as e:
                print(f"Error processing event '{event.get( 'title','Unknown')}': {e}")
                # Add event with minimal data
                event["ai_rating"] = {"score": 5, "summary": "Unable to rate"}
                enriched_events.append(event)

        return enriched_events

    def _get_ai_rating(self, event: Dict) -> Dict:
        """Get movie rating and info from Perplexity, retrying on refusal."""
        if not self.perplexity_api_key:
            return {"score": 5, "summary": "No API key provided"}

        movie_title = event.get("title", "")
        details = (
            f"Title: {movie_title}\n"
            f"Year: {event.get('release_year') or event.get('year', 'unknown')}\n"
            f"Director: {event.get('director', 'unknown')}\n"
            f"Duration: {event.get('runtime_minutes') or event.get('duration', 'unknown')}\n"
            f"Country: {event.get('country', 'unknown')}\n"
            f"Language: {event.get('language', 'unknown')}"
        )

        fact_dossier = _fact_dossier(event) if self.pilot_mode else ""

        attempts = [
            ("strict", self._build_movie_prompt_strict(details, fact_dossier)),
            ("permissive", self._build_movie_prompt_permissive(details, fact_dossier)),
            ("knowledge", self._build_movie_prompt_general_knowledge(details, fact_dossier)),
        ]
        for attempt_name, prompt in attempts:
            content = self._call_perplexity(prompt)
            if not content:
                continue
            if is_refusal_response(content):
                print(f"  Perplexity refused on '{movie_title}' (attempt={attempt_name}); retrying with broader prompt…")
                continue
            return self._parse_ai_response(content)

        # All Perplexity prompts refused — fall back to Claude direct.
        claude_review = self._claude_fallback_review(event)
        if claude_review:
            return claude_review
        return {"score": 5, "summary": f"Unable to evaluate {movie_title} (LLM unable to find sources)."}

    def _build_movie_prompt_strict(self, details: str, fact_dossier: str = "") -> str:
        rubric = _style_rubric()
        dossier_section = f"\n{fact_dossier}\n" if fact_dossier else ""
        return f"""
{rubric}

You are a rigorous cultural critic evaluating with uncompromising academic standards. Assess the movie described below using a 0–10 scale where
0–4 = weak or derivative,
5–6 = competent but unremarkable,
7–8 = strong,
9–10 = exceptional masterpieces. Scores above 5 must be justified with specific evidence.

Movie Details:
{details}{dossier_section}

Provide a concise report with these standardized sections:
★ Rating: [X/10] (integer only)
🎭 Artistic Merit – evaluate craft, execution, technical mastery and aesthetic achievement
✨ Originality – assess innovation, unpredictability, and avoidance of cliché
📚 Cultural Significance – discuss relevance, impact, and contribution to the art form
💡 Intellectual Depth – examine complexity of ideas, themes, and universal human experiences explored

Focus solely on artistic merit and complexity. Reward innovation and high entropy. Ensure you are reviewing the specific work described above.
"""

    def _build_movie_prompt_permissive(self, details: str, fact_dossier: str = "") -> str:
        rubric = _style_rubric()
        dossier_section = f"\n{fact_dossier}\n" if fact_dossier else ""
        return f"""
{rubric}

Write a brief critical review of this film. If your search results don't surface specific reviews, draw on general film history, the director's body of work, the country's cinema tradition, and contextual knowledge — DO NOT refuse to review.

Movie Details:
{details}{dossier_section}

Format:
★ Rating: [X/10] (integer)
🎭 Artistic Merit
✨ Originality
📚 Cultural Significance
💡 Intellectual Depth

Aim for 4–6 short paragraphs total. A grounded, contextual review is far more useful than a refusal.
"""

    def _build_movie_prompt_general_knowledge(self, details: str, fact_dossier: str = "") -> str:
        rubric = _style_rubric()
        dossier_section = f"\n{fact_dossier}\n" if fact_dossier else ""
        return f"""
{rubric}

You are a knowledgeable cinephile writing for an Austin film-society audience. Use your training-time knowledge — not just search — to write a real review.

Movie Details:
{details}{dossier_section}

Cover director's style, the film's place in cinema history, what makes it interesting (or not). Provide a 0–10 rating. If the film is genuinely obscure to you, still take a defensible position based on the metadata above (director's other work, country/era cinema norms) and explicitly note the uncertainty in one sentence — but do not refuse.

Format your reply with:
★ Rating: [X/10]
🎭 Artistic Merit
✨ Originality
📚 Cultural Significance
💡 Intellectual Depth
"""

    def _call_perplexity(self, prompt: str) -> Optional[str]:
        try:
            headers = {
                "Authorization": f"Bearer {self.perplexity_api_key}",
                "Content-Type": "application/json",
            }
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
                return response.json()["choices"][0]["message"]["content"]
            print(f"  Perplexity API error: {response.status_code}")
            return None
        except Exception as e:
            print(f"  Error calling Perplexity API: {e}")
            return None

    def _claude_fallback_review(self, event: Dict) -> Optional[Dict]:
        """Last-resort: ask Claude directly to write the review.

        Only used when every Perplexity prompt variant returned a refusal. Claude
        Sonnet has wider general-knowledge coverage on art-house cinema, so a
        Director + Title prompt usually produces a defensible review even when
        Perplexity's search couldn't surface evidence.
        """
        if not os.getenv("ANTHROPIC_API_KEY"):
            return None
        try:
            import anthropic
            client = anthropic.Anthropic()
            prompt = f"""
Write a 4–6 paragraph critical review of {event.get('title','this film')!r} (dir. {event.get('director','unknown')}, {event.get('release_year') or event.get('year','?')}, {event.get('country','?')}). Use your trained-knowledge of cinema, the director's filmography, and the era's stylistic norms. Provide a 0–10 rating.

Format:
★ Rating: [X/10]
🎭 Artistic Merit
✨ Originality
📚 Cultural Significance
💡 Intellectual Depth

Be specific. If you genuinely don't know this film, position it based on the director's other work and explicitly say so in one sentence — but write the review.
"""
            resp = client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=1500,
                temperature=0.4,
                messages=[{"role": "user", "content": prompt}],
            )
            content = resp.content[0].text
            if is_refusal_response(content):
                return None
            print(f"  Claude fallback succeeded for {event.get('title')!r}")
            return self._parse_ai_response(content)
        except Exception as e:
            print(f"  Claude fallback failed: {e}")
            return None

    def _get_classical_rating(self, event: Dict) -> Dict:
        """Get classical concert rating, retrying on refusal."""
        if not self.perplexity_api_key:
            return {"score": 5, "summary": "No API key provided"}

        title = event.get("title", "")
        composers = ", ".join(event.get("composers", [])) or "unknown"
        works = ", ".join(event.get("works", [])) or "unknown"
        details = (
            f"Concert: {title}\n"
            f"Series: {event.get('series', 'unknown')}\n"
            f"Program: {event.get('program', 'unknown')}\n"
            f"Featured Artist: {event.get('featured_artist', 'unknown')}\n"
            f"Composers: {composers}\n"
            f"Works: {works}"
        )

        fact_dossier = _fact_dossier(event) if self.pilot_mode else ""

        attempts = [
            ("strict", self._build_concert_prompt_strict(details, fact_dossier)),
            ("permissive", self._build_concert_prompt_permissive(details, fact_dossier)),
            ("knowledge", self._build_concert_prompt_general_knowledge(details, fact_dossier)),
        ]
        for attempt_name, prompt in attempts:
            content = self._call_perplexity(prompt)
            if not content:
                continue
            if is_refusal_response(content):
                print(f"  Perplexity refused on '{title}' (concert, attempt={attempt_name}); retrying…")
                continue
            return self._parse_ai_response(content)

        claude_review = self._claude_fallback_concert(event, details)
        if claude_review:
            return claude_review
        return {"score": 5, "summary": f"Unable to evaluate concert {title} (LLM unable to find sources)."}

    def _build_concert_prompt_strict(self, details: str, fact_dossier: str = "") -> str:
        rubric = _style_rubric()
        dossier_section = f"\n{fact_dossier}\n" if fact_dossier else ""
        return f"""
{rubric}

You are a rigorous cultural critic evaluating with uncompromising academic standards. Assess the concert described below using a 0–10 scale where
0–4 = weak or derivative,
5–6 = competent but unremarkable,
7–8 = strong,
9–10 = exceptional masterpieces. Scores above 5 must be justified with specific evidence.

Concert Details:
{details}{dossier_section}

Provide a concise report with these standardized sections:
★ Rating: [X/10] (integer only)
🎭 Artistic Merit – performance quality, technical execution, interpretive depth
✨ Originality – programming choices, interpretive freshness
📚 Cultural Significance – contribution to classical music tradition
💡 Intellectual Depth – complexity of ideas conveyed

Ensure you are reviewing the specific concert described above.
"""

    def _build_concert_prompt_permissive(self, details: str, fact_dossier: str = "") -> str:
        rubric = _style_rubric()
        dossier_section = f"\n{fact_dossier}\n" if fact_dossier else ""
        return f"""
{rubric}

Write a brief critical review of this classical concert. If your search doesn't surface specific reviews, draw on general knowledge of the composers, ensemble's reputation, and repertoire — DO NOT refuse. A grounded contextual review is more useful than a refusal.

Concert Details:
{details}{dossier_section}

Format:
★ Rating: [X/10]
🎭 Artistic Merit
✨ Originality
📚 Cultural Significance
💡 Intellectual Depth
"""

    def _build_concert_prompt_general_knowledge(self, details: str, fact_dossier: str = "") -> str:
        rubric = _style_rubric()
        dossier_section = f"\n{fact_dossier}\n" if fact_dossier else ""
        return f"""
{rubric}

You are an expert classical music critic writing for a discerning Austin audience. Use your training-time knowledge of the composers, the works listed, and the ensemble or featured artist to write a real review — even if your search doesn't surface specific reviews of this exact concert.

Concert Details:
{details}{dossier_section}

Cover the historical importance of the composers/works, what makes the program interesting (or routine), and what you'd expect from this kind of ensemble. Provide a 0–10 rating. If you genuinely don't know one element, take a defensible position from what you do know.

Format:
★ Rating: [X/10]
🎭 Artistic Merit
✨ Originality
📚 Cultural Significance
💡 Intellectual Depth
"""

    def _claude_fallback_concert(self, event: Dict, details: str) -> Optional[Dict]:
        if not os.getenv("ANTHROPIC_API_KEY"):
            return None
        try:
            import anthropic
            client = anthropic.Anthropic()
            prompt = f"""
Write a 4–6 paragraph critical review of this classical concert using your trained-knowledge of the composers, repertoire, and ensemble. Provide a 0–10 rating.

{details}

Format:
★ Rating: [X/10]
🎭 Artistic Merit
✨ Originality
📚 Cultural Significance
💡 Intellectual Depth

Be specific. Take a defensible position even if some details are missing.
"""
            resp = client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=1500,
                temperature=0.4,
                messages=[{"role": "user", "content": prompt}],
            )
            content = resp.content[0].text
            if is_refusal_response(content):
                return None
            print(f"  Claude fallback succeeded for concert '{event.get('title')}'")
            return self._parse_ai_response(content)
        except Exception as e:
            print(f"  Claude fallback (concert) failed: {e}")
            return None

    def _get_visual_arts_rating(self, event: Dict) -> Dict:
        """Get visual-arts exhibition rating, retrying on refusal.

        Modeled on _get_classical_rating. Uses an art-critic prompt tone that
        emphasizes formal qualities, cultural significance, and historical
        context rather than cinematic or musical criteria.
        """
        if not self.perplexity_api_key:
            return {"score": 5, "summary": "No API key provided"}

        title = event.get("title", "")
        artists_raw = event.get("artists") or []
        if isinstance(artists_raw, list):
            artists = ", ".join(a for a in artists_raw if a)
        else:
            artists = str(artists_raw)
        artist = event.get("artist", "") or artists or "unknown"
        details = (
            f"Exhibition: {title}\n"
            f"Artist(s): {artist}\n"
            f"Medium: {event.get('medium', 'unknown')}\n"
            f"Series: {event.get('series', 'unknown')}\n"
            f"Venue: {event.get('venue', 'unknown')}"
        )

        fact_dossier = _fact_dossier(event) if self.pilot_mode else ""

        attempts = [
            ("strict", self._build_visual_arts_prompt_strict(details, fact_dossier)),
            ("permissive", self._build_visual_arts_prompt_permissive(details, fact_dossier)),
            ("knowledge", self._build_visual_arts_prompt_general_knowledge(details, fact_dossier)),
        ]
        for attempt_name, prompt in attempts:
            content = self._call_perplexity(prompt)
            if not content:
                continue
            if is_refusal_response(content):
                print(f"  Perplexity refused on '{title}' (visual_arts, attempt={attempt_name}); retrying…")
                continue
            return self._parse_ai_response(content)

        claude_review = self._claude_fallback_visual_arts(event, details)
        if claude_review:
            return claude_review
        return {"score": 5, "summary": f"Unable to evaluate exhibition {title} (LLM unable to find sources)."}

    def _build_visual_arts_prompt_strict(self, details: str, fact_dossier: str = "") -> str:
        rubric = _style_rubric()
        dossier_section = f"\n{fact_dossier}\n" if fact_dossier else ""
        return f"""
{rubric}

You are a rigorous art critic evaluating with uncompromising curatorial standards. Assess the exhibition described below using a 0–10 scale where
0–4 = weak or derivative,
5–6 = competent but unremarkable,
7–8 = strong,
9–10 = exceptional. Scores above 5 must be justified with specific evidence.

Exhibition Details:
{details}{dossier_section}

Provide a concise report with these standardized sections:
★ Rating: [X/10] (integer only)
🎭 Formal Qualities – composition, materials, technique, spatial and visual craft
✨ Originality – conceptual innovation, departure from prevailing conventions
📚 Cultural Significance – relevance to contemporary discourse, relationship to institutional and critical context
💡 Historical Context – place within the artist's trajectory and broader art-historical lineage

Ensure you are reviewing the specific exhibition described above.
"""

    def _build_visual_arts_prompt_permissive(self, details: str, fact_dossier: str = "") -> str:
        rubric = _style_rubric()
        dossier_section = f"\n{fact_dossier}\n" if fact_dossier else ""
        return f"""
{rubric}

Write a brief critical review of this visual-arts exhibition. If your search doesn't surface specific reviews, draw on general knowledge of the artist's body of work, the venue's curatorial program, and the medium's conventions — DO NOT refuse. A grounded contextual review is more useful than a refusal.

Exhibition Details:
{details}{dossier_section}

Format:
★ Rating: [X/10]
🎭 Formal Qualities
✨ Originality
📚 Cultural Significance
💡 Historical Context
"""

    def _build_visual_arts_prompt_general_knowledge(self, details: str, fact_dossier: str = "") -> str:
        rubric = _style_rubric()
        dossier_section = f"\n{fact_dossier}\n" if fact_dossier else ""
        return f"""
{rubric}

You are an expert art critic writing for a discerning Austin gallery-going audience. Use your training-time knowledge of the artist, the medium, and the venue to write a real review — even if your search doesn't surface specific reviews of this exact exhibition.

Exhibition Details:
{details}{dossier_section}

Cover the artist's reputation and trajectory, the formal strategies at work, and the exhibition's place in the current art-historical moment. Provide a 0–10 rating. If you genuinely don't know one element, take a defensible position from what you do know and say so in one sentence — but do not refuse.

Format:
★ Rating: [X/10]
🎭 Formal Qualities
✨ Originality
📚 Cultural Significance
💡 Historical Context
"""

    def _claude_fallback_visual_arts(self, event: Dict, details: str) -> Optional[Dict]:
        if not os.getenv("ANTHROPIC_API_KEY"):
            return None
        try:
            import anthropic
            client = anthropic.Anthropic()
            prompt = f"""
Write a 4–6 paragraph critical review of this visual-arts exhibition using your trained-knowledge of the artist, the medium, and the venue's curatorial program. Provide a 0–10 rating.

{details}

Format:
★ Rating: [X/10]
🎭 Formal Qualities
✨ Originality
📚 Cultural Significance
💡 Historical Context

Be specific. Take a defensible position even if some details are missing.
"""
            resp = client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=1500,
                temperature=0.4,
                messages=[{"role": "user", "content": prompt}],
            )
            content = resp.content[0].text
            if is_refusal_response(content):
                return None
            print(f"  Claude fallback succeeded for exhibition '{event.get('title')}'")
            return self._parse_ai_response(content)
        except Exception as e:
            print(f"  Claude fallback (visual_arts) failed: {e}")
            return None

    def _get_dance_rating(self, event: Dict) -> Dict:
        """Get dance/ballet performance rating, retrying on refusal.

        Modeled on _get_classical_rating. Uses a dance-critic prompt that
        emphasizes choreography, the company/ensemble's repertoire, and the
        performance tradition rather than cinematic, musical, or art-historical
        criteria.
        """
        if not self.perplexity_api_key:
            return {"score": 5, "summary": "No API key provided"}

        title = event.get("title", "")
        program = event.get("program", "") or "unknown"
        series = event.get("series", "") or "unknown"
        company = event.get("company") or event.get("venue") or "unknown"
        choreographer = event.get("choreographer", "") or "unknown"
        details = (
            f"Performance: {title}\n"
            f"Company: {company}\n"
            f"Choreographer: {choreographer}\n"
            f"Series: {series}\n"
            f"Program / Repertoire: {program}"
        )

        fact_dossier = _fact_dossier(event) if self.pilot_mode else ""

        attempts = [
            ("strict", self._build_dance_prompt_strict(details, fact_dossier)),
            ("permissive", self._build_dance_prompt_permissive(details, fact_dossier)),
            ("knowledge", self._build_dance_prompt_general_knowledge(details, fact_dossier)),
        ]
        for attempt_name, prompt in attempts:
            content = self._call_perplexity(prompt)
            if not content:
                continue
            if is_refusal_response(content):
                print(f"  Perplexity refused on '{title}' (dance, attempt={attempt_name}); retrying…")
                continue
            return self._parse_ai_response(content)

        claude_review = self._claude_fallback_dance(event, details)
        if claude_review:
            return claude_review
        return {"score": 5, "summary": f"Unable to evaluate dance performance {title} (LLM unable to find sources)."}

    def _build_dance_prompt_strict(self, details: str, fact_dossier: str = "") -> str:
        rubric = _style_rubric()
        dossier_section = f"\n{fact_dossier}\n" if fact_dossier else ""
        return f"""
{rubric}

You are a rigorous dance critic evaluating with uncompromising standards. Assess the dance performance described below using a 0–10 scale where
0–4 = weak or derivative,
5–6 = competent but unremarkable,
7–8 = strong,
9–10 = exceptional. Scores above 5 must be justified with specific evidence.

Performance Details:
{details}{dossier_section}

Provide a concise report with these standardized sections:
★ Rating: [X/10] (integer only)
🎭 Choreographic Craft – movement vocabulary, structure, partnering, use of stage and ensemble
✨ Performance Quality – technique, musicality, dramatic commitment of the company and dancers
📚 Cultural Significance – place of the work and the company within the contemporary dance landscape
💡 Historical Context – relationship to the choreographer's body of work and the broader repertoire

Ensure you are reviewing the specific performance described above. Name the choreographer, company, and works when possible.
"""

    def _build_dance_prompt_permissive(self, details: str, fact_dossier: str = "") -> str:
        rubric = _style_rubric()
        dossier_section = f"\n{fact_dossier}\n" if fact_dossier else ""
        return f"""
{rubric}

Write a brief critical review of this dance performance. If your search doesn't surface specific reviews, draw on general knowledge of the choreographer, the company's repertoire, and the works on the program — DO NOT refuse. A grounded contextual review is more useful than a refusal.

Performance Details:
{details}{dossier_section}

Format:
★ Rating: [X/10]
🎭 Choreographic Craft
✨ Performance Quality
📚 Cultural Significance
💡 Historical Context
"""

    def _build_dance_prompt_general_knowledge(self, details: str, fact_dossier: str = "") -> str:
        rubric = _style_rubric()
        dossier_section = f"\n{fact_dossier}\n" if fact_dossier else ""
        return f"""
{rubric}

You are an expert dance critic writing for a discerning Austin audience. Use your training-time knowledge of the choreographer, the company, and the works on the program to write a real review — even if your search doesn't surface specific reviews of this exact performance.

Performance Details:
{details}{dossier_section}

Cover the company's reputation and repertoire, the choreographer's idiom, and what the program promises. Provide a 0–10 rating. If you genuinely don't know one element, take a defensible position from what you do know and say so in one sentence — but do not refuse.

Format:
★ Rating: [X/10]
🎭 Choreographic Craft
✨ Performance Quality
📚 Cultural Significance
💡 Historical Context
"""

    def _claude_fallback_dance(self, event: Dict, details: str) -> Optional[Dict]:
        if not os.getenv("ANTHROPIC_API_KEY"):
            return None
        try:
            import anthropic
            client = anthropic.Anthropic()
            prompt = f"""
Write a 4–6 paragraph critical review of this dance performance using your trained-knowledge of the choreographer, the company, and the works on the program. Provide a 0–10 rating.

{details}

Format:
★ Rating: [X/10]
🎭 Choreographic Craft
✨ Performance Quality
📚 Cultural Significance
💡 Historical Context

Be specific. Take a defensible position even if some details are missing.
"""
            resp = client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=1500,
                temperature=0.4,
                messages=[{"role": "user", "content": prompt}],
            )
            content = resp.content[0].text
            if is_refusal_response(content):
                return None
            print(f"  Claude fallback succeeded for dance '{event.get('title')}'")
            return self._parse_ai_response(content)
        except Exception as e:
            print(f"  Claude fallback (dance) failed: {e}")
            return None

    def _get_book_club_rating(self, event: Dict) -> Dict:
        """Get book club rating, retrying on refusal."""
        if not self.perplexity_api_key:
            return {"score": 5, "summary": "No API key provided"}

        title = event.get("book", "") or event.get("title", "")
        details = (
            f"Book: {event.get('book', '')} by {event.get('author', 'unknown author')}\n"
            f"Host: {event.get('host', '')}\n"
            f"Venue: {event.get('venue', '')}"
        )
        attempts = [
            ("strict", self._build_book_prompt_strict(details)),
            ("permissive", self._build_book_prompt_permissive(details)),
            ("knowledge", self._build_book_prompt_general_knowledge(details)),
        ]
        for attempt_name, prompt in attempts:
            content = self._call_perplexity(prompt)
            if not content:
                continue
            if is_refusal_response(content):
                print(f"  Perplexity refused on book '{title}' (attempt={attempt_name}); retrying…")
                continue
            return self._parse_ai_response(content)

        claude_review = self._claude_fallback_book(event, details)
        if claude_review:
            return claude_review
        return {"score": 5, "summary": f"Unable to evaluate {title} (LLM unable to find sources)."}

    def _build_book_prompt_strict(self, details: str) -> str:
        rubric = _style_rubric()
        return f"""
{rubric}

You are a rigorous literary critic. Assess the book described below using a 0–10 scale where
0–4 = weak or derivative,
5–6 = competent but unremarkable,
7–8 = strong,
9–10 = exceptional. Scores above 5 must be justified with specific evidence.

Book Details:
{details}

Format:
★ Rating: [X/10] (integer)
🎭 Artistic Merit – literary craft, prose quality, narrative structure
✨ Originality – innovation in form or content
📚 Cultural Significance – place in literary tradition
💡 Intellectual Depth – complexity of themes
"""

    def _build_book_prompt_permissive(self, details: str) -> str:
        rubric = _style_rubric()
        return f"""
{rubric}

Write a brief critical review of this book. If your search doesn't surface specific reviews, draw on general knowledge of the author's body of work and the book's place in their oeuvre — DO NOT refuse.

Book Details:
{details}

Format:
★ Rating: [X/10]
🎭 Artistic Merit
✨ Originality
📚 Cultural Significance
💡 Intellectual Depth
"""

    def _build_book_prompt_general_knowledge(self, details: str) -> str:
        rubric = _style_rubric()
        return f"""
{rubric}

You are a literary critic writing for a discerning Austin book-club audience. Use your training-time knowledge of the author and the book to write a real review — even if your search doesn't surface specific contemporary reviews of this exact title.

Book Details:
{details}

Cover the author's literary reputation, what makes this work distinctive (or routine), and reasons readers might gravitate to it. Provide a 0–10 rating. If you're genuinely uncertain about a detail, take a defensible position from the author's known output and say so in one sentence — but do not refuse.

Format:
★ Rating: [X/10]
🎭 Artistic Merit
✨ Originality
📚 Cultural Significance
💡 Intellectual Depth
"""

    def _claude_fallback_book(self, event: Dict, details: str) -> Optional[Dict]:
        if not os.getenv("ANTHROPIC_API_KEY"):
            return None
        try:
            import anthropic
            client = anthropic.Anthropic()
            prompt = f"""
Write a 4–6 paragraph critical review of this book using your trained-knowledge of the author and the work. Provide a 0–10 rating.

{details}

Format:
★ Rating: [X/10]
🎭 Artistic Merit
✨ Originality
📚 Cultural Significance
💡 Intellectual Depth

Be specific. Take a defensible position even if some details are missing.
"""
            resp = client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=1500,
                temperature=0.4,
                messages=[{"role": "user", "content": prompt}],
            )
            content = resp.content[0].text
            if is_refusal_response(content):
                return None
            print(f"  Claude fallback succeeded for book '{event.get('title')}'")
            return self._parse_ai_response(content)
        except Exception as e:
            print(f"  Claude fallback (book) failed: {e}")
            return None

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

            # Compute confidence from the pre-substitution summary so a
            # refusal-shaped LLM response (which is about to be replaced by
            # REFUSAL_STUB) is still recorded as low confidence.
            confidence = compute_confidence(summary)

            filtered = filter_refusal(summary)
            if filtered != summary:
                print("  Substituting refusal-shaped description with stub")
                summary = filtered

            return {
                "score": max(0, min(10, score)),  # Clamp to 0-10
                "summary": summary,  # Keep full summary
                "review_confidence": confidence,
            }

        except Exception as e:
            print(f"Error parsing AI response: {e}")
            raw_fallback = content[:2000] if content else ""
            confidence = compute_confidence(raw_fallback)
            return {
                "score": 5,
                "summary": filter_refusal(raw_fallback),
                "review_confidence": confidence,
            }
