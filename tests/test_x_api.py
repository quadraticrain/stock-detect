"""Tests for official X API v2 client."""

from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from stock_detect.fetch_window import FetchStats, FetchWindow
from stock_detect.x_api_client import XApiClient, XApiCredentials, _tweet_v2_to_post


class XApiCredentialsTests(unittest.TestCase):
    def test_bearer_from_env(self):
        with patch.dict(os.environ, {"X_BEARER_TOKEN": "test-token"}, clear=True):
            creds = XApiCredentials.from_env()
            self.assertTrue(creds.is_configured())
            self.assertEqual(creds.auth_mode(), "oauth2_bearer")

    def test_oauth1_requires_all_four_keys(self):
        with patch.dict(
            os.environ,
            {"X_API_KEY": "k", "X_API_SECRET": "s"},
            clear=True,
        ), patch("stock_detect.x_api_client.config.X_CLIENT_ID", ""), patch(
            "stock_detect.x_api_client.config.X_CLIENT_SECRET", ""
        ):
            creds = XApiCredentials.from_env()
            self.assertFalse(creds.is_configured())

    def test_client_credentials_configured(self):
        with patch.dict(
            os.environ,
            {"X_CLIENT_ID": "id", "X_CLIENT_SECRET": "secret"},
            clear=True,
        ):
            creds = XApiCredentials.from_env()
            self.assertTrue(creds.is_configured())
            self.assertEqual(creds.auth_mode(), "oauth2_client_credentials")


class XApiClientTests(unittest.TestCase):
    def test_parse_timeline_tweet(self):
        post = _tweet_v2_to_post(
            {
                "id": "1",
                "text": "Bullish on $NVDA",
                "created_at": "2026-06-21T12:00:00.000Z",
                "public_metrics": {"like_count": 42},
                "entities": {"cashtags": [{"tag": "NVDA"}]},
            },
            "aleabitoreddit",
        )
        self.assertIsNotNone(post)
        assert post is not None
        self.assertEqual(post.tickers, ["NVDA"])
        self.assertEqual(post.score, 42)

    def test_fetch_user_timeline_pagination(self):
        creds = XApiCredentials(bearer_token="token")
        client = XApiClient(credentials=creds)
        window = FetchWindow(
            after=datetime(2026, 4, 1, tzinfo=timezone.utc),
            before=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )
        stats = FetchStats()

        user_resp = MagicMock(status_code=200)
        user_resp.json.return_value = {"data": {"id": "999", "username": "demo"}}

        page1 = MagicMock(status_code=200)
        page1.json.return_value = {
            "data": [
                {
                    "id": "100",
                    "text": "$AMD buy",
                    "created_at": "2026-05-01T10:00:00.000Z",
                    "public_metrics": {"like_count": 1},
                    "entities": {"cashtags": [{"tag": "AMD"}]},
                }
            ],
            "meta": {"next_token": "cursor-2"},
        }
        page2 = MagicMock(status_code=200)
        page2.json.return_value = {
            "data": [
                {
                    "id": "101",
                    "text": "$NVDA",
                    "created_at": "2026-04-20T10:00:00.000Z",
                    "public_metrics": {"like_count": 2},
                    "entities": {"cashtags": [{"tag": "NVDA"}]},
                }
            ],
            "meta": {},
        }

        client.session.get = MagicMock(side_effect=[user_resp, page1, page2])

        with patch("stock_detect.x_api_client.time.sleep"):
            posts = client.fetch_user_timeline(
                "demo",
                window=window,
                max_pages=5,
                max_posts=100,
                stats=stats,
            )

        self.assertEqual(len(posts), 2)
        self.assertEqual(stats.pages_fetched, 2)
        self.assertEqual(client.session.get.call_count, 3)

    def test_api_failure_skips_without_retry(self):
        creds = XApiCredentials(bearer_token="token")
        client = XApiClient(credentials=creds)
        window = FetchWindow(
            after=datetime(2026, 4, 1, tzinfo=timezone.utc),
            before=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )
        stats = FetchStats()

        user_resp = MagicMock(status_code=200)
        user_resp.json.return_value = {"data": {"id": "999"}}
        fail_resp = MagicMock(status_code=401, text="unauthorized")
        client.session.get = MagicMock(side_effect=[user_resp, fail_resp])

        posts = client.fetch_user_timeline(
            "demo",
            window=window,
            max_pages=3,
            max_posts=100,
            stats=stats,
        )
        self.assertEqual(posts, [])
        self.assertEqual(stats.pages_skipped, 1)
        self.assertEqual(client.session.get.call_count, 2)


if __name__ == "__main__":
    unittest.main()
