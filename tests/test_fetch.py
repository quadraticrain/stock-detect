"""Tests for fetch window and paginated fetchers."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from stock_detect.fetch_window import FetchWindow, default_fetch_window, filter_to_window, gap_window_before
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

    def test_gap_window_before(self):
        window = FetchWindow(
            after=datetime(2026, 4, 19, tzinfo=timezone.utc),
            before=datetime(2026, 6, 21, tzinfo=timezone.utc),
        )
        gap = gap_window_before(window, datetime(2026, 6, 16, tzinfo=timezone.utc))
        self.assertIsNotNone(gap)
        assert gap is not None
        self.assertEqual(gap.after, window.after)
        self.assertEqual(gap.before, datetime(2026, 6, 16, tzinfo=timezone.utc))
        self.assertIsNone(
            gap_window_before(window, datetime(2026, 4, 10, tzinfo=timezone.utc))
        )


class TwitterFetcherTests(unittest.TestCase):
    def _guest_only_fetcher(self) -> TwitterFetcher:
        fetcher = TwitterFetcher()
        fetcher.x_api.is_configured = MagicMock(return_value=False)  # type: ignore[method-assign]
        return fetcher

    def test_syndication_failure_skips_without_retry(self):
        fetcher = self._guest_only_fetcher()
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
        fetcher = self._guest_only_fetcher()
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

    def test_cached_fetch_skips_covered_window_and_only_backfills_gap(self):
        fetcher = TwitterFetcher()
        fetcher.x_api.is_configured = MagicMock(return_value=True)  # type: ignore[method-assign]

        window = FetchWindow(
            after=datetime(2026, 4, 19, tzinfo=timezone.utc),
            before=datetime(2026, 6, 21, tzinfo=timezone.utc),
        )
        cached_recent = SocialPost(
            "900",
            "recent",
            "demo",
            "x",
            datetime(2026, 6, 16, tzinfo=timezone.utc),
            0,
            "",
            [],
        )
        gap_post = SocialPost(
            "100",
            "old",
            "demo",
            "x",
            datetime(2026, 5, 1, tzinfo=timezone.utc),
            0,
            "",
            [],
        )

        cache = MagicMock()
        cache.available = True
        cache.ensure_schema = MagicMock()
        cache.list_posts = MagicMock(
            side_effect=[[cached_recent], [cached_recent, gap_post], [cached_recent, gap_post]]
        )
        cache.get_state = MagicMock(
            return_value=MagicMock(user_id="999", last_tweet_id="900")
        )
        cache.upsert_posts = MagicMock(return_value=1)
        cache.save_state = MagicMock()
        cache.prune_before = MagicMock(return_value=0)

        gap_calls: list[FetchWindow] = []
        incremental_calls: list[str | None] = []

        def fake_timeline(
            _screen_name,
            *,
            window,
            max_pages,
            max_posts,
            stats,
            since_id=None,
            user_id=None,
        ):
            if since_id:
                incremental_calls.append(since_id)
                return []
            gap_calls.append(window)
            return [gap_post]

        fetcher.x_api.fetch_user_timeline = MagicMock(side_effect=fake_timeline)  # type: ignore[method-assign]
        fetcher.x_api.credentials.auth_mode = MagicMock(return_value="oauth2_bearer")  # type: ignore[method-assign]

        posts = fetcher._fetch_account_cached(
            "demo",
            window=window,
            max_pages=10,
            max_posts=100,
            stats=fetcher.last_stats,
            cache=cache,
        )

        self.assertEqual(len(gap_calls), 1)
        self.assertEqual(gap_calls[0].after, window.after)
        self.assertEqual(gap_calls[0].before, cached_recent.created)
        self.assertEqual(incremental_calls, ["900"])
        self.assertEqual({p.id for p in posts}, {"100", "900"})
        fetcher.x_api.fetch_user_timeline.assert_called()


if __name__ == "__main__":
    unittest.main()
