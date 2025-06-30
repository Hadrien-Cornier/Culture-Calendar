"""
Data schemas for different venue types in the Culture Calendar system
"""

from typing import Any, Dict


class SchemaField:
    """Schema field definition with extraction hints"""

    def __init__(
        self,
        field_type: str,
        required: bool = False,
        description: str = "",
        extraction_hints: list = None,
        extraction_patterns: list = None,
    ):
        self.type = field_type
        self.required = required
        self.description = description
        self.extraction_hints = extraction_hints or []
        self.extraction_patterns = extraction_patterns or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "required": self.required,
            "description": self.description,
            "extraction_hints": self.extraction_hints,
            "extraction_patterns": self.extraction_patterns,
        }


class BaseEventSchema:
    """Base schema for all events"""

    @classmethod
    def get_schema(cls) -> Dict[str, Dict]:
        return {
            "title": SchemaField(
                "string", required=True, description="Event title or name"
            ).to_dict(),
            "date": SchemaField(
                "string", 
                required=True, 
                description="Event date in YYYY-MM-DD format. Look for dates in various formats and convert to YYYY-MM-DD.",
                extraction_hints=["date", "showtime", "screening date", "event date", "calendar", "when", "on", "day"],
                extraction_patterns=[
                    r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",  # MM/DD/YY or MM/DD/YYYY
                    r"\b\d{4}-\d{1,2}-\d{1,2}\b",    # YYYY-MM-DD
                    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b",  # Month DD, YYYY
                    r"\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b",  # Day, Month DD, YYYY
                    r"\b\d{1,2}\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\b",  # DD Month YYYY
                ]
            ).to_dict(),
            "time": SchemaField(
                "string", 
                required=True, 
                description='Event time (e.g., "7:30 PM"). Look for showtimes in buttons, links, or time displays.',
                extraction_hints=["time", "showtime", "screening time", "at", "starts", "begins", "pm", "am"],
                extraction_patterns=[
                    r"\b\d{1,2}:\d{2}\s*[APap][Mm]\b",  # 7:30 PM
                    r"\b\d{1,2}[APap][Mm]\b",           # 7PM
                    r"\b\d{1,2}:\d{2}\b",               # 19:30 (24h format)
                ]
            ).to_dict(),
            "venue": SchemaField(
                "string", required=False, description="Venue or location name"
            ).to_dict(),
            "location": SchemaField(
                "string", required=False, description="Specific location or address"
            ).to_dict(),
            "url": SchemaField(
                "string", required=False, description="Event page URL"
            ).to_dict(),
            "description": SchemaField(
                "string", required=False, description="Event description or details"
            ).to_dict(),
            "type": SchemaField(
                "string",
                required=False,
                description="Event type (film, concert, book_club, etc.)",
            ).to_dict(),
        }


class FilmEventSchema(BaseEventSchema):
    """Schema for film/movie events (AFS, Hyperreal)"""

    @classmethod
    def get_schema(cls) -> Dict[str, Dict]:
        schema = super().get_schema()
        schema.update(
            {
                "full_title": SchemaField(
                    "string",
                    required=False,
                    description="Full event title, including presenter",
                ).to_dict(),
                "presenter": SchemaField(
                    "string",
                    required=False,
                    description="Presenter of the film event",
                ).to_dict(),
                "dates": SchemaField(
                    "array",
                    required=False,
                    description="List of dates for the event",
                ).to_dict(),
                "director": SchemaField(
                    "string",
                    required=False,
                    description="Film director name",
                    extraction_hints=["director", "directed by", "filmmaker"],
                    extraction_patterns=[
                        r"Directed by\s+(.+)",
                        r"Director:\s*(.+)",
                        r"Dir\.\s*(.+)",
                    ],
                ).to_dict(),
                "year": SchemaField(
                    "integer",
                    required=False,
                    description="Film release year",
                    extraction_hints=["year", "release year", "made in"],
                    extraction_patterns=[r"\b(19\d{2}|20\d{2})\b"],
                ).to_dict(),
                "country": SchemaField(
                    "string",
                    required=False,
                    description="Country of origin",
                    extraction_hints=["country", "origin", "made in"],
                    extraction_patterns=[r"([A-Z][a-z]+),\s*\d{4}", r"Country:\s*(.+)"],
                ).to_dict(),
                "language": SchemaField(
                    "string",
                    required=False,
                    description="Film language",
                    extraction_hints=["language", "subtitles", "in language"],
                    extraction_patterns=[
                        r"In\s+([A-Z][a-z]+)\s+with",
                        r"Language:\s*(.+)",
                    ],
                ).to_dict(),
                "duration": SchemaField(
                    "string",
                    required=False,
                    description='Film duration (e.g., "120 min")',
                    extraction_hints=["duration", "runtime", "length"],
                    extraction_patterns=[r"(\d+h?\s*\d*m?i?n?)", r"Runtime:\s*(.+)"],
                ).to_dict(),
                "genre": SchemaField(
                    "array",
                    required=False,
                    description="Film genres",
                    extraction_hints=[
                        "genre",
                        "type",
                        "style",
                        "drama",
                        "comedy",
                        "thriller",
                    ],
                ).to_dict(),
                "is_special_screening": SchemaField(
                    "boolean",
                    required=False,
                    description="Whether this is a special screening",
                    extraction_hints=[
                        "special",
                        "Q&A",
                        "premiere",
                        "35mm",
                        "discussion",
                        "filmmaker present",
                    ],
                ).to_dict(),
                "format": SchemaField(
                    "string",
                    required=False,
                    description="Screening format (35mm, DCP, etc.)",
                    extraction_hints=["format", "35mm", "16mm", "DCP", "digital"],
                    extraction_patterns=[r"\b(35mm|16mm|70mm|DCP|Digital)\b"],
                ).to_dict(),
            }
        )
        schema["type"] = SchemaField(
            "string", required=False, description='Should be "film"'
        ).to_dict()
        return schema


