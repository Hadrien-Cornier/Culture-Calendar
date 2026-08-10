"""Generic, config-driven scraper for venues that publish to a live website.

Every live-scraped venue in this repo used to cost a bespoke ``BaseScraper``
subclass plus six registration edits spread across four files. For a long tail
of small galleries and museums - which all publish the same shape of listing,
just with different markup - that is pure duplication, and the duplication
drifts (``_VENUE_CODE_TO_CONFIG_KEY`` had already lost two venues).

This class collapses that into one implementation driven entirely by a
``web_llm_scrapers:`` entry in ``config/master_config.yaml``. Adding a venue is
a YAML edit; no Python changes, no new file, no registration.

It deliberately owns no venue-specific knowledge. The *what to extract* comes
from :meth:`ConfigLoader.get_extraction_schema`, which already merges a
template's ``field_definitions`` with per-venue ``extraction.batch_description``
and ``field_overrides``. That machinery pre-dates this class and was previously
called by only two hand-written scrapers; here it becomes the general path.

Three fetch modes, chosen per venue in config:

- ``http`` (default) - plain ``requests`` through the session
  :class:`BaseScraper` already fits with browser-ish headers. Right for most
  sites.
- ``playwright`` - headless Chromium render, for listings built client-side.
  Must run on the serial scrape path (``signal only works in main thread``;
  see ``CLAUDE.md §Known Issues``).
- ``perplexity`` - never fetches the page at all; asks Perplexity to read the
  domain. The escape hatch for sites that return 403 to scrapers, which is how
  ``art_austin_scraper`` already copes and what The Contemporary Austin needs.

Escalating a venue from ``http`` to ``playwright`` or ``perplexity`` is a
one-line config flip, not a code change.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from src.base_scraper import BaseScraper

#: Fetch strategies a ``web_llm_scrapers:`` entry may declare.
FETCH_MODES = ("http", "playwright", "perplexity")

#: Markup that never carries event content. Stripped before the LLM sees the
#: page so the token budget goes to listings rather than chrome.
_BOILERPLATE_TAGS = (
    "script",
    "style",
    "noscript",
    "nav",
    "footer",
    "header",
    "form",
    "svg",
    "iframe",
)

#: Extraction quality falls off well before the context limit, and gallery
#: pages are mostly navigation. Matches the cap alienated_majesty settled on.
_MAX_CONTENT_CHARS = 6000

_DEFAULT_TIMEOUT_SECONDS = 20

#: Template fields that no scraper can observe on a page - the pipeline
#: produces them later (EventProcessor writes `rating`/`description`/
#: `review_confidence`, SummaryGenerator writes `one_liner_summary`, and
#: `screenings` is derived from dates/times when the site data is built).
#:
#: They appear in a template's `required_on_publish` because they must exist by
#: the time an event ships, which get_extraction_schema turns into
#: `required: true` on the *extraction* schema. Asking an extractor for them
#: invites invented ratings and fabricated criticism, so they are stripped
#: here. Extraction-required and publish-required are different questions.
_PIPELINE_DERIVED_FIELDS = frozenset(
    {
        "rating",
        "review_confidence",
        "one_liner_summary",
        "description",
        "screenings",
    }
)


#: "7:00 PM - 10:00 PM", "7pm", "18:00", "2:00 PM" - the start time is the
#: leading clock reading, and the meridiem may trail the range rather than the
#: number it belongs to ("6-8 pm").
_TIME_RE = re.compile(
    r"(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<meridiem>am|pm)?",
    re.IGNORECASE,
)
_TRAILING_MERIDIEM_RE = re.compile(r"(am|pm)", re.IGNORECASE)
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")

#: Leading date of a value that may be partial ("2022-09") or a range
#: ("2021-04 to 2021-05"). Archive pages produce both.
_PARTIAL_DATE_RE = re.compile(r"^\s*(?P<year>\d{4})-(?P<month>\d{2})(?:-(?P<day>\d{2}))?")

#: Every date token in a value, so a packed range yields both of its ends.
_DATE_TOKEN_RE = re.compile(r"\d{4}-\d{2}(?:-\d{2})?")

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
#: "July 18", "Aug. 29", "September 12" - a month name followed by a day.
_MONTH_DAY_RE = re.compile(
    r"(?P<month>jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(?P<day>\d{1,2})",
    re.IGNORECASE,
)
_YEAR_RE = re.compile(r"\b(20\d{2})\b")


def _as_list(value: Any) -> List[str]:
    """Coerce a scalar-or-list LLM field into a list, dropping empties."""
    if value is None:
        return []
    if not isinstance(value, list):
        value = [value]
    return [v for v in value if v]


def _normalize_date(value: Any) -> Optional[str]:
    """Reduce a date expression to ``YYYY-MM-DD``.

    Archive listings hand back month-precision dates ("2022-09") and ranges
    ("2021-04 to 2021-05"). ``validate_event`` requires a full ISO date, so
    those used to fail validation *and* slip past the past-event filter, which
    is how a gallery's entire back catalogue arrived as invalid events. A
    month with no day is treated as its first; a range is read from its start.
    Returns ``None`` when nothing date-like is there.
    """
    if value is None:
        return None
    match = _PARTIAL_DATE_RE.match(str(value))
    if not match:
        return None
    year, month = int(match.group("year")), int(match.group("month"))
    day = int(match.group("day") or 1)
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


#: A year-less date is assumed to be the coming one. Anything further into the
#: past than this rolls forward, so "Jan 15" read in December means next
#: January. Wide enough that a genuinely recent date still resolves backwards
#: and gets filtered as finished.
_YEARLESS_GRACE_DAYS = 60


def _split_date_range(value: Any, today: Optional[date] = None) -> tuple:
    """Split a value into its start and end dates.

    Exhibition listings show a run, and extractors often pack the whole thing
    into one string - ``"dates": "2026-07-18 to 2026-08-29"`` - instead of
    filling ``end_date``. Reading only the leading date there makes a show
    that is currently on view look like it closed on opening day, which is how
    Martha's current exhibition was being dropped. Returns
    ``(start, end)``; ``end`` is ``None`` unless the value really held a range.
    """
    if value is None:
        return None, None
    text = str(value)
    tokens = _DATE_TOKEN_RE.findall(text)
    if tokens:
        start = _normalize_date(tokens[0])
        end = _normalize_date(tokens[-1]) if len(tokens) > 1 else None
        return start, end
    return _parse_human_date_range(text, today)


def _parse_human_date_range(text: str, today: Optional[date] = None) -> tuple:
    """Parse a month-name range like "July 18 - August 29, 2026".

    Extractors ignore the schema's ISO instruction whenever the page states
    dates in prose, which gallery listings almost always do. Without this the
    value is unparseable and a real, current exhibition is dropped.

    The year is taken from the string and applied to both ends; when the end
    falls before the start the range crosses New Year, so the end rolls
    forward ("December 12 - January 15, 2026").
    """
    matches = _MONTH_DAY_RE.findall(text)
    if not matches:
        return None, None

    year_match = _YEAR_RE.search(text)
    if year_match:
        year = int(year_match.group(1))
    else:
        # Event feeds routinely omit the year ("Fri, Aug 14") because it is
        # obvious in context. Requiring one dropped those outright, which is
        # what left the Umlauf feed empty. Infer the coming occurrence.
        year = _infer_year(matches[0], today or date.today())
        if year is None:
            return None, None

    def _build(month_token: str, day_token: str, in_year: int) -> Optional[str]:
        month = _MONTHS.get(month_token[:3].lower())
        if not month:
            return None
        try:
            return date(in_year, month, int(day_token)).isoformat()
        except ValueError:
            return None

    start = _build(*matches[0], year)
    if not start:
        return None, None
    if len(matches) == 1:
        return start, None

    end = _build(*matches[-1], year)
    if end and end < start:
        end = _build(*matches[-1], year + 1)
    return start, end


def _any_date_field(event: Dict[str, Any]) -> Any:
    """Last-resort search for whichever key the extractor put the dates in.

    Enumerating aliases does not converge: the same page yielded ``dates``,
    then ``start_date``, then ``run_dates`` across three runs. Rather than grow
    that list forever, fall back to any key that mentions a date - excluding
    ``end_date``, which is the close, not the start.
    """
    for key, value in event.items():
        lowered = key.lower()
        if "date" in lowered and lowered != "end_date" and value:
            return value
    return None


def _infer_year(month_day: tuple, today: date) -> Optional[int]:
    """Pick the year for a year-less "Month Day", rolling forward if needed."""
    month = _MONTHS.get(str(month_day[0])[:3].lower())
    if not month:
        return None
    try:
        candidate = date(today.year, month, int(month_day[1]))
    except ValueError:
        return None
    if candidate < today - timedelta(days=_YEARLESS_GRACE_DAYS):
        return today.year + 1
    return today.year


def _normalize_time(value: Any) -> Optional[str]:
    """Reduce a human time expression to 24-hour ``HH:MM``.

    Extractors return whatever the page said - "7:00 PM - 10:00 PM", "6-8 pm",
    "2 PM". ``validate_event`` rejects anything that is not ``HH:MM`` outright,
    so an un-normalized range silently costs the whole event. Takes the start
    of a range; returns ``None`` when nothing clock-like is there.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text or _ISO_DATE_RE.match(text):
        # Guard against a date landing in the times field: "2026-08-14" would
        # otherwise read as hour 20.
        return None

    match = _TIME_RE.search(text)
    if not match:
        return None

    hour = int(match.group("hour"))
    minute = int(match.group("minute") or 0)
    meridiem = match.group("meridiem")
    if meridiem is None:
        # "6-8 pm" - the meridiem sits after the range, not after the start.
        trailing = _TRAILING_MERIDIEM_RE.search(text[match.end() :])
        meridiem = trailing.group(1) if trailing else None

    if meridiem:
        meridiem = meridiem.lower()
        if meridiem == "pm" and hour != 12:
            hour += 12
        elif meridiem == "am" and hour == 12:
            hour = 0

    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return f"{hour:02d}:{minute:02d}"


