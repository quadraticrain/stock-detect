"""Tests for report manifest metadata."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from stock_detect.report import enrich_manifest_from_reports, run_entry


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

    def test_enrich_manifest_backfills_api_metadata(self):
        run_id = "20260621T185757Z_x_aleabitoreddit"
        manifest = {
            "latest": run_id,
            "runs": [
                {
                    "id": run_id,
                    "generated_at": "2026-06-21T18:57:57+00:00",
                    "source": "x",
                    "accounts": ["aleabitoreddit"],
                    "html": f"reports/{run_id}.html",
                    "json": f"reports/{run_id}.json",
                    "fetched_posts": 630,
                    "signal_count": 1834,
                    "consensus_count": 550,
                }
            ],
        }
        with tempfile.TemporaryDirectory() as reports_dir:
            reports = Path(reports_dir)
            (reports / f"{run_id}.json").write_text(
                '{"api_posts_new": 0, "pages_fetched": 2, "cache_posts": 630}',
                encoding="utf-8",
            )
            enriched = enrich_manifest_from_reports(manifest, reports)
        entry = enriched["runs"][0]
        self.assertTrue(entry["data_unchanged"])
        self.assertEqual(entry["api_posts_new"], 0)
        self.assertEqual(entry["pages_fetched"], 2)


if __name__ == "__main__":
    unittest.main()