class ConcertEventSchema(BaseEventSchema):
    """Schema for classical music concerts (Symphony, Early Music, La Follia)"""

    @classmethod
    def get_schema(cls) -> Dict[str, Dict]:
        schema = super().get_schema()
        schema.update(
            {
                "composers": SchemaField(
                    "array", required=False, description="List of composer names"
                ).to_dict(),
                "works": SchemaField(
                    "array",
                    required=False,
                    description="List of musical works being performed",
                ).to_dict(),
                "featured_artist": SchemaField(
                    "string", required=False, description="Featured artist or soloist"
                ).to_dict(),
                "conductor": SchemaField(
                    "string", required=False, description="Conductor name"
                ).to_dict(),
                "orchestra": SchemaField(
                    "string", required=False, description="Orchestra or ensemble name"
                ).to_dict(),
                "series": SchemaField(
                    "string", required=False, description="Concert series name"
                ).to_dict(),
                "program": SchemaField(
                    "string", required=False, description="Full program description"
                ).to_dict(),
            }
        )
        schema["type"] = SchemaField(
            "string", required=False, description='Should be "concert"'
        ).to_dict()
        return schema


class BookClubEventSchema(BaseEventSchema):
    """Schema for book club events (Alienated Majesty, First Light)"""

    @classmethod
    def get_schema(cls) -> Dict[str, Dict]:
        schema = super().get_schema()
        schema.update(
            {
                "book": SchemaField(
                    "string",
                    required=True,
                    description="Book title being discussed",
                    extraction_hints=["book title", "reading", "novel", "book"],
                    extraction_patterns=[
                        r'"([^"]+)"',
                        r"Book:\s*(.+)",
                        r"Reading:\s*(.+)",
                    ],
                ).to_dict(),
                "author": SchemaField(
                    "string",
                    required=True,
                    description="Book author name",
                    extraction_hints=["author", "by", "written by", "writer"],
                    extraction_patterns=[
                        r"by\s+([^,\n]+)",
                        r"Author:\s*(.+)",
                        r"Written by\s+(.+)",
                    ],
                ).to_dict(),
                "host": SchemaField(
                    "string",
                    required=False,
                    description="Book club host or facilitator",
                    extraction_hints=["host", "hosted by", "facilitated by", "led by"],
                    extraction_patterns=[
                        r"[Hh]ost(?:ed)?\s*(?:by)?\s*([A-Z][^,\n]+)",
                        r"Led by\s+(.+)",
                    ],
                ).to_dict(),
                "series": SchemaField(
                    "string",
                    required=False,
                    description="Book club series name",
                    extraction_hints=["book club", "series", "group", "circle"],
                    extraction_patterns=[
                        r"([^:]+(?:[Bb]ook [Cc]lub|[Cc]ircle))",
                        r"Series:\s*(.+)",
                    ],
                ).to_dict(),
                "genre": SchemaField(
                    "array",
                    required=False,
                    description="Book genres",
                    extraction_hints=[
                        "fiction",
                        "non-fiction",
                        "memoir",
                        "poetry",
                        "science fiction",
                        "literary fiction",
                    ],
                ).to_dict(),
                "publication_year": SchemaField(
                    "integer",
                    required=False,
                    description="Book publication year",
                    extraction_hints=["published", "year", "copyright"],
                    extraction_patterns=[r"\b(19\d{2}|20\d{2})\b"],
                ).to_dict(),
                "discussion_topics": SchemaField(
                    "array",
                    required=False,
                    description="Discussion topics or themes",
                    extraction_hints=["themes", "topics", "discusses", "explores"],
                ).to_dict(),
                "reading_level": SchemaField(
                    "string",
                    required=False,
                    description="Reading difficulty level",
                    extraction_hints=[
                        "level",
                        "difficulty",
                        "accessible",
                        "challenging",
                    ],
                ).to_dict(),
            }
        )
        schema["type"] = SchemaField(
            "string", required=False, description='Should be "book_club"'
        ).to_dict()
        return schema


