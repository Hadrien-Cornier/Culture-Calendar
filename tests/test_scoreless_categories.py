"""Structural tests for the no-score presentation of non-film categories.

Background: the 0-10 AI rating only carries signal for film. Measured across
the published corpus, film reviews decline to judge 19% of the time and the
scores use the whole 0-10 range; concert declines 73% of the time and visual
arts 56%, both clustered flat around 3.4. In those categories the model is
scoring how much material it could find, not how good the work is - a gallery
show described only by title and venue scores low whatever is on the walls.

So the site shows no score there, and must not reintroduce one: not as a badge,
not as a fabricated venue-average fallback, and not as a "top picks" ranking
claim over an unranked list.

Same no-dependency structural strategy as test_venue_card_rendering: the
relevant function bodies are brace-matched out of docs/script.js.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "docs" / "script.js"
STYLES_PATH = REPO_ROOT / "docs" / "styles.css"


def _extract_function_body(source: str, signature: str) -> str:
    idx = source.index(signature)
    open_brace = source.index("{", idx)
    depth = 0
    for i in range(open_brace, len(source)):
        ch = source[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return source[open_brace : i + 1]
    raise AssertionError(f"unterminated function body for {signature!r}")


@pytest.fixture(scope="module")
def script_source() -> str:
    return SCRIPT_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def css_source() -> str:
    return STYLES_PATH.read_text(encoding="utf-8")


# --- which categories are scored -----------------------------------------


@pytest.mark.unit
def test_only_film_is_scored(script_source: str) -> None:
    """Film is the sole scored category. Adding another needs the evidence."""
    match = re.search(r"var SCORED_CATEGORIES\s*=\s*\{([^}]*)\}", script_source)
    assert match, "SCORED_CATEGORIES must be declared"
    keys = re.findall(r"(\w+)\s*:", match.group(1))
    assert keys == ["movie"], f"expected only 'movie' to be scored, got {keys}"


@pytest.mark.unit
def test_is_scored_helper_exists(script_source: str) -> None:
    assert "function isScored(" in script_source


# --- the badge -----------------------------------------------------------


@pytest.mark.unit
def test_badge_is_gated_on_is_scored(script_source: str) -> None:
    """The rating badge must not render for an unscored category."""
    body = _extract_function_body(script_source, "function appendRatingBadge")
    assert re.search(
        r"if\s*\(\s*!\s*isScored\(ev\)\s*\)\s*return", body
    ), "appendRatingBadge must bail out early for unscored events"


@pytest.mark.unit
@pytest.mark.parametrize("builder", ["buildPickCard", "buildListingCard"])
def test_card_builders_do_not_inline_a_badge(script_source: str, builder: str) -> None:
    """Both card faces must go through the gated helper.

    Guards the specific regression this replaced: each builder used to inline
    `ev.rating > 0 ? ev.rating : (ev._derivedRating || 5)` and always append a
    badge, so an unscored event displayed a fabricated 5.
    """
    body = _extract_function_body(script_source, "function " + builder)
    assert "appendRatingBadge(" in body, f"{builder} must use appendRatingBadge"
    assert "event-rating-badge" not in body, (
        f"{builder} must not build a badge inline; that path skips the isScored gate"
    )


# --- no fabricated ratings ----------------------------------------------


@pytest.mark.unit
def test_derived_rating_only_applies_to_scored_categories(script_source: str) -> None:
    """The venue-average fallback must never reach an unscored event.

    Inventing a number for a gallery show puts a fabricated value in exactly
    the place a real judgement goes, which is worse than showing nothing.
    """
    body = _extract_function_body(script_source, "function renderAll")
    assert re.search(
        r"isScored\(ev\)\s*&&[\s\S]{0,120}?_derivedRating\s*=\s*derivedRating", body
    ), "renderAll must gate derivedRating on isScored"


# --- ordering ------------------------------------------------------------


@pytest.mark.unit
def test_unscored_events_sort_by_urgency(script_source: str) -> None:
    """Unscored events order by date, not by a rating they do not have."""
    body = _extract_function_body(script_source, "function groupEvents")
    assert "urgencyDate(" in body, "groupEvents must sort unscored events by urgencyDate"
    assert "isScored(" in body, "groupEvents must branch on whether a category is scored"


@pytest.mark.unit
def test_urgency_prefers_end_date_for_a_running_show(script_source: str) -> None:
    """A months-long exhibition is urgent when it closes, not when it opened."""
    body = _extract_function_body(script_source, "function urgencyDate")
    assert re.search(
        r"first\s*<=\s*today[\s\S]{0,60}?return\s+end", body
    ), "urgencyDate must return the closing date for a show already open"


# --- ranking claims ------------------------------------------------------


@pytest.mark.unit
def test_picks_heading_drops_the_ranking_claim(script_source: str) -> None:
    """"Top picks" is a ranking claim; an unranked list must not make it."""
    body = _extract_function_body(script_source, "function renderPicks")
    assert "TOP PICKS OF THE WEEK" in body and "ON THIS WEEK" in body, (
        "renderPicks must swap the heading when nothing in the list is scored"
    )
    assert "isScored" in body


@pytest.mark.unit
def test_rank_counter_hidden_for_unscored_picks(css_source: str) -> None:
    """A big '1' beside the first item reads as 'best'."""
    assert re.search(
        r"\.event-card-unscored\s+\.event-header::before\s*\{\s*content:\s*none",
        css_source,
    ), "the pick rank counter must be suppressed on unscored cards"


# --- layout --------------------------------------------------------------


@pytest.mark.unit
def test_unscored_card_reclaims_the_rating_column(css_source: str) -> None:
    """Without this the title is squeezed into the vacated badge column."""
    assert ".event-card-unscored .event-header" in css_source
    assert re.search(
        r"\.picks-list\.top-picks \.event-card\.event-card-unscored \.event-header\s*\{",
        css_source,
    ), "the picks variant needs its own grid override to beat the base rule"


@pytest.mark.unit
def test_run_note_style_exists(css_source: str) -> None:
    assert re.search(r"\.event-run-note\s*\{", css_source)
    assert re.search(r"\.event-run-note\.is-closing-soon\s*\{", css_source)


# --- non-judgement suppression -------------------------------------------


@pytest.mark.unit
def test_non_judgement_detector_exists(script_source: str) -> None:
    assert "NON_JUDGEMENT_RE" in script_source
    assert "function isNonJudgement(" in script_source


@pytest.mark.unit
@pytest.mark.parametrize(
    "phrase",
    [
        "There is not enough evidence in the supplied material to judge composition",
        "I cannot assess composition, materials, technique, or installation",
        "The available information does not describe the actual works",
        "no basis for crediting composition or technique",
        "the provided sources do not include an exhibition description",
        "its cultural significance is limited by the thin public record",
        "the exhibition remains undocumented rather than conceptually legible",
        "I cannot fairly credit originality from the available record",
    ],
)
def test_detector_matches_real_non_judgements(script_source: str, phrase: str) -> None:
    """Every phrase here was published on the live site under a critic heading."""
    match = re.search(r"var NON_JUDGEMENT_RE = new RegExp\(\[([\s\S]*?)\]\.join", script_source)
    assert match, "NON_JUDGEMENT_RE must be a joined list of alternatives"
    alternatives = re.findall(r'"((?:[^"\\]|\\.)*)"', match.group(1))
    pattern = re.compile("|".join(alternatives).replace("\\\\b", "\\b"), re.IGNORECASE)
    assert pattern.search(phrase), f"detector must catch: {phrase!r}"


@pytest.mark.unit
@pytest.mark.parametrize(
    "phrase",
    [
        "A juried survey of contemporary printmaking, and that is its strength.",
        "Treviño draws from her experience as a mother, interrogating media narratives.",
        "The exhibition is a juried PrintAustin show, so its value lies in the friction.",
    ],
)
def test_detector_leaves_real_criticism_alone(script_source: str, phrase: str) -> None:
    """A genuine review must survive - this filter removes content."""
    match = re.search(r"var NON_JUDGEMENT_RE = new RegExp\(\[([\s\S]*?)\]\.join", script_source)
    alternatives = re.findall(r'"((?:[^"\\]|\\.)*)"', match.group(1))
    pattern = re.compile("|".join(alternatives).replace("\\\\b", "\\b"), re.IGNORECASE)
    assert not pattern.search(phrase), f"detector must not swallow real criticism: {phrase!r}"


@pytest.mark.unit
def test_one_liner_is_filtered_too(script_source: str) -> None:
    """The hook is generated from the same thin material as the review."""
    assert re.search(
        r"if\s*\(ev\.one_liner\s*&&\s*!isNonJudgement\(ev\.one_liner\)\)", script_source
    ), "the one-liner must be suppressed when it is itself a non-judgement"
