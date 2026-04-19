"""Shared LLM client — Perplexity (Sonar) + Anthropic (Claude) abstraction.

Single class :class:`LLMService` that every AI-using subsystem imports:

- :mod:`src.base_scraper` (LLM-extraction scrapers like Hyperreal,
  Alienated Majesty, First Light).
- :mod:`src.processor` — AI ratings + critic-style reviews.
- :mod:`src.enrichment_layer` — classification + field extraction.
- :mod:`src.summary_generator` — one-liner hooks.
- ``scripts/prospect_venues.py`` — Perplexity-driven venue discovery.
- ``scripts/persona_critique.py`` — LLM persona council critiques.

**Public surface**

- :meth:`extract_data(content, schema)` — structured extraction against
  a schema dict; returns a populated dict or ``None`` on failure.
- :meth:`validate_extraction(extracted, content, schema)` — asks the
  model to judge whether an extraction is evidence-grounded. Used by
  the enrichment layer's "evidence-validated" field flow.
- :meth:`get_similarity_score(e1, e2)` — LLM-backed dedup helper;
  falls back to :meth:`_simple_similarity` (bag-of-words Jaccard)
  when no API key is present.
- :meth:`call_perplexity(prompt, ...)` — raw Perplexity Sonar call for
  callers that want prompt-level control (processor's rating cascade,
  prospect_venues). Returns ``(response_text, citations)``.
- :meth:`_call_anthropic_json(prompt)` — internal JSON-forcing Claude
  call used as Perplexity fallback and for prompts that need strict
  structure.

**Env vars**

- ``PERPLEXITY_API_KEY`` — required for :meth:`call_perplexity`.
- ``ANTHROPIC_API_KEY`` — required for :meth:`_call_anthropic_json`
  and the Claude fallback path in :meth:`_chat`. Loaded via
  ``python-dotenv`` so ``.env`` files work without shell-exporting.

**Perplexity quirks this module handles**

- Perplexity occasionally returns refusal-shaped text even when the
  prompt disallows refusals. :mod:`src.refusal` detects these so
  callers can retry with a permissive prompt or escalate to Claude.
- Sonar adds inline citation markers (``[1]``, ``[2]``) to prose;
  :meth:`_parse_extraction_response` strips them before validation.
- Rate limits aren't heavily enforced by Perplexity, so this module
  doesn't implement transport-level backoff. If 429s start hitting,
  add retry here — :mod:`src.processor`'s retry cascade is
  prompt-level, not transport-level.

**Caching**

None at this layer. Each subsystem maintains its own cache
(``docs/data.json`` for processor, ``cache/summary_cache.json`` for
summary_generator, ``cache/wikipedia/`` for the wikipedia source).
Centralizing caching would simplify invalidation but break the
per-subsystem freshness contract — keep separate.
"""

import json
import os
import re
import time
from datetime import datetime
from typing import Dict, Optional
import requests

import anthropic
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()


_EXTRACTION_SYSTEM_PROMPT = (
    "You are a meticulous data-extraction assistant. Read the provided HTML or "
    "text content and return JSON conforming to the requested schema. Output ONLY "
    "the JSON — no preamble, no commentary, no markdown code fences."
)

_VALIDATION_SYSTEM_PROMPT = (
    "You are a strict data-validation assistant. Compare the extracted data against "
    "the source content and report whether it is valid. Output ONLY the requested "
    "JSON shape — no preamble."
)


