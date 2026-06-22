"""Tests for AI analysis MySQL schema definitions."""

from __future__ import annotations

import unittest

from stock_detect.ai_analysis_schema import AI_ANALYSIS_TABLES
from stock_detect.config import (
    MYSQL_TABLE_AI_CONSENSUS,
    MYSQL_TABLE_AI_RUNS,
    MYSQL_TABLE_AI_SIGNALS,
    MYSQL_TABLE_AI_TOP_TICKERS,
)
from stock_detect.tweet_cache import TweetCache


class AiAnalysisSchemaTests(unittest.TestCase):
    def test_table_names(self):
        names = {t.name for t in AI_ANALYSIS_TABLES}
        self.assertEqual(
            names,
            {
                MYSQL_TABLE_AI_RUNS,
                MYSQL_TABLE_AI_SIGNALS,
                MYSQL_TABLE_AI_CONSENSUS,
                MYSQL_TABLE_AI_TOP_TICKERS,
            },
        )

    def test_signals_primary_key_includes_ticker(self):
        signals = next(t for t in AI_ANALYSIS_TABLES if t.name == MYSQL_TABLE_AI_SIGNALS)
        self.assertEqual(signals.primary_key, ("run_id", "post_id", "ticker"))

    def test_runs_has_checkpoint_columns(self):
        runs = next(t for t in AI_ANALYSIS_TABLES if t.name == MYSQL_TABLE_AI_RUNS)
        col_names = {c.name for c in runs.columns}
        self.assertIn("checkpoint_post_id", col_names)
        self.assertIn("checkpoint_post_created_at", col_names)
        self.assertIn("resume_from_post_id", col_names)

    def test_merged_into_tweet_cache_schema(self):
        from stock_detect import tweet_cache as tc

        table_names = {t.name for t in tc._TABLES}
        self.assertIn(MYSQL_TABLE_AI_RUNS, table_names)
        self.assertIn(MYSQL_TABLE_AI_TOP_TICKERS, table_names)


if __name__ == "__main__":
    unittest.main()
