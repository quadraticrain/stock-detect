"""Tests for report manifest metadata."""

from __future__ import annotations

import unittest

from stock_detect.report import run_entry


class RunEntryTests(unittest.TestCase):
    def test_marks_unchanged_when_no_api_posts(self):
        entry = run_entry(
            {
                "id": "20260621T185757Z_x_aleabitoreddit",
                "generated_at": "2026-06-21T18:57:57+00:00",
                "source": "x",
                "accounts": ["aleabitoreddit"],
                "fetched_posts": 630,
                "signal_count": 1834,
                "consensus_count": 550,
                "api_posts_new": 0,
                "pages_fetched": 2,
                "cache_posts": 630,
            }
        )
        self.assertTrue(entry["data_unchanged"])
        self.assertEqual(entry["api_posts_new"], 0)

    def test_marks_new_data_when_api_posts_added(self):
        entry = run_entry(
            {
                "id": "20260621T184320Z_x_aleabitoreddit",
                "generated_at": "2026-06-21T18:43:20+00:00",
                "source": "x",
                "accounts": ["aleabitoreddit"],
                "fetched_posts": 630,
                "signal_count": 1834,
                "consensus_count": 550,
                "api_posts_new": 540,
            }
        )
        self.assertFalse(entry["data_unchanged"])


if __name__ == "__main__":
    unittest.main()