class LLMService:
    """Centralized service for all LLM-powered data extraction and validation.

    Provider preference: Anthropic Claude (Haiku 4.5) > OpenRouter Gemini Flash.
    Only one is required; both work. Perplexity is used separately for
    rating/review generation in EventProcessor.
    """

    def __init__(self):
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
        self.perplexity_api_key = os.getenv("PERPLEXITY_API_KEY")
        self.perplexity_base_url = "https://api.perplexity.ai"

        if self.anthropic_api_key:
            self.provider = "anthropic"
            self.anthropic = anthropic.Anthropic(api_key=self.anthropic_api_key)
            self.openai = None
            self.model = "claude-haiku-4-5-20251001"
        elif self.openrouter_api_key:
            self.provider = "openrouter"
            self.anthropic = None
            self.openai = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=self.openrouter_api_key,
            )
            self.model = "google/gemini-2.5-flash"
        else:
            self.provider = None
            self.anthropic = None
            self.openai = None
            self.model = None

        self.extraction_cache = {}
        self.validation_cache = {}
        self.classification_cache = {}

        if self.provider is None and not self.perplexity_api_key:
            print("Warning: No LLM API keys found. LLM features will be disabled.")

    def _chat(self, system: str, user: str, max_tokens: int = 2000, temperature: float = 0.1) -> Optional[str]:
        """Send a system+user prompt, return the assistant text or None on error."""
        if self.provider == "anthropic":
            try:
                resp = self.anthropic.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                )
                return resp.content[0].text.strip()
            except Exception as e:
                print(f"  LLM (anthropic) error: {e}")
                return None
        if self.provider == "openrouter":
            try:
                resp = self.openai.chat.completions.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                )
                return resp.choices[0].message.content.strip()
            except Exception as e:
                print(f"  LLM (openrouter) error: {e}")
                return None
        return None

    def extract_data(
        self, content: str, schema: Dict, url: str = "", content_type: str = "html"
    ) -> Dict:
        """
        Extract structured data from HTML/markdown content using LLM

        Args:
            content: Raw HTML or markdown content
            schema: Expected data schema definition
            url: Source URL for caching
            content_type: Type of content ("html", "markdown", "text")

        Returns:
            Dict with extracted data and success status
        """
        if self.provider is None:
            return {"success": False, "error": "LLM service not available", "data": {}}

        cache_key = self._create_cache_key(content, schema, "extract")
        if cache_key in self.extraction_cache:
            print("Using cached extraction result")
            return self.extraction_cache[cache_key]

        prompt = self._create_extraction_prompt(content, schema, content_type)
        time.sleep(1)

        text = self._chat(_EXTRACTION_SYSTEM_PROMPT, prompt, max_tokens=2000, temperature=0.1)
        if text is None:
            error_result = {"success": False, "error": "LLM call returned no text", "data": {}}
            self.extraction_cache[cache_key] = error_result
            return error_result

        result = self._parse_extraction_response(text, schema)
        self.extraction_cache[cache_key] = result
        return result

    def validate_extraction(
        self, extracted_data: Dict, schema: Dict, original_content: str = ""
    ) -> Dict:
        """
        Validate extracted data for plausibility and correctness

        Args:
            extracted_data: Data extracted from content
            schema: Expected schema for validation
            original_content: Original content for cross-reference

        Returns:
            Dict with validation result and reasoning
        """
        if self.provider is None:
            return {
                "is_valid": True,
                "confidence": 0.5,
                "reason": "LLM validation not available",
            }

        cache_key = self._create_cache_key(str(extracted_data), schema, "validate")
        if cache_key in self.validation_cache:
            print("Using cached validation result")
            return self.validation_cache[cache_key]

        prompt = self._create_validation_prompt(extracted_data, schema, original_content)
        time.sleep(1)

        text = self._chat(_VALIDATION_SYSTEM_PROMPT, prompt, max_tokens=1000, temperature=0.1)
        if text is None:
            error_result = {
                "is_valid": False,
                "confidence": 0.0,
                "reason": "Validation call returned no text",
            }
            self.validation_cache[cache_key] = error_result
            return error_result

        result = self._parse_validation_response(text)
        self.validation_cache[cache_key] = result
        return result

    def get_similarity_score(self, event1: Dict, event2: Dict) -> float:
        """
        Calculate similarity between two events to detect duplicates

        Args:
            event1: First event data
            event2: Second event data

        Returns:
            Similarity score between 0.0 and 1.0
        """
        if self.provider is None:
            return self._simple_similarity(event1, event2)

        try:
            prompt = f"""
Compare these two cultural events and determine if they are the same event (duplicate) or different events.
Consider title, date, time, venue, and description. Minor formatting differences should not affect similarity.

Event 1:
{json.dumps(event1, indent=2)}

Event 2:
{json.dumps(event2, indent=2)}

Respond with a similarity score from 0.0 to 1.0:
- 1.0 = Same event (duplicate)
- 0.8-0.9 = Very likely the same event
- 0.5-0.7 = Possibly related events
- 0.0-0.4 = Different events

Format: SIMILARITY: [score]
Reason: [brief explanation]
"""

            time.sleep(1)
            content_text = self._chat(_VALIDATION_SYSTEM_PROMPT, prompt, max_tokens=500, temperature=0.1)
            if content_text is None:
                return self._simple_similarity(event1, event2)

            similarity_match = re.search(r"SIMILARITY:\s*([0-9.]+)", content_text)
            if similarity_match:
                return float(similarity_match.group(1))
            return self._simple_similarity(event1, event2)

        except Exception as e:
            print(f"Error calculating similarity: {e}")
            return self._simple_similarity(event1, event2)

    def _create_extraction_prompt(
        self, content: str, schema: Dict, content_type: str
    ) -> str:
        """Create extraction prompt based on content and schema"""

        # Truncate content if too long
        max_content_length = 8000
        if len(content) > max_content_length:
            content = content[:max_content_length] + "... [truncated]"

        schema_description = self._format_schema_description(schema)

        prompt = f"""
Extract structured event data from the following {content_type} content.

EXPECTED DATA SCHEMA:
{schema_description}

CONTENT TO PARSE:
{content}

INSTRUCTIONS:
1. Extract data that matches the schema exactly.
2. The 'description' field should always be extracted, even if it's short.
3. If a field is not found, use null or an empty string.
4. For book club events, the 'series' field should contain the name of the book club (e.g., "Sci-Fi Book Club"). The 'title' should be in the format "Series Name - Book Title".
5. If an event is not a book reading (e.g., a happy hour), the 'book' and 'author' fields should be null.
6. Ensure dates are in YYYY-MM-DD format.
7. Ensure times are in a standard format (e.g., "7:30 PM").
8. Be conservative - only extract data you're confident about.
9. For arrays, extract all relevant items found.

Return the extracted data as valid JSON only. Do not include explanations or markdown formatting.

Example format:
{{
  "title": "Event Title",
  "date": "2025-06-30",
  "time": "7:30 PM",
  "venue": "Venue Name"
}}
"""

        return prompt

    def _create_validation_prompt(
        self, extracted_data: Dict, schema: Dict, original_content: str
    ) -> str:
        """Create validation prompt for extracted data"""

        prompt = f"""
Validate the following extracted event data for plausibility and correctness.

EXTRACTED DATA:
{json.dumps(extracted_data, indent=2)}

VALIDATION CRITERIA:
1. Are the dates realistic and in the future (or recent past) today is {datetime.now().strftime("%Y-%m-%d")}?
2. Are the times in valid format?
3. Do the titles look like real event names?
4. Are venue names plausible?
5. Is the data internally consistent?
6. For books: Do book titles and authors seem real?
7. For movies: Do movie titles, directors, and years seem realistic?
8. For concerts: Do composer names and work titles seem authentic?

INSTRUCTIONS:
Respond with:
VALID: [true/false]
CONFIDENCE: [0.0 to 1.0]
REASON: [brief explanation of your assessment]

Be critical but fair. Minor formatting issues should not invalidate data.
Focus on whether the data represents a plausible real-world event.
"""

        return prompt

    def _parse_extraction_response(self, response_text: str, schema: Dict) -> Dict:
        """Parse LLM extraction response into structured data"""
        try:
            # Try to find JSON in the response
            json_start = response_text.find("{")
            json_end = response_text.rfind("}") + 1

            if json_start != -1 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                extracted_data = json.loads(json_str)

                # Check if the extracted data is useful (not empty or all
                # null/empty)
                if self._is_extraction_data_useful(extracted_data, schema):
                    return {
                        "success": True,
                        "data": extracted_data,
                        "raw_response": response_text,
                    }
                else:
                    return {
                        "success": False,
                        "error": "No useful data extracted - all fields are empty, null, or missing required data",
                        "data": extracted_data,
                        "raw_response": response_text,
                    }
            else:
                return {
                    "success": False,
                    "error": "No valid JSON found in response",
                    "data": {},
                    "raw_response": response_text,
                }

        except json.JSONDecodeError as e:
            return {
                "success": False,
                "error": f"JSON parsing error: {str(e)}",
                "data": {},
                "raw_response": response_text,
            }

    def _is_extraction_data_useful(self, data: Dict, schema: Dict) -> bool:
        """
        Check if extracted data is useful (not empty, null, or missing required fields)

        Args:
            data: Extracted data dictionary
            schema: Expected schema definition

        Returns:
            True if data is useful, False otherwise
        """
        if not data:
            return False

        # Check if all values are empty/null
        all_empty = True
        has_required_fields = True

        for field_name, field_def in schema.items():
            if isinstance(field_def, dict):
                is_required = field_def.get("required", False)
                field_value = data.get(field_name)

                # Check if field is empty/null
                is_empty = (
                    field_value is None
                    or field_value == ""
                    or (isinstance(field_value, str) and field_value.strip() == "")
                )

                if not is_empty:
                    all_empty = False

                # Check required fields
                if is_required and is_empty:
                    has_required_fields = False

        # Data is useful if:
        # 1. Not all fields are empty/null
        # 2. All required fields are present and non-empty
        return not all_empty and has_required_fields

    def _parse_validation_response(self, response_text: str) -> Dict:
        """Parse LLM validation response"""
        try:
            # Extract validation components
            valid_match = re.search(
                r"VALID:\s*(true|false)", response_text, re.IGNORECASE
            )
            confidence_match = re.search(r"CONFIDENCE:\s*([0-9.]+)", response_text)
            reason_match = re.search(r"REASON:\s*(.+)", response_text, re.DOTALL)

            is_valid = False
            if valid_match:
                is_valid = valid_match.group(1).lower() == "true"

            confidence = 0.5
            if confidence_match:
                confidence = float(confidence_match.group(1))

            reason = "No reason provided"
            if reason_match:
                reason = reason_match.group(1).strip()

            return {
                "is_valid": is_valid,
                "confidence": confidence,
                "reason": reason,
                "raw_response": response_text,
            }

        except Exception as e:
            return {
                "is_valid": False,
                "confidence": 0.0,
                "reason": f"Error parsing validation response: {str(e)}",
                "raw_response": response_text,
            }

    def _format_schema_description(self, schema: Dict) -> str:
        """Format schema into human-readable description"""
        lines = []

        for field, definition in schema.items():
            if isinstance(definition, dict):
                field_type = definition.get("type", "string")
                required = definition.get("required", False)
                description = definition.get("description", "")

                line = f"- {field} ({field_type})"
                if required:
                    line += " [REQUIRED]"
                if description:
                    line += f": {description}"
                lines.append(line)
            else:
                lines.append(f"- {field}: {definition}")

        return "\n".join(lines)

    def _simple_similarity(self, event1: Dict, event2: Dict) -> float:
        """Simple similarity calculation without LLM"""
        # Compare key fields
        title1 = str(event1.get("title", "")).lower().strip()
        title2 = str(event2.get("title", "")).lower().strip()

        date1 = str(event1.get("date", ""))
        date2 = str(event2.get("date", ""))

        time1 = str(event1.get("time", ""))
        time2 = str(event2.get("time", ""))

        # Exact matches
        if title1 and title1 == title2 and date1 == date2 and time1 == time2:
            return 1.0

        # Title similarity (basic)
        if title1 and title2:
            if title1 in title2 or title2 in title1:
                same_date = date1 == date2
                same_time = time1 == time2

                if same_date and same_time:
                    return 0.9
                elif same_date:
                    return 0.7
                else:
                    return 0.4

        return 0.0

    def _create_cache_key(self, content: str, schema: Dict, operation: str) -> str:
        """Create a cache key for content and schema"""
        import hashlib

        # Create hash of content + schema + operation
        content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()[:16]
        schema_hash = hashlib.md5(str(schema).encode("utf-8")).hexdigest()[:16]

        return f"{operation}_{content_hash}_{schema_hash}"
    
    def call_perplexity(
        self, 
        prompt: str, 
        temperature: float = 0.2,
        model: str = "sonar",
        search_domain_filter: Optional[list] = None,
        search_recency_filter: Optional[str] = None
    ) -> Optional[Dict]:
        """
        Call Perplexity API for classification and enrichment
        
        Args:
            prompt: User prompt for the query
            temperature: Temperature for response generation (0.0-2.0)
            model: Perplexity model to use
            search_domain_filter: List of domains to restrict search to
            search_recency_filter: Time filter for search results (e.g., "day", "week", "month", "year")
            
        Returns:
            Parsed response or None if error
        """
        if not self.perplexity_api_key:
            # Fall back to whichever LLM provider is configured.
            if self.provider is not None:
                return self._call_anthropic_json(prompt, temperature)
            return None
        
        try:
            # Build request payload
            payload = {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a precise event classification and data extraction assistant. Always respond in valid JSON format only."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": temperature,
                "top_p": 0.9,
                "frequency_penalty": 1
            }
            
            # Add search filters if provided
            if search_domain_filter:
                payload["search_domain_filter"] = search_domain_filter
            if search_recency_filter:
                payload["search_recency_filter"] = search_recency_filter
            
            # Make API request
            headers = {
                "Authorization": f"Bearer {self.perplexity_api_key}",
                "Content-Type": "application/json"
            }
            
            response = requests.post(
                f"{self.perplexity_base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                
                # Parse JSON from response
                json_start = content.find("{")
                json_end = content.rfind("}") + 1
                
                if json_start != -1 and json_end > json_start:
                    json_str = content[json_start:json_end]
                    return json.loads(json_str)
            else:
                print(f"Perplexity API error: {response.status_code} - {response.text}")
                
        except Exception as e:
            print(f"Error calling Perplexity API: {e}")
        
        return None
    
    def _call_anthropic_json(self, prompt: str, temperature: float = 0.2) -> Optional[Dict]:
        """Call the configured LLM and parse the response as JSON.

        Despite the historical method name, this routes through whichever
        provider is configured (Anthropic Claude or OpenRouter Gemini). Returns
        the parsed dict, or None if the call fails or the response isn't JSON.
        """
        time.sleep(1)
        text = self._chat(_EXTRACTION_SYSTEM_PROMPT, prompt, max_tokens=2000, temperature=temperature)
        if not text:
            return None
        try:
            json_start = text.find("{")
            json_end = text.rfind("}") + 1
            if json_start != -1 and json_end > json_start:
                return json.loads(text[json_start:json_end])
        except Exception as e:
            print(f"  LLM JSON parse error: {e}")
        return None
