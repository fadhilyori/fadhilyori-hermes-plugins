import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from time_awareness import plugin


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
            r"[A-Za-z]+(?:/[A-Za-z_]+)+\s*$",
        )

    def test_fallback_to_utc_when_get_localzone_fails(self):
        with patch("time_awareness.plugin.get_localzone", side_effect=Exception("boom")):
            result = plugin.inject_context()
        self.assertIn("UTC", result["context"])

    def test_fallback_to_utc_for_invalid_timezone(self):
        with patch(
            "time_awareness.plugin.get_localzone",
            return_value="Invalid/Zone",
        ):
            result = plugin.inject_context()
        self.assertIn("UTC", result["context"])

    def test_fallback_to_utc_when_tzlocal_not_installed(self):
        with patch("time_awareness.plugin.get_localzone", None):
            result = plugin.inject_context()
        self.assertIn("UTC", result["context"])
        self.assertRegex(result["context"], r"\+00:00")


if __name__ == "__main__":
    unittest.main()
