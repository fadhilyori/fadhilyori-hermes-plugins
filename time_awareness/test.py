import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from . import plugin


class TestBuildContext(unittest.TestCase):
    def test_format_matches_expected_pattern(self):
        now = datetime(2024, 6, 15, 14, 30, tzinfo=ZoneInfo("Asia/Jakarta"))
        result = plugin._build_context(now, "Asia/Jakarta")
        self.assertEqual(
            result,
            "2024-06-15T14:30+07:00 Sat Asia/Jakarta",
        )

    def test_weekday_localized(self):
        now = datetime(2024, 1, 1, 9, 0, tzinfo=ZoneInfo("Asia/Jakarta"))
        result = plugin._build_context(now, "Asia/Jakarta")
        self.assertIn("Mon", result)

    def test_utc_timezone(self):
        now = datetime(2024, 6, 15, 7, 30, tzinfo=ZoneInfo("UTC"))
        result = plugin._build_context(now, "UTC")
        self.assertEqual(
            result,
            "2024-06-15T07:30+00:00 Sat UTC",
        )

    def test_returns_non_empty_string(self):
        now = datetime(2024, 6, 15, 14, 30, tzinfo=ZoneInfo("Asia/Jakarta"))
        result = plugin._build_context(now, "Asia/Jakarta")
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)


class TestInjectContext(unittest.TestCase):
    def test_returns_dict_with_context_key(self):
        result = plugin.inject_context()
        self.assertIsInstance(result, dict)
        self.assertIn("context", result)
        self.assertIsInstance(result["context"], str)
        self.assertTrue(len(result["context"]) > 0)

    def test_context_contains_iso_timestamp(self):
        result = plugin.inject_context()
        self.assertRegex(
            result["context"],
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}[+-]\d{2}:\d{2}",
        )

    def test_context_ends_with_timezone_name(self):
        result = plugin.inject_context()
        self.assertRegex(
            result["context"],
            r"[A-Za-z]+(?:/[A-Za-z_]+)*\s*$",
        )

    def test_uses_configured_timezone_when_available(self):
        jakarta = ZoneInfo("Asia/Jakarta")
        with patch("time_awareness.plugin.get_timezone", return_value=jakarta):
            result = plugin.inject_context()
        self.assertIn("Asia/Jakarta", result["context"])
        self.assertIn("+07:00", result["context"])

    def test_falls_back_to_local_time_when_no_timezone_configured(self):
        local_now = datetime(2026, 7, 12, 15, 30, tzinfo=ZoneInfo("Etc/GMT-7"))
        with patch("time_awareness.plugin.get_timezone", return_value=None), \
             patch("time_awareness.plugin.now", return_value=local_now):
            result = plugin.inject_context()
        self.assertRegex(result["context"], r"[+-]\d{2}:\d{2}")
        self.assertNotIn("+00:00", result["context"])

    def test_falls_back_to_local_time_when_hermes_time_raises(self):
        with patch("time_awareness.plugin.now", side_effect=Exception("boom")), \
             patch("time_awareness.plugin.get_timezone", side_effect=Exception("boom")):
            result = plugin.inject_context()
        self.assertRegex(result["context"], r"[+-]\d{2}:\d{2}")


if __name__ == "__main__":
    unittest.main()
