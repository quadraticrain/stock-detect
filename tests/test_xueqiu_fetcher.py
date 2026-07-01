from __future__ import annotations

import unittest

from stock_detect.xueqiu_fetcher import _status_to_post
from stock_detect.signal_extractor import extract_social_post_signals


class XueqiuFetcherTests(unittest.TestCase):
    def test_status_to_post_cleans_html_and_tickers(self):
        post = _status_to_post(
            {
                "id": 123,
                "created_at": 1780300800000,
                "text": '<p>长期看好 $AAPL&nbsp;和 <a href="/S/SH600519">$贵州茅台(SH600519)$</a></p>',
                "user": {"id": 1247347556, "screen_name": "大道无形我有型"},
                "reply_count": 7,
            },
            "1247347556",
        )

        self.assertIsNotNone(post)
        assert post is not None
        self.assertEqual(post.id, "xueqiu:123")
        self.assertEqual(post.source, "xueqiu")
        self.assertEqual(post.author, "xueqiu:1247347556")
        self.assertEqual(post.score, 7)
        self.assertEqual(post.tickers, ["AAPL", "SH600519"])
        self.assertNotIn("<p>", post.text)

    def test_xueqiu_tickers_feed_signal_extractor(self):
        post = _status_to_post(
            {
                "id": 124,
                "created_at": 1780300800000,
                "text": '<a href="/S/SH600519">$贵州茅台(SH600519)$</a> 买一点',
            },
            "1247347556",
        )

        assert post is not None
        signals = extract_social_post_signals(post, None)
        self.assertEqual([signal.ticker for signal in signals], ["SH600519"])

    def test_status_to_post_skips_reposts_and_other_users(self):
        base = {"id": 125, "created_at": 1780300800000, "text": "买 $AAPL", "user": {"id": 1247347556}}

        self.assertIsNone(_status_to_post({**base, "retweeted_status": {"id": 1}}, "1247347556"))
        self.assertIsNone(_status_to_post({**base, "user": {"id": 1}}, "1247347556"))

    def test_status_to_post_keeps_own_replies(self):
        post = _status_to_post(
            {
                "id": 126,
                "created_at": 1780300800000,
                "text": "回帖里提到 $AAPL",
                "user": {"id": 1247347556},
                "in_reply_to_status_id": 1,
            },
            "1247347556",
        )

        self.assertIsNotNone(post)

    def test_status_to_post_skips_non_duan_replies(self):
        post = _status_to_post(
            {
                "id": 127,
                "created_at": 1780300800000,
                "text": "回帖里提到 $AAPL",
                "user": {"id": 1102105103},
                "in_reply_to_status_id": 1,
            },
            "1102105103",
        )

        self.assertIsNone(post)


if __name__ == "__main__":
    unittest.main()
