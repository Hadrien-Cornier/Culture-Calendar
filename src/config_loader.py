"""
Configuration loader for master_config.yaml
Provides read-only access to venue policies, templates, and validation rules
"""

import os
import yaml
from typing import Dict, Any, Optional, List


class ConfigLoader:
    """Read-only configuration loader for master_config.yaml"""

    def __init__(self, config_path: str = None):
        """
        Initialize configuration loader

        Args:
            config_path: Path to master_config.yaml (defaults to config/master_config.yaml)
        """
        if config_path is None:
            # Default to config/master_config.yaml relative to project root
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            config_path = os.path.join(project_root, "config", "master_config.yaml")

        self.config_path = config_path
        self._config = self._load_config()
        self._validate_config()

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")

        with open(self.config_path, "r") as f:
            config = yaml.safe_load(f)

        return config

    def _validate_config(self) -> None:
        """Validate that required configuration sections exist"""
        required_sections = [
            "style",
            "date_time_spec",
            "ontology",
            "templates",
            "venues",
        ]
        for section in required_sections:
            if section not in self._config:
                raise ValueError(f"Missing required configuration section: {section}")

        # Validate style configuration
        if self._config["style"].get("field_naming") != "snake_case":
            raise ValueError("Field naming must be 'snake_case'")

        # Validate date_time_spec
        date_spec = self._config["date_time_spec"]
        required_date_fields = [
            "date_field",
            "time_field",
            "date_format",
            "time_format",
        ]
        for field in required_date_fields:
            if field not in date_spec:
                raise ValueError(f"Missing required date_time_spec field: {field}")

    def get_venue_policy(self, venue_key: str) -> Dict[str, Any]:
        """
        Get venue-specific policy configuration

        Args:
            venue_key: Venue identifier (e.g., 'afs', 'hyperreal')

        Returns:
            Venue configuration dictionary
        """
        if venue_key not in self._config["venues"]:
            raise ValueError(f"Unknown venue: {venue_key}")

        return self._config["venues"][venue_key]

    def get_template(self, event_type: str) -> Dict[str, Any]:
        """
        Get template configuration for an event type

        Args:
            event_type: Event type (e.g., 'Movie', 'Concert')

        Returns:
            Template configuration dictionary
        """
        if event_type not in self._config["templates"]:
            # Return a minimal template for unknown types
            return {
                "fields": ["title", "dates", "times", "venue", "description", "url"],
                "required_on_publish": ["title", "dates", "times"],
            }

        return self._config["templates"][event_type]

    def get_date_time_spec(self) -> Dict[str, Any]:
        """
        Get date/time specification

        Returns:
            Date/time specification dictionary
        """
        return self._config["date_time_spec"]

    def get_allowed_event_categories(self) -> List[str]:
        """
        Get list of allowed event categories from ontology

        Returns:
            List of valid event category labels
        """
        return self._config["ontology"]["labels"]

    def is_classification_enabled(self, venue_key: str) -> bool:
        """
        Check if classification is enabled for a venue

        Args:
            venue_key: Venue identifier

        Returns:
            True if classification is enabled, False otherwise
        """
        venue_policy = self.get_venue_policy(venue_key)
        return venue_policy.get("classification", {}).get("enabled", True)

    def get_assumed_event_category(self, venue_key: str) -> Optional[str]:
        """
        Get assumed event category for a venue (if classification is disabled)

        Args:
            venue_key: Venue identifier

        Returns:
            Assumed event category or None
        """
        venue_policy = self.get_venue_policy(venue_key)
        classification = venue_policy.get("classification", {})

        if not classification.get("enabled", True):
            assumed = classification.get("assumed_event_category")
            if assumed and assumed in self.get_allowed_event_categories():
                return assumed
            elif assumed:
                raise ValueError(
                    f"Invalid assumed_event_category '{assumed}' for venue '{venue_key}'"
                )

        return None

    def get_validation_rules(self) -> Dict[str, Any]:
        """
        Get validation rules

        Returns:
            Validation rules dictionary
        """
        return self._config.get(
            "validation",
            {
                "fail_fast": True,
                "error_on_missing_required_on_publish": True,
                "error_on_mismatched_dates_times_length": True,
            },
        )

    def get_extraction_schema(
        self, venue_key: str, event_type: str = None
    ) -> Dict[str, Any]:
        """
        Get the complete extraction schema for a venue, merging template definitions
        with venue-specific overrides.

        Args:
            venue_key: Venue identifier (e.g., 'alienated_majesty')
            event_type: Event type to use for template (defaults to venue's assumed category)

        Returns:
            Complete extraction schema with all overrides applied
        """
        # Get venue configuration
        venue_config = self.get_venue_policy(venue_key)

        # Determine event type
        if not event_type:
            event_type = self.get_assumed_event_category(venue_key)
            if not event_type:
                raise ValueError(
                    f"No event type specified and no assumed category for venue '{venue_key}'"
                )

        # Get base template
        template = self.get_template(event_type)
        field_definitions = template.get("field_definitions", {})
        required_fields = template.get("required_on_publish", [])

        if not field_definitions:
            raise ValueError(
                f"No field definitions found for event type '{event_type}'"
            )

        # Get venue-specific overrides
        field_overrides = venue_config.get("field_overrides", {})
        extraction_config = venue_config.get("extraction", {})

        # Build merged field schema
        items_schema = {}
        for field_name, field_def in field_definitions.items():
            # Start with base field definition
            field_schema = {
                "type": field_def.get("type", "string"),
                "required": field_name in required_fields,
                "description": field_def.get("description", ""),
            }

            # Apply venue-specific overrides
            if field_name in field_overrides:
                override = field_overrides[field_name]

                # Override required if specified
                if "required" in override:
                    field_schema["required"] = override["required"]

                # Replace or append to description
                if "description" in override:
                    field_schema["description"] = override["description"]
                elif "description_append" in override:
                    field_schema["description"] += override["description_append"]

                # Store metadata for runtime processing
                if "default_value" in override:
                    field_schema["default_value"] = override["default_value"]

                if "dynamic_guidance" in override:
                    field_schema["dynamic_guidance"] = override["dynamic_guidance"]

            items_schema[field_name] = field_schema

        # Build complete schema
        schema = {
            "type": "object",
            "fields": items_schema,
            "batch_description": extraction_config.get(
                "batch_description",
                f"List of {event_type} events extracted from the webpage.",
            ),
            "field_overrides": field_overrides,  # Keep raw overrides for post-processing
        }

        return schema

    def apply_default_values(
        self, event: Dict[str, Any], venue_key: str
    ) -> Dict[str, Any]:
        """
        Apply default values from configuration to an event.

        Args:
            event: Event data to apply defaults to
            venue_key: Venue identifier

        Returns:
            Event with default values applied
        """
        venue_config = self.get_venue_policy(venue_key)
        field_overrides = venue_config.get("field_overrides", {})

        # Apply default values
        for field_name, override in field_overrides.items():
            if "default_value" in override and not event.get(field_name):
                event[field_name] = override["default_value"]

        return event

    def get_field_defaults(self) -> Dict[str, Any]:
        """
        Get field default values from configuration

        Returns:
            Dictionary of field default values
        """
        return self._config.get(
            "field_defaults",
            {
                "rating": -1,
                "description": "No description available",
                "country": "USA",
                "language": "English",
                "url": "",
                "venue": "",
            },
        )
