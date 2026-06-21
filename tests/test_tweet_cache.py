"""Tests for MySQL tweet cache (mocked connection)."""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from stock_detect.fetch_window import FetchWindow
from stock_detect.models import SocialPost
from stock_detect.tweet_cache import TweetCache, init_mysql_cache


class TweetCacheTests(unittest.TestCase):
    def _sample_post(self, post_id: str = "100") -> SocialPost:
        return SocialPost(
            id=post_id,
            text="$AAPL buy",
            author="demo",
            source="x",
            created=datetime(2026, 6, 1, tzinfo=timezone.utc),
            score=3,
            url="https://x.com/demo/status/100",
            tickers=["AAPL"],
        )

    @patch("stock_detect.tweet_cache.pymysql.connect")
    def test_upsert_uses_insert_ignore(self, mock_connect):
        conn = MagicMock()
        cursor = MagicMock()
        cursor.rowcount = 1
        conn.cursor.return_value.__enter__.return_value = cursor
        mock_connect.return_value = conn

        cache = TweetCache(password="secret")
        inserted = cache.upsert_posts([self._sample_post()])

        self.assertEqual(inserted, 1)
        sql = cursor.execute.call_args[0][0]
        self.assertIn("INSERT IGNORE", sql)

    @patch("stock_detect.tweet_cache.pymysql.connect")
    def test_list_posts_maps_rows(self, mock_connect):
        conn = MagicMock()
        cursor = MagicMock()
        cursor.fetchall.return_value = [
            {
                "post_id": "100",
                "author": "demo",
                "text": "$AAPL buy",
                "created_at": datetime(2026, 6, 1, 12, 0, 0),
                "score": 3,
                "url": "https://x.com/demo/status/100",
                "tickers": json.dumps(["AAPL"]),
                "source": "x",
            }
        ]
        conn.cursor.return_value.__enter__.return_value = cursor
        mock_connect.return_value = conn

        window = FetchWindow(
            after=datetime(2026, 1, 1, tzinfo=timezone.utc),
            before=datetime(2026, 12, 31, tzinfo=timezone.utc),
        )
        cache = TweetCache(password="secret")
        posts = cache.list_posts("demo", window)

        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].id, "100")
        self.assertEqual(posts[0].tickers, ["AAPL"])

    def test_unavailable_without_password(self):
        cache = TweetCache(password="")
        self.assertFalse(cache.available)

    @patch("stock_detect.tweet_cache.pymysql.connect")
    def test_sync_schema_adds_missing_column(self, mock_connect):
        conn = MagicMock()
        cursor = MagicMock()

        def fetchall_side_effect():
            sql = cursor.execute.call_args[0][0]
            if "information_schema.columns" in sql and "stock_detect_x_posts" in str(cursor.execute.call_args[0][1]):
                return [{"column_name": "post_id"}, {"column_name": "author"}]
            if "information_schema.statistics" in sql:
                return [{"index_name": "PRIMARY"}]
            return []

        cursor.fetchall.side_effect = lambda: fetchall_side_effect()
        conn.cursor.return_value.__enter__.return_value = cursor
        mock_connect.return_value = conn

        cache = TweetCache(password="secret")
        cache.sync_schema(force=True)

        alter_calls = [
            call.args[0]
            for call in cursor.execute.call_args_list
            if call.args and str(call.args[0]).startswith("ALTER TABLE")
        ]
        self.assertTrue(any("ADD COLUMN source" in sql for sql in alter_calls))

    @patch.dict("os.environ", {}, clear=True)
    @patch("stock_detect.tweet_cache.pymysql.connect")
    def test_init_mysql_cache_returns_false_without_password(self, mock_connect):
        import stock_detect.tweet_cache as tc

        tc._schema_synced = False
        self.assertFalse(init_mysql_cache())
        mock_connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