class WebLlmScraper(BaseScraper):
    """Scrape a live venue site into standardized events via LLM extraction."""

    def __init__(
        self,
        *,
        base_url: str,
        venue_name: str,
        urls: List[str],
        venue_key: Optional[str] = None,
        config: Optional[Any] = None,
        fetch: str = "http",
        default_event_type: str = "visual_arts",
        default_time: str = "12:00",
        preserve_venue_name: bool = False,
        max_content_chars: int = _MAX_CONTENT_CHARS,
        timeout: int = _DEFAULT_TIMEOUT_SECONDS,
        today: Optional[date] = None,
    ):
        super().__init__(
            base_url=base_url,
            venue_name=venue_name,
            venue_key=venue_key,
            config=config,
        )
        if fetch not in FETCH_MODES:
            raise ValueError(
                f"Unknown fetch mode {fetch!r} for venue {venue_key!r}; "
                f"expected one of {', '.join(FETCH_MODES)}"
            )
        if not urls:
            raise ValueError(f"web_llm_scrapers entry {venue_key!r} declares no urls")

        self.urls = list(urls)
        self.fetch = fetch
        self.default_event_type = default_event_type
        self.default_time = default_time
        self.preserve_venue_name = preserve_venue_name
        self.max_content_chars = max_content_chars
        self.timeout = timeout
        self._today_override = today

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    def get_target_urls(self) -> List[str]:
        """Absolute listing URLs. Config may hold paths or full URLs."""
        return [urljoin(self.base_url, u) for u in self.urls]

    def _today(self) -> date:
        """Today's date, overridable so date-sensitive tests cannot rot."""
        return self._today_override or date.today()

    def _resolve_event_type(self) -> str:
        """Prefer the venue's declared category; fall back to registry default."""
        if self.config is not None and self.venue_key:
            from_config = self.config.get_assumed_event_category(self.venue_key)
            if from_config:
                return from_config
        return self.default_event_type

    # ------------------------------------------------------------------
    # Fetching
    # ------------------------------------------------------------------

    def _fetch_http(self, url: str) -> str:
        """GET the page. Returns "" on any failure so one dead URL is survivable."""
        try:
            response = self.session.get(url, timeout=self.timeout)
            if response.status_code != 200:
                print(f"  {self.venue_name}: {url} returned {response.status_code}")
                return ""
            return response.text
        except Exception as exc:
            print(f"  {self.venue_name}: fetch failed for {url}: {exc}")
            return ""

    def _render_with_playwright(self, url: str) -> str:
        """Render the URL with headless Chromium and return post-JS HTML.

        Returns "" on failure (including playwright not being installed) so
        callers degrade instead of raising. Playwright's sync API manages its
        own event loop, so this is safe inside MultiVenueScraper's serial loop.
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            print("  playwright not installed; cannot render JS-heavy page")
            return ""

        try:
            print(f"  Launching Playwright for {url}")
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                try:
                    page = browser.new_page(
                        user_agent=(
                            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/120.0.0.0 Safari/537.36"
                        )
                    )
                    page.goto(url, wait_until="networkidle", timeout=30000)
                    return page.content()
                finally:
                    browser.close()
        except Exception as exc:
            print(f"  Playwright error for {url}: {exc}")
            return ""

    def _simplify_html(self, html: str) -> str:
        """Strip boilerplate markup down to the text an extractor needs."""
        if not html:
            return ""
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(list(_BOILERPLATE_TAGS)):
            tag.decompose()

        main = soup.find("main") or soup.find("article") or soup.body or soup
        text = main.get_text(separator=" | ", strip=True)
        if len(text) > self.max_content_chars:
            text = text[: self.max_content_chars] + "..."
        return text

    # ------------------------------------------------------------------
    # Extraction
    # ------------------------------------------------------------------

    def _extraction_schema(self) -> Dict[str, Any]:
        """Config-driven schema for this venue's event template."""
        return self.config.get_extraction_schema(
            self.venue_key, self._resolve_event_type()
        )

    def _extraction_fields(self) -> Dict[str, Any]:
        """The observable fields, i.e. everything the pipeline does not derive."""
        return {
            name: spec
            for name, spec in self._extraction_schema().get("fields", {}).items()
            if name not in _PIPELINE_DERIVED_FIELDS
        }

    def _llm_schema(self) -> Dict[str, Any]:
        """Shape :meth:`_extraction_schema` into the array form extract_data wants."""
        schema = self._extraction_schema()
        items = self._extraction_fields()
        return {
            "events": {
                "type": "array",
                "description": schema.get(
                    "batch_description", "List of events extracted from the webpage."
                ),
                "items": items,
            }
        }

    def _extract_from_content(self, content: str, url: str) -> List[Dict]:
        """Run the LLM extraction over already-fetched page text."""
        if not content:
            return []

        result = self.llm_service.extract_data(
            content=content,
            schema=self._llm_schema(),
            url=url,
            content_type="text",
            # Gallery archive pages routinely list 20-40 exhibitions; the
            # default 2000-token budget truncates the response mid-array.
            max_tokens=4000,
        )
        if not result.get("success"):
            print(
                f"  {self.venue_name}: extraction failed for {url}: "
                f"{result.get('error', 'unknown error')}"
            )
            return []
        return result.get("data", {}).get("events", []) or []

    def _perplexity_prompt(self) -> str:
        """Prompt for the no-fetch mode, built from the same config schema.

        Keeps the ``perplexity`` mode as config-driven as the HTML modes: the
        field list and per-venue guidance come from master_config, not from a
        prompt hardcoded here.
        """
        schema = self._extraction_schema()
        field_lines = "\n".join(
            f"- {name}: {spec.get('description', '')}".rstrip()
            for name, spec in self._extraction_fields().items()
        )
        domain = urlparse(self.base_url).netloc
        listing_urls = "\n".join(f"  {u}" for u in self.get_target_urls())

        return f"""Search {domain} for ALL current and upcoming events at {self.venue_name} in Austin, Texas.

Today is {self._today().strftime('%B %d, %Y')}. Only include events happening today or later.

{schema.get('batch_description', '')}

Start from these listing pages:
{listing_urls}

For each event, extract these fields:
{field_lines}

Return ONLY valid JSON of the form {{"events": [ {{...}} ]}}.

Important:
- Include ALL events you find, not just the first few.
- Dates must be YYYY-MM-DD and times must be 24-hour HH:MM.
- `dates` and `times` are parallel arrays: one time per date, in the same order.
- Skip events that have already passed.
"""

    def _extract_via_perplexity(self) -> List[Dict]:
        """Ask Perplexity to read the domain; never fetches the page directly."""
        domain = urlparse(self.base_url).netloc
        try:
            result = self.llm_service.call_perplexity(
                self._perplexity_prompt(),
                search_domain_filter=[domain],
            )
        except Exception as exc:
            print(f"  {self.venue_name}: Perplexity call failed: {exc}")
            return []

        if not result:
            print(f"  {self.venue_name}: Perplexity returned no results")
            return []
        return result.get("events", []) or []

    # ------------------------------------------------------------------
    # Standardization
    # ------------------------------------------------------------------

    def _has_finished(self, dates: List[str], end_date: Optional[str]) -> bool:
        """Has this event already ended?

        Gallery sites list their whole back catalogue on the same page as the
        current show, so without this the calendar fills with exhibitions that
        closed years ago. An exhibition runs over a range, so ``end_date`` is
        what decides it when present; one-off events fall back to their latest
        date. An unparseable date is kept rather than dropped - better a stray
        event than silently losing a real one to a format we did not expect.
        """
        today = self._today()
        for candidate in (end_date, max(dates) if dates else None):
            if not candidate:
                continue
            try:
                return date.fromisoformat(str(candidate)[:10]) < today
            except ValueError:
                continue
        return False

    def _standardize(self, event: Dict, url: str) -> Optional[Dict]:
        """Apply config defaults and normalize into the pipeline event shape.

        Returns ``None`` for events the LLM returned without the minimum a
        calendar entry needs (a title and at least one date), rather than
        letting a half-event through to fail validation later.
        """
        out = dict(
            self.config.apply_default_values(event, self.venue_key)
            if self.config
            else event
        )

        title = (out.get("title") or "").strip()
        if not title:
            return None
        out["title"] = title

        # Extractors reliably drift away from the schema's key names toward
        # whatever reads naturally for the page: `date`/`time` instead of the
        # arrays we asked for, and `start_date` whenever the listing shows a
        # run ("September 12 - October 11, 2026"). Each of those was a
        # complete, correct event being silently dropped, so accept the
        # aliases rather than insisting on the schema's spelling.
        raw_dates = _as_list(
            out.get("dates") or out.get("date") or out.get("start_date")
        ) or _as_list(_any_date_field(out))
        dates: List[str] = []
        range_ends: List[str] = []
        for value in raw_dates:
            start, end = _split_date_range(value, self._today())
            if not start:
                continue
            dates.append(start)
            if end:
                range_ends.append(end)
        if not dates:
            return None
        raw_times = _as_list(out.get("times") or out.get("time"))
        times = [t for t in (_normalize_time(v) for v in raw_times) if t]
        for alias in ("date", "time", "start_date"):
            out.pop(alias, None)
        # dates/times are zipped pairwise downstream and BaseScraper.format_event
        # rejects a length mismatch outright, so pad or trim to match.
        if len(times) < len(dates):
            times = times + [self.default_time] * (len(dates) - len(times))
        elif len(times) > len(dates):
            times = times[: len(dates)]

        end_date = _normalize_date(out.get("end_date")) or (
            max(range_ends) if range_ends else None
        )
        if self._has_finished(dates, end_date):
            return None
        if end_date:
            out["end_date"] = end_date

        out["dates"] = dates
        out["times"] = times
        out["type"] = self._resolve_event_type()
        out["venue"] = (out.get("venue") or self.venue_name) if self.preserve_venue_name else self.venue_name
        if not out.get("url"):
            out["url"] = url
        return out

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def scrape_events(self) -> List[Dict]:
        """Scrape every configured listing URL into standardized events."""
        if self.llm_service is None or self.llm_service.provider is None:
            print(f"  {self.venue_name}: no LLM provider configured; skipping")
            return []

        raw: List[tuple] = []
        if self.fetch == "perplexity":
            listing_url = self.get_target_urls()[0]
            raw = [(evt, listing_url) for evt in self._extract_via_perplexity()]
        else:
            for url in self.get_target_urls():
                html = (
                    self._render_with_playwright(url)
                    if self.fetch == "playwright"
                    else self._fetch_http(url)
                )
                content = self._simplify_html(html)
                raw.extend((evt, url) for evt in self._extract_from_content(content, url))

        events: List[Dict] = []
        seen = set()
        for evt, url in raw:
            standardized = self._standardize(evt, url)
            if not standardized:
                continue
            # One exhibition often appears on both /exhibitions and /events.
            key = (standardized["title"].lower(), standardized["dates"][0])
            if key in seen:
                continue
            seen.add(key)
            events.append(standardized)

        print(f"  {self.venue_name}: {len(events)} events via {self.fetch}")
        return events
