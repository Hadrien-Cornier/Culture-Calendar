"""Unit tests for the Paramount scraper sparse-metadata policy."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.scrapers.paramount_scraper import ParamountScraper


class TestParamountSparseMetadataPolicy(unittest.TestCase):
    """Exercise _is_sparse_event and _apply_sparse_metadata_policy directly."""

    def setUp(self) -> None:
        self.scraper = ParamountScraper()

    def _rich_event(self, title: str = "Dune: Part Two") -> dict:
        return {
            "title": title,
            "type": "movie",
            "dates": ["2026-05-01"],
            "times": ["7:00 PM"],
            "venue": "Paramount Theatre",
            "url": "https://tickets.austintheatre.org/1",
            "description": "A detailed description of the film screening.",
        }

    def _sparse_event(self, title: str = "Mystery Matinee") -> dict:
        return {
            "title": title,
            "type": "movie",
            "dates": ["2026-05-02"],
            "times": ["2:00 PM"],
            "venue": "Paramount Theatre",
            "url": "https://tickets.austintheatre.org/2",
            "description": "",
        }

    def test_is_sparse_event_detects_empty_metadata(self) -> None:
        self.assertTrue(self.scraper._is_sparse_event(self._sparse_event()))

    def test_is_sparse_event_false_when_description_present(self) -> None:
        self.assertFalse(self.scraper._is_sparse_event(self._rich_event()))

    def test_is_sparse_event_false_when_runtime_present(self) -> None:
        event = self._sparse_event()
        event["runtime_minutes"] = 120
        self.assertFalse(self.scraper._is_sparse_event(event))

    def test_is_sparse_event_false_when_release_year_present(self) -> None:
        event = self._sparse_event()
        event["release_year"] = 1999
        self.assertFalse(self.scraper._is_sparse_event(event))

    def test_is_sparse_event_false_when_director_present(self) -> None:
        event = self._sparse_event()
        event["director"] = "Stanley Kubrick"
        self.assertFalse(self.scraper._is_sparse_event(event))

    def test_policy_skips_sparse_when_under_threshold(self) -> None:
        events = [self._rich_event(f"Rich {i}") for i in range(9)]
        events.append(self._sparse_event("Sparse 1"))

        result = self.scraper._apply_sparse_metadata_policy(events)

        self.assertEqual(len(result), 9)
        titles = {e["title"] for e in result}
        self.assertNotIn("Sparse 1", titles)

    def test_policy_inverts_when_above_threshold(self) -> None:
        events = [self._rich_event(f"Rich {i}") for i in range(3)]
        events.extend(self._sparse_event(f"Sparse {i}") for i in range(2))

        result = self.scraper._apply_sparse_metadata_policy(events)

        self.assertEqual(len(result), 5)
        sparse_results = [e for e in result if e["title"].startswith("Sparse")]
        for event in sparse_results:
            expected = f"{event['title']} at the Paramount — see venue for details"
            self.assertEqual(event["description"], expected)
            self.assertEqual(event["one_liner_summary"], expected)

        rich_results = [e for e in result if e["title"].startswith("Rich")]
        for event in rich_results:
            self.assertNotIn("one_liner_summary", event)
            self.assertEqual(
                event["description"],
                "A detailed description of the film screening.",
            )

    def test_policy_no_sparse_events_returns_unchanged(self) -> None:
        events = [self._rich_event(f"Rich {i}") for i in range(3)]

        result = self.scraper._apply_sparse_metadata_policy(events)

        self.assertEqual(result, events)

    def test_policy_empty_list_returns_empty(self) -> None:
        self.assertEqual(self.scraper._apply_sparse_metadata_policy([]), [])

    def test_policy_threshold_boundary_at_twenty_percent(self) -> None:
        events = [self._rich_event(f"Rich {i}") for i in range(4)]
        events.append(self._sparse_event("Sparse 1"))

        result = self.scraper._apply_sparse_metadata_policy(events)

        self.assertEqual(len(result), 4)
        titles = {e["title"] for e in result}
        self.assertNotIn("Sparse 1", titles)


if __name__ == "__main__":
    unittest.main()
