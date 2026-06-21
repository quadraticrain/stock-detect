"""Tests for social signal extraction."""

from datetime import datetime, timezone

import unittest

from stock_detect.models import SocialPost
from stock_detect.signal_extractor import (
    aggregate_daily_consensus,
    extract_post_signals,
    extract_social_post_signals,
    is_actionable_post,
)


class SignalExtractorTests(unittest.TestCase):
    def test_buy_signal_from_dd_post(self):
        created = datetime(2024, 1, 15, tzinfo=timezone.utc)
        signals = extract_post_signals(
            "$NVDA is a buy before earnings\nI'm loading calls on NVDA.",
            created,
            120,
            {"NVDA", "AMD"},
            source="wsb",
            flair="DD",
        )
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].ticker, "NVDA")
        self.assertEqual(signals[0].recommendation, "buy")

    def test_x_post_all_cashtags(self):
        created = datetime(2024, 1, 15, tzinfo=timezone.utc)
        post = SocialPost(
            id="1",
            text="Bullish on $AXTI and $SOI for photonics chokepoints",
            author="aleabitoreddit",
            source="x",
            created=created,
            score=500,
            url="https://x.com/status/1",
            tickers=["AXTI", "SOI"],
        )
        signals = extract_social_post_signals(post, None, all_cashtags=True)
        tickers = {s.ticker for s in signals}
        self.assertIn("AXTI", tickers)
        self.assertIn("SOI", tickers)

    def test_reactive_flair_excluded(self):
        self.assertFalse(is_actionable_post("wsb", "Loss", "I lost everything on GME"))
        self.assertTrue(is_actionable_post("x", None, "$NVDA looks strong"))

    def test_daily_consensus_threshold(self):
        created = datetime(2024, 1, 15, 12, tzinfo=timezone.utc)
        signals = []
        for _ in range(3):
            signals.extend(
                extract_post_signals(
                    "$AMD buy calls",
                    created,
                    50,
                    {"AMD"},
                    source="x",
                )
            )
        signals.extend(
            extract_post_signals(
                "$AMD sell",
                created,
                10,
                {"AMD"},
                source="x",
            )
        )
        daily = aggregate_daily_consensus(signals)
        self.assertEqual(daily[0].signal, "buy")


if __name__ == "__main__":
    unittest.main()
