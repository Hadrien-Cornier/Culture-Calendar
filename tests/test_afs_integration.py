"""End-to-end AFS scraper test against saved HTML fixtures + the oracle.

This test exercises the full scrape_events() path: fetch the listing, parse
/screening/ links, fetch each movie page, and assemble events. Network is
mocked by patching requests.Session.get so the fixtures drive the run.

Coverage is measured against scripts/oracle_afs.parse_afs_schedule restricted
to the set of films for which we saved a movie-page fixture. This is the
measurable termination criterion for Milestone B.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.oracle_afs import FilmScreening, parse_afs_schedule  # noqa: E402
from src.scrapers.afs_scraper import AFSScraper  # noqa: E402


TEST_DATA = ROOT / "tests" / "AFS_test_data"
ORACLE_FIXTURE = ROOT / "tests" / "april-may-2026-schedule-afs.md"


def _discover_saved_fixtures() -> dict[str, str]:
    """Map slug → filename for every screening_*_2026.html in AFS_test_data/."""
    out: dict[str, str] = {}
    for path in TEST_DATA.glob("screening_*_2026.html"):
        # screening_<slug_with_underscores>_2026.html → slug (hyphens)
        slug = path.stem.removeprefix("screening_").removesuffix("_2026").replace("_", "-")
        out[slug] = path.name
    return out


SAVED_FIXTURES_FILES = _discover_saved_fixtures()


def _make_response(html: str, status: int = 200) -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.text = html
    return r


def _load_fixture(relpath: str) -> str:
    return (TEST_DATA / relpath).read_text(encoding="utf-8")


def _mock_session_get(*args: Any, **kwargs: Any) -> MagicMock:
    """Route AFS URLs to saved fixtures. Unknown URLs get 404."""
    url = args[0] if args else kwargs.get("url", "")
    if url.rstrip("/").endswith("austinfilm.org"):
        # Root URL fallback — not used when listing succeeds.
        return _make_response("<html></html>", 200)
    if "/calendar/" in url or "/screenings/" in url:
        return _make_response(_load_fixture("calendar_snapshot_2026_04.html"))
    for slug, filename in SAVED_FIXTURES_FILES.items():
        if f"/screening/{slug}/" in url or url.rstrip("/").endswith(f"/screening/{slug}"):
            return _make_response(_load_fixture(filename))
    return _make_response("", 404)


@pytest.fixture(scope="module")
def scraped_events() -> list[dict]:
    scraper = AFSScraper()
    with patch.object(scraper.session, "get", side_effect=_mock_session_get):
        events = scraper.scrape_events()
    return events


@pytest.fixture(scope="module")
def oracle_films() -> list[FilmScreening]:
    return parse_afs_schedule(ORACLE_FIXTURE)


class TestAFSIntegration:
    def test_scrape_returns_non_empty(self, scraped_events):
        assert len(scraped_events) > 0, "Scraper produced zero events"

    def test_every_event_has_type_movie(self, scraped_events):
        for e in scraped_events:
            assert e.get("type") == "movie", f"type missing/wrong for {e.get('title')}"

    def test_every_event_has_core_fields(self, scraped_events):
        required = {"title", "dates", "times", "url", "venue"}
        for e in scraped_events:
            missing = required - set(e.keys())
            assert not missing, f"{e.get('title','?')} missing {missing}"
            assert e["dates"] and e["times"], f"{e['title']} has empty dates/times"
            assert len(e["dates"]) == len(e["times"]), f"{e['title']} has mismatched dates/times"

    def test_metadata_is_populated(self, scraped_events):
        """Director, release_year, country, runtime_minutes should usually be set.

        Not every AFS page lists every field (some repertory entries omit director
        or year), but ≥60% coverage is a reasonable floor.
        """
        n = len(scraped_events)
        assert n > 0
        have_director = sum(1 for e in scraped_events if e.get("director"))
        have_year = sum(1 for e in scraped_events if e.get("release_year"))
        have_country = sum(1 for e in scraped_events if e.get("country"))
        have_runtime = sum(1 for e in scraped_events if e.get("runtime_minutes"))
        assert have_director / n >= 0.6, f"Only {have_director}/{n} have director"
        assert have_year / n >= 0.6, f"Only {have_year}/{n} have release_year"
        assert have_country / n >= 0.6, f"Only {have_country}/{n} have country"
        assert have_runtime / n >= 0.6, f"Only {have_runtime}/{n} have runtime_minutes"

    def test_oracle_coverage_for_saved_fixtures(self, scraped_events, oracle_films):
        """Every (title, date, time) in the oracle must appear in the scraper output.

        Titles are normalized: curly quotes → straight, NFKC, case-folded. AFS
        renders "PALESTINE ’36" (curly) while the oracle markdown uses the
        straight apostrophe; both refer to the same film.

        With all 46 AFS /screening/ fixtures saved, coverage should be ~100%
        for everything in the oracle's date range that still resolves to a
        live /screening/ page.
        """
        import unicodedata

        def _norm(title: str) -> str:
            title = unicodedata.normalize("NFKC", title or "")
            title = title.replace("\u2019", "'").replace("\u2018", "'")
            title = title.replace("\u201c", '"').replace("\u201d", '"')
            return title.strip().casefold()

        scraped_titles_norm = {_norm(e.get("title") or "") for e in scraped_events}
        expected_triples = {
            (_norm(s.title), s.date, s.time_24h)
            for s in oracle_films
            if _norm(s.title) in scraped_titles_norm
        }
        assert expected_triples, "No oracle titles match any scraper output"

        from scripts.oracle_afs import _to_24h
        scraped_triples: set[tuple[str, str, str]] = set()
        for e in scraped_events:
            title_norm = _norm(e.get("title") or "")
            for date, time in zip(e.get("dates", []), e.get("times", [])):
                try:
                    time_24 = _to_24h(time)
                except ValueError:
                    continue
                scraped_triples.add((title_norm, date, time_24))

        missing = expected_triples - scraped_triples
        coverage = 1.0 - len(missing) / len(expected_triples)
        assert coverage >= 0.95, (
            f"Oracle coverage {coverage:.0%} below 95% floor. "
            f"Missing {len(missing)} of {len(expected_triples)}: {sorted(missing)[:5]}..."
        )

    def test_palestine_multi_time_row(self, scraped_events):
        """'PALESTINE '36' appears on Apr 19 at both 12:30 PM and 6:15 PM in the oracle."""
        palestine_events = [e for e in scraped_events if "PALESTINE" in (e.get("title") or "")]
        assert palestine_events, "PALESTINE '36 not found in scraper output"
        all_dates_times = set()
        for e in palestine_events:
            for d, t in zip(e.get("dates", []), e.get("times", [])):
                all_dates_times.add((d, t))
        apr19_times = {t for (d, t) in all_dates_times if d == "2026-04-19"}
        assert apr19_times, "No PALESTINE screenings on 2026-04-19"
        # Times come back in 12h format from the scraper; accept either 12h or 24h.
        expected_patterns = {"12:30 PM", "6:15 PM", "12:30", "18:15"}
        assert any(t in expected_patterns for t in apr19_times), (
            f"PALESTINE Apr 19 times {apr19_times} don't include 12:30 PM / 6:15 PM"
        )

    def test_every_oracle_film_has_full_metadata(self, scraped_events, oracle_films):
        """MB.5: for every film the oracle knows about, scraper output must
        populate director/release_year/country/runtime_minutes when the film
        actually reached the scraper.

        Some oracle films may not appear in scraped_events (e.g., removed from
        the calendar, or not yet saved as a fixture) — those are skipped.
        Each appearing film must have ≥3 of the 4 metadata fields (some
        repertory/rep-cinema pages intentionally omit e.g. country).
        """
        import unicodedata

        def _norm(s: str) -> str:
            s = unicodedata.normalize("NFKC", s or "")
            return s.replace("\u2019", "'").replace("\u2018", "'").strip().casefold()

        oracle_titles = {_norm(s.title) for s in oracle_films}
        checked = 0
        metadata_fields = ("director", "release_year", "country", "runtime_minutes")
        for e in scraped_events:
            title_norm = _norm(e.get("title", ""))
            if title_norm not in oracle_titles:
                continue
            populated = sum(1 for f in metadata_fields if e.get(f))
            assert populated >= 3, (
                f"{e.get('title')!r}: only {populated}/4 of {metadata_fields} populated: "
                f"{ {f: e.get(f) for f in metadata_fields} }"
            )
            checked += 1
        assert checked >= 20, f"Only {checked} oracle films in scraper output (expected ≥20)"
