"""
Smart validation service for Culture Calendar events
Provides real-time validation during scraping with fail-fast mechanisms
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

        # Validation thresholds
        self.min_scraper_success_rate = 0.5  # 50% of scrapers must succeed
        self.min_events_per_scraper = 1  # At least 1 valid event per scraper
        self.validation_sample_size = 3  # Sample 3 events per scraper

    def validate_event_schema(self, event: Dict) -> ValidationResult:
        """Validate event against its schema"""
        try:
            # Check required fields
            required_fields = ["title", "date", "venue", "type"]
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

            # Validate date format
            try:
                datetime.strptime(event["date"], "%Y-%m-%d")
            except ValueError:
                return ValidationResult(
                    passed=False,
                    level=ValidationLevel.CRITICAL,
                    message=f"Invalid date format: {event['date']}",
                    event_data=event,
                )

            # Validate event type
            event_type = event.get("type")
            if event_type not in ["screening", "concert", "book_club"]:
                return ValidationResult(
                    passed=False,
                    level=ValidationLevel.WARNING,
                    message=f"Unknown event type: {event_type}",
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
            if not self.llm_service.anthropic_api_key:
                return ValidationResult(
                    passed=True,
                    level=ValidationLevel.INFO,
                    message="LLM validation skipped (no API key)",
                    event_data=event,
                )

            # Construct validation prompt
            event_summary = f"""
            Title: {event.get('title', 'N/A')}
            Date: {event.get('date', 'N/A')}
            Time: {event.get('time', 'N/A')}
            Venue: {event.get('venue', 'N/A')}
            Type: {event.get('type', 'N/A')}
            Description: {str(event.get('description', 'N/A'))[:500]}...
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

            # Get LLM validation
            response = self.llm_service.analyze_with_anthropic(
                prompt, max_tokens=200, temperature=0.1
            )

            # Parse response
            try:
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
                    level = ValidationLevel.CRITICAL
                    message = f"LLM validation failed: {reasoning}"

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

        self.logger.info("🔍 Starting comprehensive scraper validation...")

        for scraper_name, events in scraper_results.items():
            self.logger.info(f"Validating {scraper_name}: {len(events)} events")

            health_check = self.validate_scraper_health(scraper_name, events)
            health_checks.append(health_check)

            # Log results
            if health_check.success_rate >= 0.5:  # 50% success threshold
                successful_scrapers += 1
                self.logger.info(
                    f"✅ {scraper_name}: {health_check.events_validated}/"
                    f"{len(health_check.sample_events)} events valid "
                    f"({health_check.success_rate:.1%})"
                )
            else:
                self.logger.warning(
                    f"⚠️ {scraper_name}: {health_check.events_validated}/"
                    f"{len(health_check.sample_events)} events valid "
                    f"({health_check.success_rate:.1%})"
                )

                # Log specific errors
                for error in health_check.errors[:3]:  # First 3 errors
                    self.logger.warning(f"   - {error}")

        # Determine if pipeline should continue
        total_scrapers = len(scraper_results)
        scraper_success_rate = (
            successful_scrapers / total_scrapers if total_scrapers > 0 else 0
        )

        should_continue = scraper_success_rate >= self.min_scraper_success_rate

        self.logger.info(
            f"📊 Validation Summary: {successful_scrapers}/{total_scrapers} scrapers passed "
            f"({scraper_success_rate:.1%})"
        )

        if should_continue:
            self.logger.info("✅ Pipeline validation passed - continuing...")
        else:
            self.logger.error(
                f"❌ Pipeline validation failed - only {scraper_success_rate:.1%} "
                f"of scrapers succeeded (minimum: {self.min_scraper_success_rate:.1%})"
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
