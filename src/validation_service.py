"""Scraper health checks + fail-fast validation.

Wired up via the ``--validate`` flag on ``update_website_data.py``.
Runs between scraping (Phase One) and enrichment (Phase Two) to
catch catastrophic scraper failures before expensive LLM work burns
on garbage input.

**Why fail-fast matters**

Without this layer, a scraper regression (e.g., venue redesigns the
HTML so selectors match nothing) silently drops events to the floor.
The pipeline finishes, the website updates with fewer events, and
nobody notices until a user complains that "where did all the AFS
screenings go?". Validation catches the drop before LLM calls and
halts the build.

**Severity levels** (:class:`ValidationLevel` enum)

- ``CRITICAL`` — counts against a venue's health score. Reserved for
  deterministic schema failures (missing title/dates/venue, bad date
  format).
- ``WARNING`` — log and continue. Includes LLM content-validation
  "invalid" verdicts, which are advisory only (see incident note below).
- ``INFO`` — telemetry only.

**Gate policy** (:meth:`validate_all_scrapers`)

Publishing the healthy subset beats killing the whole run when one venue
breaks. The pipeline aborts only on systemic failure: zero events across
all scrapers, zero healthy scrapers, or more failed than healthy
scrapers. A single bad venue must never stall the whole calendar — the
July 2026 incident is the cautionary tale: the validator prompt showed
``Date: N/A`` for every normalized ``dates[]`` event (it read the
singular ``date`` key), deepseek-v4-flash strictly judged them all
invalid, five scrapers "failed", and publishing froze for weeks while
every scraper was actually healthy.

Reports are collected on the service instance for post-run summary
printing. The caller (``update_website_data.py``) exits non-zero only
when the gate says the failure is systemic.

**Schemas** — validation references :class:`src.schemas.SchemaRegistry`,
not :mod:`src.config_loader`. The registry is kept hand-synced with
``config/master_config.yaml`` templates; if you add a field in one,
add it in the other. Tests/test_validation_integration.py guards this.
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple

from .llm_service import LLMService
from .schemas import SchemaRegistry


class ValidationLevel(Enum):
    """Validation severity levels"""

    CRITICAL = "critical"  # Must pass - workflow fails if not
    WARNING = "warning"  # Should pass - logged but not fatal
    INFO = "info"  # Nice to have - informational only


@dataclass
class ValidationResult:
    """Result of a validation check"""

    passed: bool
    level: ValidationLevel
    message: str
    details: Optional[Dict] = None
    event_data: Optional[Dict] = None


@dataclass
class ScraperHealthCheck:
    """Health check result for a scraper"""

    scraper_name: str
    events_found: int
    events_validated: int
    success_rate: float
    sample_events: List[Dict]
    errors: List[str]
    timestamp: datetime


class EventValidationService:
    """Smart validation service for cultural event data"""

    def __init__(self, llm_service: Optional[LLMService] = None):
        self.llm_service = llm_service or LLMService()
        self.schema_registry = SchemaRegistry()

        # Configure logging
        self.logger = logging.getLogger(__name__)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)

        # Validation settings
        self.min_events_per_scraper = 1  # At least 1 valid event per scraper
        self.validation_sample_size = 3  # Sample 3 events per scraper

    def validate_event_schema(self, event: Dict) -> ValidationResult:
        """Validate event against its schema"""
        try:
            # Check required fields (match master_config.yaml schema)
            required_fields = ["title", "dates", "venue"]
            missing_fields = [
                field for field in required_fields if not event.get(field)
            ]

            if missing_fields:
                return ValidationResult(
                    passed=False,
                    level=ValidationLevel.CRITICAL,
                    message=f"Missing required fields: {missing_fields}",
                    event_data=event,
                )

            # Validate dates format (array of YYYY-MM-DD strings)
            dates = event.get("dates", [])
            if not isinstance(dates, list):
                dates = [dates]

            for date in dates:
                try:
                    datetime.strptime(str(date), "%Y-%m-%d")
                except ValueError:
                    return ValidationResult(
                        passed=False,
                        level=ValidationLevel.CRITICAL,
                        message=f"Invalid date format: {date} (expected YYYY-MM-DD)",
                        event_data=event,
                    )

            # Validate event_category (from master_config ontology labels)
            event_category = event.get("event_category")
            if event_category and event_category not in [
                "movie",
                "concert",
                "book_club",
                "opera",
                "dance",
                "other",
            ]:
                return ValidationResult(
                    passed=False,
                    level=ValidationLevel.WARNING,
                    message=f"Unknown event_category: {event_category}",
                    event_data=event,
                )

            return ValidationResult(
                passed=True,
                level=ValidationLevel.INFO,
                message="Schema validation passed",
                event_data=event,
            )

        except Exception as e:
            return ValidationResult(
                passed=False,
                level=ValidationLevel.CRITICAL,
                message=f"Schema validation error: {str(e)}",
                event_data=event,
            )

    def validate_event_content_with_llm(self, event: Dict) -> ValidationResult:
        """Use LLM to validate event content quality"""
        try:
            if self.llm_service.provider is None:
                return ValidationResult(
                    passed=True,
                    level=ValidationLevel.INFO,
                    message="LLM validation skipped (no LLM provider)",
                    event_data=event,
                )

            # Construct validation prompt. Read BOTH event shapes: raw
            # scraper output may use singular `date`/`time`, while the
            # normalized shape uses pairwise `dates[]`/`times[]` arrays.
            # Reading only the singular keys shows the LLM "Date: N/A" for
            # every normalized event, and strict models mark them all
            # invalid (the July 2026 publishing freeze).
            dates = event.get("dates") or (
                [event["date"]] if event.get("date") else []
            )
            times = event.get("times") or (
                [event["time"]] if event.get("time") else []
            )
            event_type = event.get("type") or event.get("event_category") or "N/A"
            description = str(event.get("description") or "").strip()
            if len(description) > 500:
                description = description[:500] + "..."
            event_summary = f"""
            Title: {event.get('title', 'N/A')}
            Dates: {', '.join(str(d) for d in dates) or 'N/A'}
            Times: {', '.join(str(t) for t in times) or 'N/A'}
            Venue: {event.get('venue', 'N/A')}
            Type: {event_type}
            Description: {description or 'N/A'}
            """

            prompt = f"""
            Please validate if this appears to be a legitimate cultural event (movie screening, concert, or book club).

            Event Details:
            {event_summary}

            Validation Criteria:
            1. Has realistic venue, date, and time information
            2. Title and description make sense for the event type
            3. Contains meaningful content (not placeholder text or errors)
            4. Appears to be a real cultural event, not spam or malformed data

            Respond with JSON only:
            {{
                "is_valid": true/false,
                "confidence": 0.0-1.0,
                "issues": ["list of specific issues found"],
                "reasoning": "brief explanation"
            }}
            """

            # Route through LLMService._chat so validation works on whichever
            # provider is active (OpenRouter deepseek-v4-flash by default, or
            # Anthropic Claude as fallback) — not hardwired to the Anthropic SDK.
            response = self.llm_service._chat(
                "You are a strict validator of cultural-event data. "
                "Respond with JSON only.",
                prompt,
                max_tokens=200,
                temperature=0.1,
            )
            if not response:
                return ValidationResult(
                    passed=True,
                    level=ValidationLevel.INFO,
                    message="LLM validation skipped (no LLM response)",
                    event_data=event,
                )

            # Parse response (tolerate code fences / preamble around the JSON)
            try:
                json_start = response.find("{")
                json_end = response.rfind("}") + 1
                if json_start != -1 and json_end > json_start:
                    response = response[json_start:json_end]
                validation_data = json.loads(response)
                is_valid = validation_data.get("is_valid", False)
                confidence = validation_data.get("confidence", 0.0)
                issues = validation_data.get("issues", [])
                reasoning = validation_data.get("reasoning", "")

                if is_valid and confidence > 0.7:
                    level = ValidationLevel.INFO
                    message = f"LLM validation passed (confidence: {confidence:.2f})"
                elif is_valid and confidence > 0.5:
                    level = ValidationLevel.WARNING
                    message = (
                        f"LLM validation passed with low confidence: {confidence:.2f}"
                    )
                else:
                    # Advisory only — an LLM "invalid" verdict must NOT sink
                    # an otherwise schema-valid event. Validator models can be
                    # over-strict or be shown an incomplete summary; the
                    # deterministic schema check is the tripwire that counts.
                    level = ValidationLevel.WARNING
                    message = f"LLM validation advisory (event kept): {reasoning}"

                return ValidationResult(
                    passed=is_valid and confidence > 0.5,
                    level=level,
                    message=message,
                    details={
                        "confidence": confidence,
                        "issues": issues,
                        "reasoning": reasoning,
                    },
                    event_data=event,
                )

            except json.JSONDecodeError:
                return ValidationResult(
                    passed=False,
                    level=ValidationLevel.WARNING,
                    message="LLM returned invalid JSON response",
                    details={"raw_response": response},
                    event_data=event,
                )

        except Exception as e:
            self.logger.warning(f"LLM validation error: {str(e)}")
            return ValidationResult(
                passed=True,  # Don't fail on LLM errors
                level=ValidationLevel.WARNING,
                message=f"LLM validation error: {str(e)}",
                event_data=event,
            )

    def validate_event(
        self, event: Dict, use_llm: bool = True
    ) -> List[ValidationResult]:
        """Comprehensive event validation"""
        results = []

        # Schema validation
        schema_result = self.validate_event_schema(event)
        results.append(schema_result)

        # LLM content validation (if enabled and schema passed)
        if use_llm and schema_result.passed:
            llm_result = self.validate_event_content_with_llm(event)
            results.append(llm_result)

        return results

    def validate_scraper_health(
        self, scraper_name: str, events: List[Dict], sample_size: Optional[int] = None
    ) -> ScraperHealthCheck:
        """Validate health of a specific scraper"""
        sample_size = sample_size or self.validation_sample_size

        # Sample events for validation
        sample_events = events[:sample_size] if events else []

        validated_events = 0
        all_errors = []

        for event in sample_events:
            validation_results = self.validate_event(event, use_llm=True)

            # Check if event passed all critical validations
            critical_failures = [
                r
                for r in validation_results
                if r.level == ValidationLevel.CRITICAL and not r.passed
            ]

            if not critical_failures:
                validated_events += 1
            else:
                # Collect error messages
                errors = [r.message for r in critical_failures]
                all_errors.extend(errors)

        success_rate = validated_events / len(sample_events) if sample_events else 0.0

        return ScraperHealthCheck(
            scraper_name=scraper_name,
            events_found=len(events),
            events_validated=validated_events,
            success_rate=success_rate,
            sample_events=sample_events,
            errors=all_errors,
            timestamp=datetime.now(),
        )

    def validate_all_scrapers(
        self, scraper_results: Dict[str, List[Dict]]
    ) -> Tuple[bool, List[ScraperHealthCheck]]:
        """
        Validate all scrapers and determine if pipeline should continue
        Returns: (should_continue, health_checks)
        """
        health_checks = []
        successful_scrapers = 0
        failed_scrapers = 0
        zero_event_scrapers = []
        total_events = sum(len(events) for events in scraper_results.values())

        self.logger.info("🔍 Starting comprehensive scraper validation...")

        for scraper_name, events in scraper_results.items():
            self.logger.info(f"Validating {scraper_name}: {len(events)} events")

            # Skip validation if scraper returned no events — but surface
            # them in the report so a silent venue redesign is visible.
            if not events:
                self.logger.info(f"⏭️ {scraper_name}: No events to validate")
                zero_event_scrapers.append(scraper_name)
                continue

            health_check = self.validate_scraper_health(scraper_name, events)
            health_checks.append(health_check)

            # Log results
            if (
                health_check.success_rate >= 0.5
            ):  # 50% success threshold for individual scrapers
                successful_scrapers += 1
                self.logger.info(
                    f"✅ {scraper_name}: {health_check.events_validated}/"
                    f"{len(health_check.sample_events)} events valid "
                    f"({health_check.success_rate:.1%})"
                )
            else:
                failed_scrapers += 1
                self.logger.warning(
                    f"⚠️ {scraper_name}: {health_check.events_validated}/"
                    f"{len(health_check.sample_events)} events valid "
                    f"({health_check.success_rate:.1%})"
                )

                # Log specific errors
                for error in health_check.errors[:3]:  # First 3 errors
                    self.logger.warning(f"   - {error}")

        # Degradation policy: publish the healthy subset rather than kill the
        # whole run for isolated venue breakage. Abort only on systemic
        # failure:
        #   - no scraper produced any events at all (total collapse), or
        #   - zero healthy scrapers while some failed, or
        #   - more scrapers failed than passed (shared cause likely: network,
        #     LLM provider outage, config breakage).
        if total_events == 0:
            should_continue = False
            abort_reason = "no scraper produced any events"
        elif successful_scrapers == 0 and failed_scrapers > 0:
            should_continue = False
            abort_reason = "every event-bearing scraper failed validation"
        elif failed_scrapers > successful_scrapers:
            should_continue = False
            abort_reason = (
                f"more scrapers failed ({failed_scrapers}) than passed "
                f"({successful_scrapers})"
            )
        else:
            should_continue = True
            abort_reason = ""

        total_validated = successful_scrapers + failed_scrapers

        if total_validated > 0:
            self.logger.info(
                f"📊 Validation Summary: {successful_scrapers}/{total_validated} scrapers passed"
            )
        else:
            self.logger.info(
                "📊 Validation Summary: No scrapers had events to validate"
            )

        if zero_event_scrapers:
            self.logger.warning(
                f"⚠️ Zero-event venues (skipped, not counted as failures): "
                f"{', '.join(zero_event_scrapers)}"
            )

        if should_continue:
            if failed_scrapers:
                self.logger.warning(
                    f"⚠️ {failed_scrapers} scraper(s) failed validation - "
                    "continuing with the healthy subset (degraded mode)"
                )
            self.logger.info("✅ Pipeline validation passed - continuing...")
        else:
            self.logger.error(
                f"❌ Pipeline validation failed (systemic): {abort_reason}"
            )

        return should_continue, health_checks

    def log_validation_report(self, health_checks: List[ScraperHealthCheck]) -> None:
        """Generate detailed validation report"""
        self.logger.info("\n" + "=" * 60)
        self.logger.info("📋 VALIDATION REPORT")
        self.logger.info("=" * 60)

        for health_check in health_checks:
            self.logger.info(f"\n{health_check.scraper_name}:")
            self.logger.info(f"  📊 Events Found: {health_check.events_found}")
            self.logger.info(f"  ✅ Events Validated: {health_check.events_validated}")
            self.logger.info(f"  📈 Success Rate: {health_check.success_rate:.1%}")

            if health_check.errors:
                self.logger.info(f"  ⚠️ Issues Found:")
                for error in health_check.errors[:5]:  # First 5 errors
                    self.logger.info(f"    - {error}")

        self.logger.info("=" * 60)


# Convenience function for quick validation
def quick_validate_events(events: List[Dict], scraper_name: str = "Unknown") -> bool:
    """Quick validation for a list of events - returns True if >= 50% pass"""
    validator = EventValidationService()
    health_check = validator.validate_scraper_health(scraper_name, events)
    return health_check.success_rate >= 0.5
