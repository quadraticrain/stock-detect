"""Tests for fetch window and paginated fetchers."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from stock_detect.fetch_window import FetchWindow, default_fetch_window, filter_to_window
from stock_detect.models import SocialPost
from stock_detect.twitter_fetcher import TwitterFetcher


class FetchWindowTests(unittest.TestCase):
    def test_default_window_is_63_days(self):
        before = datetime(2026, 6, 21, tzinfo=timezone.utc)
        window = default_fetch_window(before=before)
        self.assertEqual(window.window_days, 63)
        self.assertEqual(window.before, before)
        self.assertEqual(window.after, before - timedelta(days=63))

    def test_filter_to_window(self):
        window = FetchWindow(
            after=datetime(2026, 4, 1, tzinfo=timezone.utc),
            before=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )
        posts = [
            SocialPost("1", "a", "u", "x", datetime(2026, 5, 1, tzinfo=timezone.utc), 0, "", []),
            SocialPost("2", "b", "u", "x", datetime(2026, 1, 1, tzinfo=timezone.utc), 0, "", []),
        ]
        filtered = filter_to_window(posts, window, created_at=lambda p: p.created)
        self.assertEqual([p.id for p in filtered], ["1"])


class TwitterFetcherTests(unittest.TestCase):
    def test_syndication_failure_skips_without_retry(self):
        fetcher = TwitterFetcher()
        fetcher._resolve_user_id = MagicMock(return_value=None)  # type: ignore[method-assign]
        fetcher._load_graphql_ops = MagicMock(return_value={})  # type: ignore[method-assign]

        response = MagicMock(status_code=503, text="")
        fetcher.session.get = MagicMock(return_value=response)

        window = FetchWindow(
            after=datetime(2026, 1, 1, tzinfo=timezone.utc),
            before=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )
        posts = fetcher.fetch_user("demo", window=window)
        self.assertEqual(posts, [])
        self.assertEqual(fetcher.last_stats.pages_skipped, 1)
        self.assertEqual(fetcher.session.get.call_count, 1)

    def test_graphql_page_failure_skips_without_retry(self):
        fetcher = TwitterFetcher()
        fetcher._resolve_user_id = MagicMock(return_value="123")  # type: ignore[method-assign]
        fetcher._load_graphql_ops = MagicMock(return_value={"UserTweets": ("qid", {}, {})})  # type: ignore[method-assign]
        fetcher._guest_headers = MagicMock(return_value={})  # type: ignore[method-assign]

        guest = MagicMock()
        guest.status_code = 422
        guest.text = "fail"
        syndication = MagicMock(status_code=200, text="no next data")
        fetcher.session.get = MagicMock(side_effect=[guest, syndication])

        window = FetchWindow(
            after=datetime(2026, 1, 1, tzinfo=timezone.utc),
            before=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )
        posts = fetcher.fetch_user("demo", window=window)
        self.assertEqual(posts, [])
        self.assertEqual(fetcher.last_stats.pages_skipped, 2)
        self.assertEqual(fetcher.session.get.call_count, 2)


if __name__ == "__main__":
    unittest.main()