class TheaterEventSchema(BaseEventSchema):
    """Schema for theater events (Paramount Theater)"""

    @classmethod
    def get_schema(cls) -> Dict[str, Dict]:
        schema = super().get_schema()
        schema.update(
            {
                "playwright": SchemaField(
                    "string", required=False, description="Playwright name"
                ).to_dict(),
                "director": SchemaField(
                    "string", required=False, description="Director name"
                ).to_dict(),
                "cast": SchemaField(
                    "array", required=False, description="Main cast members"
                ).to_dict(),
                "production_company": SchemaField(
                    "string", required=False, description="Theater company or producer"
                ).to_dict(),
                "genre": SchemaField(
                    "array",
                    required=False,
                    description="Theater genres (drama, comedy, musical, etc.)",
                ).to_dict(),
                "run_dates": SchemaField(
                    "string",
                    required=False,
                    description="Full run dates for the production",
                ).to_dict(),
            }
        )
        schema["type"] = SchemaField(
            "string", required=False, description='Should be "theater"'
        ).to_dict()
        return schema


class GenericEventSchema(BaseEventSchema):
    """Generic schema for miscellaneous events"""

    @classmethod
    def get_schema(cls) -> Dict[str, Dict]:
        schema = super().get_schema()
        schema.update(
            {
                "category": SchemaField(
                    "string", required=False, description="Event category"
                ).to_dict(),
                "organizer": SchemaField(
                    "string", required=False, description="Event organizer"
                ).to_dict(),
                "tags": SchemaField(
                    "array", required=False, description="Event tags or keywords"
                ).to_dict(),
            }
        )
        return schema


class SchemaRegistry:
    """Registry for managing different event schemas"""

    SCHEMAS = {
        "film": FilmEventSchema,
        "concert": ConcertEventSchema,
        "book_club": BookClubEventSchema,
        "theater": TheaterEventSchema,
        "event": GenericEventSchema,
    }

    @classmethod
    def get_schema(cls, event_type: str) -> Dict[str, Dict]:
        """Get schema for a specific event type"""
        event_type = event_type.lower().strip()
        schema_class = cls.SCHEMAS.get(event_type, GenericEventSchema)
        return schema_class.get_schema()

    @classmethod
    def get_available_types(cls) -> list:
        """Get list of available event types"""
        return list(cls.SCHEMAS.keys())

    @classmethod
    def validate_event_data(cls, event_data: Dict, event_type: str) -> Dict[str, Any]:
        """
        Validate event data against schema

        Returns:
            Dict with validation results
        """
        schema = cls.get_schema(event_type)
        errors = []
        warnings = []

        # Check required fields
        for field_name, field_def in schema.items():
            if field_def.get("required", False):
                if field_name not in event_data or not event_data[field_name]:
                    errors.append(f"Required field '{field_name}' is missing or empty")

        # Check field types (basic validation)
        for field_name, value in event_data.items():
            if field_name in schema:
                expected_type = schema[field_name]["type"]

                if expected_type == "string" and not isinstance(value, str):
                    warnings.append(
                        f"Field '{field_name}' should be a string, got {type(value).__name__}"
                    )
                elif expected_type == "integer" and not isinstance(value, int):
                    warnings.append(
                        f"Field '{field_name}' should be an integer, got {type(value).__name__}"
                    )
                elif expected_type == "boolean" and not isinstance(value, bool):
                    warnings.append(
                        f"Field '{field_name}' should be a boolean, got {type(value).__name__}"
                    )
                elif expected_type == "array" and not isinstance(value, list):
                    warnings.append(
                        f"Field '{field_name}' should be an array, got {type(value).__name__}"
                    )

        return {
            "is_valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "schema_used": event_type,
        }


# Venue-specific schema mappings
VENUE_SCHEMAS = {
    "AFS": "film",
    "Hyperreal": "film",
    "Symphony": "concert",
    "EarlyMusic": "concert",
    "LaFollia": "concert",
    "AlienatedMajesty": "book_club",
    "FirstLight": "book_club",
    "Paramount": "film",
    "NewYorkerMeetup": "book_club",
}


def get_venue_schema(venue_name: str) -> Dict[str, Dict]:
    """Get appropriate schema for a venue"""
    schema_type = VENUE_SCHEMAS.get(venue_name, "generic")
    return SchemaRegistry.get_schema(schema_type)


def get_schema_for_venue_type(venue_type: str) -> Dict[str, Dict]:
    """Get schema for a venue type (for new venues)"""
    return SchemaRegistry.get_schema(venue_type)
