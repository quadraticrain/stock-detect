"""Tests for SocialPost helpers."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from stock_detect.models import SocialPost, sort_posts_chronological


class SortPostsChronologicalTests(unittest.TestCase):
    def test_orders_by_created_then_post_id(self):
        posts = [
            SocialPost(
                "300",
                "new",
                "demo",
                "x",
                datetime(2026, 6, 3, tzinfo=timezone.utc),
                0,
                "",
            ),
            SocialPost(
                "100",
                "old",
                "demo",
                "x",
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                0,
                "",
            ),
            SocialPost(
                "200",
                "mid",
                "demo",
                "x",
                datetime(2026, 3, 1, tzinfo=timezone.utc),
                0,
                "",
            ),
        ]
        ordered = sort_posts_chronological(posts)
        self.assertEqual([p.id for p in ordered], ["100", "200", "300"])


if __name__ == "__main__":
    unittest.main()
