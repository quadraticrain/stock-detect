"""Tests for post ticker resolution."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from stock_detect.models import SocialPost
from stock_detect.post_tickers import merge_ticker_lists, resolve_post_tickers


class PostTickerTests(unittest.TestCase):
    def test_resolve_uses_db_tickers_without_cashtag(self):
        post = SocialPost(
            id="1",
            text="Tesla production ramp looks strong",
            author="elonmusk",
            source="x",
            created=datetime(2026, 1, 1, tzinfo=timezone.utc),
            score=1,
            url="",
            tickers=["TSLA"],
        )
        self.assertEqual(resolve_post_tickers(post), ["TSLA"])

    def test_resolve_merges_db_and_text(self):
        post = SocialPost(
            id="2",
            text="Adding $NVDA",
            author="demo",
            source="x",
            created=datetime(2026, 1, 1, tzinfo=timezone.utc),
            score=1,
            url="",
            tickers=["TSM"],
        )
        self.assertEqual(resolve_post_tickers(post), ["TSM", "NVDA"])

    def test_merge_ticker_lists(self):
        self.assertEqual(merge_ticker_lists(["NVDA"], ["nvda", "TSM"]), ["NVDA", "TSM"])


if __name__ == "__main__":
    unittest.main()
