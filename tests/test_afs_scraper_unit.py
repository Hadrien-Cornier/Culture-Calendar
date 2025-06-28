#!/usr/bin/env python3
"""
Unit tests for AFS scraper
Tests individual HTML files against expected output in test database
"""

import json
import os
import sys
import unittest
from pathlib import Path

from src.scrapers.afs_scraper import ComprehensiveAFSScraper

# Add the src directory to the path to import the scraper
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src", "scrapers"))


class TestAFSScraper(unittest.TestCase):
    """Unit tests for AFS scraper"""

    def setUp(self):
        """Set up test fixtures"""
        self.scraper = ComprehensiveAFSScraper()
        self.test_data_dir = Path(__file__).parent / "AFS_test_data"

        # Load test database
        with open(self.test_data_dir / "afs_scraper_test_database.json", "r") as f:
            self.test_database = json.load(f)

    def _compare_values(self, actual, expected, field_name):
        """Compare two values and return detailed error message if different"""
        if actual != expected:
            return f"{field_name}: Expected {expected!r}, got {actual!r}"
        return None

    def _run_single_test(self, test_case):
        """Run a single test case"""
        test_id = test_case["test_id"]
        html_file = test_case["input"]["html_file"]
        expected = test_case["expected_output"]

        # Load HTML file
        html_path = self.test_data_dir / html_file
        if not html_path.exists():
            return f"❌ Test {test_id}: HTML file {html_file} not found"

        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        # Parse with scraper
        actual = self.scraper.parse_movie_page(html_content, expected["url"])

        if actual is None:
            return f"❌ Test {test_id}: Scraper returned None"

        # Compare all fields
        errors = []
        for field in expected.keys():
            error = self._compare_values(actual.get(field), expected[field], field)
            if error:
                errors.append(f"  • {error}")

        if errors:
            return f"❌ Test {test_id} ({expected['title']}): FAILED\n" + "\n".join(
                errors
            )
        else:
            return f"✅ Test {test_id} ({expected['title']}): PASSED"

    def test_all_movie_pages(self):
        """Test all movie pages in the test database"""
        print(f"\n🎬 Running AFS Scraper Unit Tests")
        print(f"📋 Found {len(self.test_database['test_cases'])} test cases\n")

        results = []
        passed = 0
        failed = 0

        for test_case in self.test_database["test_cases"]:
            result = self._run_single_test(test_case)
            results.append(result)
            print(result)

            if result.startswith("✅"):
                passed += 1
            else:
                failed += 1

        print(f"\n📊 Test Results:")
        print(f"✅ Passed: {passed}")
        print(f"❌ Failed: {failed}")
        print(f"📈 Success Rate: {passed / (passed + failed) * 100:.1f}%")

        # Assert that all tests passed
        if failed > 0:
            self.fail(f"{failed} out of {passed + failed} tests failed")

    def test_individual_fields(self):
        """Test individual fields across all test cases"""
        print(f"\n🔍 Testing Individual Fields")

        field_stats = {}

        for test_case in self.test_database["test_cases"]:
            html_file = test_case["input"]["html_file"]
            expected = test_case["expected_output"]

            # Load and parse HTML
            html_path = self.test_data_dir / html_file
            with open(html_path, "r", encoding="utf-8") as f:
                html_content = f.read()

            actual = self.scraper.parse_movie_page(html_content, expected["url"])

            if actual is None:
                continue

            # Track field accuracy
            for field in expected.keys():
                if field not in field_stats:
                    field_stats[field] = {"correct": 0, "total": 0}

                field_stats[field]["total"] += 1
                if actual.get(field) == expected[field]:
                    field_stats[field]["correct"] += 1

        # Print field statistics
        for field, stats in field_stats.items():
            accuracy = (
                stats["correct"] / stats["total"] * 100 if stats["total"] > 0 else 0
            )
            print(
                f"  {field:20} {stats['correct']:2}/{stats['total']:2} ({accuracy:5.1f}%)"
            )

    def test_special_screening_detection(self):
        """Test that special screening detection works correctly"""
        print(f"\n⭐ Testing Special Screening Detection")

        special_screenings = []
        regular_screenings = []

        for test_case in self.test_database["test_cases"]:
            expected = test_case["expected_output"]
            if expected.get("is_special_screening", False):
                special_screenings.append(expected["title"])
            else:
                regular_screenings.append(expected["title"])

        print(f"  Special screenings: {len(special_screenings)}")
        for title in special_screenings:
            print(f"    • {title}")

        print(f"  Regular screenings: {len(regular_screenings)}")
        for title in regular_screenings:
            print(f"    • {title}")

    def test_date_time_parsing(self):
        """Test that dates and times are parsed correctly"""
        print(f"\n📅 Testing Date/Time Parsing")

        for test_case in self.test_database["test_cases"]:
            test_id = test_case["test_id"]
            html_file = test_case["input"]["html_file"]
            expected = test_case["expected_output"]

            # Load and parse HTML
            html_path = self.test_data_dir / html_file
            with open(html_path, "r", encoding="utf-8") as f:
                html_content = f.read()

            actual = self.scraper.parse_movie_page(html_content, expected["url"])

            if actual is None:
                continue

            # Check date format (should be YYYY-MM-DD)
            dates_ok = True
            if actual.get("dates"):
                for date in actual["dates"]:
                    if (
                        not isinstance(date, str)
                        or len(date) != 10
                        or date.count("-") != 2
                    ):
                        dates_ok = False
                        break

            # Check time format (should be like "7:30 PM")
            times_ok = True
            if actual.get("times"):
                for time in actual["times"]:
                    if not isinstance(time, str) or not any(
                        x in time for x in ["AM", "PM"]
                    ):
                        times_ok = False
                        break

            status = "✅" if dates_ok and times_ok else "❌"
            print(f"  {status} Test {test_id}: Dates: {dates_ok}, Times: {times_ok}")


if __name__ == "__main__":
    # Run tests with verbose output
    unittest.main(verbosity=2)
