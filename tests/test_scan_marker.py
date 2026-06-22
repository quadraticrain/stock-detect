"""Tests for CI scan markers."""

from __future__ import annotations

import unittest

from stock_detect.ci_scan_metadata import merge_ci_scan_metadata
from stock_detect.scan_marker import (
    MARKER_NO_NEW,
    ci_marker_for,
    ci_marker_post_id,
    parse_ci_marker,
)
from stock_detect.tweet_cache import FetchState


class ScanMarkerTests(unittest.TestCase):
    def test_no_new_marker(self):
        self.assertEqual(ci_marker_for(0), MARKER_NO_NEW)
        self.assertEqual(parse_ci_marker(MARKER_NO_NEW), 0)

    def test_new_marker(self):
        marker = ci_marker_for(5)
        self.assertEqual(marker, "***NEW:5***")
        self.assertEqual(parse_ci_marker(marker), 5)

    def test_marker_post_id(self):
        self.assertEqual(ci_marker_post_id("HillaryClinton"), "###CI_SCAN_hillaryclinton###")
        self.assertEqual(ci_marker_post_id("SpeakerPelosi"), "###CI_SCAN_speakerpelosi###")


class MergeCiScanMetadataTests(unittest.TestCase):
    def test_merges_no_new_marker_into_payload(self):
        class FakeCache:
            available = True

            def get_state(self, account: str) -> FetchState:
                return FetchState(
                    account=account,
                    last_ci_marker=MARKER_NO_NEW,
                    last_ci_api_posts_new=0,
                    last_ci_window_days=180,
                    last_ci_run_id="12345",
                )

        payload = merge_ci_scan_metadata(
            {"fetched_posts": 10},
            ["demo"],
            FakeCache(),  # type: ignore[arg-type]
        )
        self.assertTrue(payload["data_unchanged"])
        self.assertEqual(payload["api_posts_new"], 0)
        self.assertEqual(payload["ci_scan_marker"], MARKER_NO_NEW)
        self.assertIn("demo", payload["ci_scan_markers"])


if __name__ == "__main__":
    unittest.main()
