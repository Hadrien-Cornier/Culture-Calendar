#!/usr/bin/env python3
"""
Unit tests for Alienated Majesty Books scraper
Tests HTML file against expected output in test database
"""

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add the src directory to the path to import the scraper
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src', 'scrapers'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
from alienated_majesty_scraper import AlienatedMajestyBooksScraper


class TestAlienatedMajestyBooksScraper(unittest.TestCase):
    """Unit tests for Alienated Majesty Books scraper"""

    def setUp(self):
        """Set up test fixtures"""
        self.scraper = AlienatedMajestyBooksScraper()
        self.test_data_dir = Path(__file__).parent / "Alienated_majesty_test_data"
        
        # Load test database
        with open(self.test_data_dir / "alienated_majesty_scraper_test_database.json", 'r') as f:
            self.test_database = json.load(f)

    def _compare_event(self, actual, expected, event_index):
        """Compare a single event and return detailed error messages if different"""
        errors = []
        
        # Check all required fields
        for field, expected_value in expected.items():
            actual_value = actual.get(field)
            if actual_value != expected_value:
                errors.append(f"  Event {event_index} - {field}: Expected {expected_value!r}, got {actual_value!r}")
        
        # Check for extra fields in actual
        for field in actual.keys():
            if field not in expected:
                errors.append(f"  Event {event_index} - Unexpected field {field}: {actual[field]!r}")
                
        return errors

    def _run_single_test(self, test_case):
        """Run a single test case"""
        test_id = test_case["test_id"]
        html_file = test_case["input"]["html_file"]
        expected_events = test_case["expected_output"]
        url = test_case["input"]["url"]
        
        # Load HTML file
        html_path = self.test_data_dir / html_file
        if not html_path.exists():
            return f"❌ Test {test_id}: HTML file {html_file} not found"
        
        with open(html_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        # Extract events using the scraper's extraction method
        actual_events = self.scraper._extract_book_club_events(html_content, url)
        
        if not actual_events:
            return f"❌ Test {test_id}: No events extracted"
        
        # Compare number of events
        if len(actual_events) != len(expected_events):
            return f"❌ Test {test_id}: Expected {len(expected_events)} events, got {len(actual_events)}"
        
        # Compare each event
        all_errors = []
        for i, (actual_event, expected_event) in enumerate(zip(actual_events, expected_events)):
            event_errors = self._compare_event(actual_event, expected_event, i+1)
            all_errors.extend(event_errors)
        
        if all_errors:
            return f"❌ Test {test_id}: FAILED\n" + "\n".join(all_errors)
        else:
            return f"✅ Test {test_id}: PASSED - {len(actual_events)} events extracted correctly"

    def test_all_book_club_events(self):
        """Test all book club events in the test database"""
        print(f"\n📚 Running Alienated Majesty Books Scraper Unit Tests")
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
        print(f"📈 Success Rate: {passed/(passed+failed)*100:.1f}%")
        
        # Assert that all tests passed
        if failed > 0:
            self.fail(f"{failed} out of {passed+failed} tests failed")

    def test_individual_fields(self):
        """Test individual fields across all book club events"""
        print(f"\n🔍 Testing Individual Fields")
        
        field_stats = {}
        
        for test_case in self.test_database["test_cases"]:
            html_file = test_case["input"]["html_file"]
            expected_events = test_case["expected_output"]
            url = test_case["input"]["url"]
            
            # Load and extract data
            html_path = self.test_data_dir / html_file
            with open(html_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            actual_events = self.scraper._extract_book_club_events(html_content, url)
            
            if not actual_events or len(actual_events) != len(expected_events):
                continue
            
            # Track field accuracy
            for actual_event, expected_event in zip(actual_events, expected_events):
                for field in expected_event.keys():
                    if field not in field_stats:
                        field_stats[field] = {"correct": 0, "total": 0}
                    
                    field_stats[field]["total"] += 1
                    if actual_event.get(field) == expected_event[field]:
                        field_stats[field]["correct"] += 1
        
        # Print field statistics
        for field, stats in field_stats.items():
            accuracy = stats["correct"] / stats["total"] * 100 if stats["total"] > 0 else 0
            print(f"  {field:20} {stats['correct']:2}/{stats['total']:2} ({accuracy:5.1f}%)")

    def test_book_club_series_detection(self):
        """Test that different book club series are detected correctly"""
        print(f"\n📖 Testing Book Club Series Detection")
        
        expected_series = set()
        actual_series = set()
        
        for test_case in self.test_database["test_cases"]:
            html_file = test_case["input"]["html_file"]
            expected_events = test_case["expected_output"]
            url = test_case["input"]["url"]
            
            # Collect expected series
            for event in expected_events:
                if event.get("series"):
                    expected_series.add(event["series"])
            
            # Load and extract data
            html_path = self.test_data_dir / html_file
            with open(html_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            actual_events = self.scraper._extract_book_club_events(html_content, url)
            
            if actual_events:
                for event in actual_events:
                    if event.get("series"):
                        actual_series.add(event["series"])
        
        print(f"  Expected series: {sorted(expected_series)}")
        print(f"  Detected series: {sorted(actual_series)}")
        
        missing_series = expected_series - actual_series
        extra_series = actual_series - expected_series
        
        if missing_series:
            print(f"  ❌ Missing series: {sorted(missing_series)}")
        if extra_series:
            print(f"  ⚠️  Extra series: {sorted(extra_series)}")
        if not missing_series and not extra_series:
            print(f"  ✅ All series detected correctly")

    def test_date_time_parsing(self):
        """Test that dates and times are parsed correctly"""
        print(f"\n📅 Testing Date/Time Parsing")
        
        for test_case in self.test_database["test_cases"]:
            html_file = test_case["input"]["html_file"]
            expected_events = test_case["expected_output"]
            url = test_case["input"]["url"]
            
            # Load and extract data
            html_path = self.test_data_dir / html_file
            with open(html_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            actual_events = self.scraper._extract_book_club_events(html_content, url)
            
            if not actual_events:
                continue
            
            dates_ok = 0
            times_ok = 0
            total_events = len(actual_events)
            
            for event in actual_events:
                # Check date format (should be YYYY-MM-DD)
                date = event.get("date", "")
                if isinstance(date, str) and len(date) == 10 and date.count('-') == 2:
                    try:
                        # Try to parse as date
                        from datetime import datetime
                        datetime.strptime(date, '%Y-%m-%d')
                        dates_ok += 1
                    except ValueError:
                        pass
                
                # Check time format (should be like "7:00 PM" or "11:00 AM")
                time = event.get("time", "")
                if isinstance(time, str) and any(x in time for x in ["AM", "PM"]):
                    times_ok += 1
            
            print(f"  Test {test_case['test_id']}: Dates: {dates_ok}/{total_events} correct, Times: {times_ok}/{total_events} correct")

    def test_llm_extraction(self):
        """Test that LLM extraction works correctly"""
        print(f"\n🤖 Testing LLM Extraction")
        
        test_case = self.test_database["test_cases"][0]
        html_file = test_case["input"]["html_file"]
        html_path = self.test_data_dir / html_file
        url = test_case["input"]["url"]
        
        with open(html_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        # Test LLM extraction directly
        events = self.scraper._extract_with_llm(html_content, url)
        
        print(f"  LLM extracted {len(events)} events")
        
        # Test that we can find book club series
        series_found = set()
        for event in events:
            if event.get("series"):
                series_found.add(event["series"])
        
        print(f"  Series found: {sorted(series_found)}")
        
        # Should find at least some events
        self.assertGreater(len(events), 0, "LLM should extract some events")


if __name__ == "__main__":
    # Run tests with verbose output
    unittest.main(verbosity=2) 