"""Tests for multi-account combined X API incremental fetch."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from stock_detect.fetch_window import FetchStats, FetchWindow
from stock_detect.models import SocialPost
from stock_detect.twitter_fetcher import TwitterFetcher
from stock_detect.x_api_client import XApiClient, XApiCredentials


class CombinedFetchTests(unittest.TestCase):
    def test_build_from_users_query(self):
        query = XApiClient.build_from_users_query(
            ["elonmusk", "justinsuntron", "mingchikuo"],
        )
        self.assertEqual(
            query,
            "(from:elonmusk OR from:justinsuntron OR from:mingchikuo) -is:retweet",
        )
        self.assertEqual(
            XApiClient.build_from_users_query(["solo"]),
            "from:solo -is:retweet",
        )

    def test_combined_incremental_uses_one_search_page_for_all_accounts(self):
        fetcher = TwitterFetcher()
        fetcher.x_api.is_configured = MagicMock(return_value=True)  # type: ignore[method-assign]
        fetcher.x_api.credentials.auth_mode = MagicMock(return_value="oauth2_bearer")  # type: ignore[method-assign]
        fetcher.x_api.resolve_user_ids = MagicMock(return_value={})  # type: ignore[method-assign]

        window = FetchWindow(
            after=datetime(2026, 4, 19, tzinfo=timezone.utc),
            before=datetime(2026, 6, 21, tzinfo=timezone.utc),
        )
        page = [
            SocialPost(
                "901",
                "new elon",
                "elonmusk",
                "x",
                datetime(2026, 6, 20, tzinfo=timezone.utc),
                0,
                "",
                [],
            ),
            SocialPost(
                "902",
                "new justin",
                "justinsuntron",
                "x",
                datetime(2026, 6, 20, tzinfo=timezone.utc),
                0,
                "",
                [],
            ),
        ]
        fetcher.x_api.iter_search_recent_pages = MagicMock(return_value=iter([page]))  # type: ignore[method-assign]

        cache = MagicMock()
        cache.available = True
        cache.ensure_schema = MagicMock()
        cache.get_state = MagicMock(
            side_effect=[
                MagicMock(user_id="1", last_tweet_id="900"),
                MagicMock(user_id="2", last_tweet_id="800"),
                MagicMock(user_id="1", last_tweet_id="900"),
                MagicMock(user_id="2", last_tweet_id="800"),
            ]
        )
        cache.list_posts = MagicMock(return_value=[MagicMock()])
        cache.insert_posts_batch = MagicMock(return_value=(1, 0))
        cache.save_state = MagicMock()
        cache.record_ci_scan = MagicMock()

        fetcher._fetch_account_cached = MagicMock(  # type: ignore[method-assign]
            side_effect=[
                [MagicMock(id="900")],
                [MagicMock(id="800")],
            ]
        )
        fetcher._fetch_combined_incremental = MagicMock(return_value=2)  # type: ignore[method-assign]

        stats = FetchStats()
        posts = fetcher._fetch_accounts_cached_combined(
            ["elonmusk", "justinsuntron"],
            window=window,
            max_pages=8,
            max_posts=100,
            stats=stats,
            cache=cache,
        )

        fetcher._fetch_account_cached.assert_any_call(
            "elonmusk",
            window=window,
            max_pages=8,
            max_posts=100,
            stats=stats,
            cache=cache,
            skip_incremental=True,
            skip_ci_scan=True,
        )
        fetcher._fetch_combined_incremental.assert_called_once()
        self.assertEqual(len(posts), 2)
        self.assertEqual(cache.record_ci_scan.call_count, 2)


class XApiSearchTests(unittest.TestCase):
    def test_iter_search_recent_pages_parses_authors(self):
        creds = XApiCredentials(bearer_token="token")
        client = XApiClient(credentials=creds)
        window = FetchWindow(
            after=datetime(2026, 4, 1, tzinfo=timezone.utc),
            before=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )
        stats = FetchStats()

        resp = MagicMock(status_code=200)
        resp.json.return_value = {
            "data": [
                {
                    "id": "100",
                    "author_id": "11",
                    "text": "$TRX",
                    "created_at": "2026-05-01T10:00:00.000Z",
                    "public_metrics": {"like_count": 1},
                    "entities": {"cashtags": [{"tag": "TRX"}]},
                }
            ],
            "includes": {
                "users": [{"id": "11", "username": "justinsuntron"}],
            },
            "meta": {},
        }
        client.session.get = MagicMock(return_value=resp)

        with patch("stock_detect.x_api_client.time.sleep"):
            pages = list(
                client.iter_search_recent_pages(
                    ["justinsuntron", "elonmusk"],
                    window=window,
                    max_pages=1,
                    max_posts=100,
                    stats=stats,
                    since_id="50",
                )
            )

        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0][0].author, "justinsuntron")
        self.assertEqual(stats.pages_fetched, 1)
        call_params = client.session.get.call_args.kwargs["params"]
        self.assertIn("from:justinsuntron OR from:elonmusk", call_params["query"])
        self.assertEqual(call_params["since_id"], "50")
        self.assertEqual(call_params["max_results"], 100)


if __name__ == "__main__":
    unittest.main()
