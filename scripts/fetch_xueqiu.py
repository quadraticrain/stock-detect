#!/usr/bin/env python3
"""Fetch Xueqiu user timelines into MySQL."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stock_detect.config import CI_SCHEDULED_XUEQIU_USERS, FETCH_WINDOW_DAYS, MAX_FETCH_PAGES, MAX_FETCH_POSTS  # noqa: E402
from stock_detect.env import bootstrap  # noqa: E402
from stock_detect.fetch_window import default_fetch_window  # noqa: E402
from stock_detect.tweet_cache import TweetCache  # noqa: E402
from stock_detect.xueqiu_fetcher import XueqiuFetcher  # noqa: E402


def _users(value: str) -> list[str]:
    return [user.strip() for user in value.split(",") if user.strip()]


def main() -> int:
    bootstrap()
    parser = argparse.ArgumentParser(description="Fetch Xueqiu posts into MySQL")
    parser.add_argument("--users", default=",".join(CI_SCHEDULED_XUEQIU_USERS))
    parser.add_argument("--window-days", type=int, default=FETCH_WINDOW_DAYS)
    parser.add_argument("--limit", type=int, default=MAX_FETCH_POSTS)
    parser.add_argument("--max-pages", type=int, default=MAX_FETCH_PAGES)
    args = parser.parse_args()

    cache = TweetCache()
    if not cache.available:
        print("MySQL unavailable; set MYSQL_PASSWORD", file=sys.stderr)
        return 2
    cache.sync_schema()

    fetcher = XueqiuFetcher()
    window = default_fetch_window(window_days=args.window_days)
    total = inserted = skipped = 0
    for user_id in _users(args.users):
        posts = fetcher.fetch_user_posts(user_id, window=window, max_pages=args.max_pages, max_posts=args.limit)
        new_count, skipped_count = cache.insert_posts_batch(posts)
        total += len(posts)
        inserted += new_count
        skipped += skipped_count
        print(f"xueqiu user={user_id} fetched={len(posts)} inserted={new_count} skipped={skipped_count}")

    print(f"Xueqiu OK: posts={total} inserted={inserted} skipped={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
