"""Tests for multi-account X fetch using per-account timelines."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from stock_detect.fetch_window import FetchWindow
from stock_detect.models import SocialPost
from stock_detect.twitter_fetcher import TwitterFetcher


class MultiAccountFetchTests(unittest.TestCase):
    def test_multi_account_fetch_uses_per_account_timeline(self):
        fetcher = TwitterFetcher()
        window = FetchWindow(
            after=datetime(2026, 4, 19, tzinfo=timezone.utc),
            before=datetime(2026, 6, 21, tzinfo=timezone.utc),
        )
        def fake_fetch_account(account, *, stats, **_kwargs):
            if account == "elonmusk":
                stats.api_posts_new = 1
                return [SocialPost("901", "new elon", "elonmusk", "x", window.before, 0, "", [])]
            stats.api_posts_new = 2
            return [SocialPost("902", "new ming", "mingchikuo", "x", window.before, 0, "", [])]

        fetcher._fetch_account = MagicMock(side_effect=fake_fetch_account)

        with patch("stock_detect.twitter_fetcher.TweetCache") as cache_cls, patch(
            "stock_detect.twitter_fetcher.time.sleep"
        ):
            cache_cls.return_value.available = True
            posts = fetcher.fetch_accounts(
                ["elonmusk", "mingchikuo"],
                window=window,
                max_pages=8,
                max_posts=100,
            )

        self.assertEqual({p.id for p in posts}, {"901", "902"})
        self.assertEqual(fetcher.last_stats.api_posts_new, 3)
        self.assertEqual(fetcher._fetch_account.call_count, 2)
        for call in fetcher._fetch_account.call_args_list:
            self.assertIn(call.args[0], {"elonmusk", "mingchikuo"})


if __name__ == "__main__":
    unittest.main()
