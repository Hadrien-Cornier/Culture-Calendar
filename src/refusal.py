"""Refusal detection and substitution for LLM-generated descriptions.

Separated from processor.py so tests and callers (summary_generator,
verify_calendar) can import without pulling in the full EventProcessor
dependency graph (requests, dotenv, wikipedia/letterboxd sources, etc.).
"""

import re

REFUSAL_STUB = (
    "No public information available for this event yet. "
    "Check the venue page for details."
)

REFUSAL_PATTERNS = (
    r"i cannot provide",
    r"i cannot create",
    r"i cannot verify",
    r"i (cannot|can'?t) locate",
    r"i'?m unable to",
    r"do(es)? not contain (any |relevant |specific )?information",
    r"search results (do not|provided do not)",
    r"would be speculative",
    r"speculative rather than",
    r"speculative criticism",
    r"without substantive information",
    r"lack(s)? the substantive detail",
    r"without specific (recordings|reviews|program information|sources|information)",
    r"insufficient (information|context|sources|data)",
    r"i (do not|don'?t) have (access to |sufficient |enough )",
    r"i appreciate your request, but i (must be direct|cannot)",
    r"following this instruction would require me to generate speculative",
)
_REFUSAL_RE = re.compile("|".join(REFUSAL_PATTERNS), re.IGNORECASE)


def is_refusal_response(text: str) -> bool:
    """Heuristic: does this look like an LLM refusing to write a real review?

    Empty or very short text is NOT considered a refusal here — that's a
    separate condition handled by other gates in verify_calendar.py. Only
    verbose refusal-shaped prose triggers this detector.
    """
    if not text or len(text.strip()) < 40:
        return False
    return bool(_REFUSAL_RE.search(text))


def filter_refusal(text: str) -> str:
    """Return the canonical refusal stub if text looks like an LLM refusal.

    Empty input passes through unchanged (empty description is a separate
    failure mode). Legitimate reviews are returned unchanged.
    """
    if not text:
        return text
    if is_refusal_response(text):
        return REFUSAL_STUB
    return text


# Fields on an event that can carry LLM-generated text and therefore need
# refusal filtering. Kept as a module constant so callers (data-cleanup
# scripts, test fixtures, verify_calendar) share the same invariant.
REFUSAL_SENSITIVE_FIELDS: tuple[str, ...] = ("description", "one_liner_summary")


def clean_event_refusals(event: dict) -> tuple[dict, list[str]]:
    """Return (cleaned_event, changed_fields).

    Walks every refusal-sensitive field on the event; substitutes the
    canonical stub where the content matches the refusal regex. This
    fixes the 04-18 leak where the T2.4 cleanup only checked
    `description` and missed refusal-shaped `one_liner_summary`.

    The returned event is a shallow copy; the input is not mutated.
    """
    cleaned = dict(event)
    changed: list[str] = []
    for field in REFUSAL_SENSITIVE_FIELDS:
        original = cleaned.get(field) or ""
        if original and is_refusal_response(original):
            cleaned[field] = REFUSAL_STUB
            changed.append(field)
    return cleaned, changed
