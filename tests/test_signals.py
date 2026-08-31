"""Tests for social signal extraction."""

from datetime import datetime, timezone

import unittest

from stock_detect.models import SocialPost
from stock_detect.signal_extractor import (
    aggregate_daily_consensus,
    extract_post_signals,
    extract_social_post_signals,
    is_actionable_post,
    mask_non_signal_phrases,
)


class NonSignalPhraseMaskTests(unittest.TestCase):
    """关键词计数器误把「short sellers」「AI bears」等当成作者看空表态的回归测试。"""

    def test_masks_bear_camp_references(self):
        """作者**反驳**空方的语境不应计为看空。"""
        for text in (
            "overall drop + short sellers with timing",
            "FYI to the AI bears: $NVDA projects $1.3T",
            "mix of algorithms, short sellers, dormant accounts",
            'management was asked how to "stop the bleeding"',
        ):
            with self.subTest(text=text):
                self.assertEqual(_sell_hits(mask_non_signal_phrases(text)), 0)

    def test_masks_time_horizon_and_meeting_words(self):
        """short/long term、earnings call 是时间尺度/业绩会，不是多空表态。"""
        self.assertEqual(_sell_hits(mask_non_signal_phrases("short term structural overhang")), 0)
        self.assertEqual(_buy_hits(mask_non_signal_phrases("55-60% long term gross margins")), 0)
        self.assertEqual(_buy_hits(mask_non_signal_phrases("all the fun happens in the earnings call")), 0)
        self.assertEqual(_buy_hits(mask_non_signal_phrases("the entire calls were focused on financials")), 0)
        self.assertEqual(_buy_hits(mask_non_signal_phrases("q: how long into 2028 does that extend?")), 0)

    def test_masks_put_as_plain_verb(self):
        """put 作为普通动词（戴帽子/表述）不是看跌期权。"""
        self.assertEqual(_sell_hits(mask_non_signal_phrases("if i had to put my supply chain hat on")), 0)
        self.assertEqual(_sell_hits(mask_non_signal_phrases("as morgan stanley put it...")), 0)

    def test_keeps_genuine_directional_signals(self):
        """真实多空表态必须完整保留——掩蔽不能误伤。"""
        self.assertGreater(_sell_hits(mask_non_signal_phrases("I am short $TSLA")), 0)
        self.assertGreater(_sell_hits(mask_non_signal_phrases("bought puts on $AAPL")), 0)
        self.assertGreater(_sell_hits(mask_non_signal_phrases("time to sell $INTC")), 0)
        self.assertGreater(_buy_hits(mask_non_signal_phrases("buying $NVDA calls here")), 0)
        self.assertGreater(_buy_hits(mask_non_signal_phrases("still bullish on $AAOI")), 0)
        self.assertGreater(_buy_hits(mask_non_signal_phrases("i remain long.")), 0)

    def test_mask_preserves_offsets(self):
        """掩蔽必须等长：_proximity_score 依赖代码周围的字符窗口。"""
        text = "$SIVE dropped on short sellers but long term thesis intact"
        masked = mask_non_signal_phrases(text)
        self.assertEqual(len(masked), len(text))
        self.assertEqual(masked.index("$SIVE"), text.index("$SIVE"))

    def test_bullish_post_not_flagged_sell(self):
        """端到端：看多帖提到 short sellers 时，不得被判为 sell。

        真实 case（@aleabitoreddit 2026-08）：NVDA/SIVE/AAOI 因此全部被误标 sell。
        """
        signals = extract_post_signals(
            "$NVDA beat big. FYI to the AI bears: projects $1.3T hyperscaler spend. "
            "The drop was short sellers with timing. Still bullish, long term thesis intact. "
            "Watch the earnings call.",
            datetime(2026, 8, 26, tzinfo=timezone.utc),
            100,
            None,
            source="x",
            author="aleabitoreddit",
            all_cashtags=True,
        )
        nvda = [s for s in signals if s.ticker == "NVDA"]
        self.assertTrue(nvda)
        self.assertEqual(nvda[0].sell_score, 0)
        self.assertNotEqual(nvda[0].recommendation, "sell")


def _sell_hits(text: str) -> float:
    from stock_detect.config import SELL_NEGATIONS, SELL_WORDS
    from stock_detect.signal_extractor import _word_score

    return _word_score(text, SELL_WORDS, SELL_NEGATIONS)


def _buy_hits(text: str) -> float:
    from stock_detect.config import BUY_NEGATIONS, BUY_WORDS
    from stock_detect.signal_extractor import _word_score

    return _word_score(text, BUY_WORDS, BUY_NEGATIONS)


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
