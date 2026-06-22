#!/usr/bin/env python3
"""Backfill X posts older than the 63-day window into MySQL via guest fetchers."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stock_detect.config import DEFAULT_X_ACCOUNTS, MAX_FETCH_PAGES, MAX_FETCH_POSTS  # noqa: E402
from stock_detect.env import bootstrap  # noqa: E402
from stock_detect.fetch_window import default_fetch_window  # noqa: E402
from stock_detect.tweet_cache import TweetCache  # noqa: E402
from stock_detect.twitter_fetcher import TwitterFetcher  # noqa: E402


def main() -> int:
    bootstrap()
    parser = argparse.ArgumentParser(
        description="Backfill pre-63-day X posts into MySQL (guest/syndication, no API billing)"
    )
    parser.add_argument(
        "--accounts",
        default=",".join(DEFAULT_X_ACCOUNTS),
        help="Comma-separated X screen names",
    )
    parser.add_argument(
        "--before",
        help="Only posts before this date (YYYY-MM-DD). Default: start of current 63-day window",
    )
    parser.add_argument(
        "--after",
        help="Only posts after this date (YYYY-MM-DD). Default: 2006-03-21 (Twitter launch)",
    )
    parser.add_argument("--max-pages", type=int, default=MAX_FETCH_PAGES)
    parser.add_argument("--max-posts", type=int, default=MAX_FETCH_POSTS)
    parser.add_argument("--batch-size", type=int, default=100, help="MySQL insert batch size")
    parser.add_argument("--dry-run", action="store_true", help="Fetch only, do not write MySQL")
    args = parser.parse_args()

    cache = TweetCache()
    if not cache.available and not args.dry_run:
        print("Error: MYSQL_PASSWORD not set or pymysql missing", file=sys.stderr)
        return 1

    ci_window = default_fetch_window()
    before = (
        datetime.strptime(args.before, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if args.before
        else ci_window.after
    )
    after = (
        datetime.strptime(args.after, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if args.after
        else datetime(2006, 3, 21, tzinfo=timezone.utc)
    )

    accounts = [a.strip().lstrip("@").lower() for a in args.accounts.split(",") if a.strip()]
    fetcher = TwitterFetcher()

    print(f"History window: {after.date()} .. {before.date()} (exclusive upper = before 63-day CI start)")
    print(f"Accounts: {', '.join(accounts)}")

    if not args.dry_run:
        cache.ensure_schema()

    total_fetched = 0
    total_inserted = 0
    total_skipped = 0

    for account in accounts:
        posts, stats = fetcher.fetch_guest_history(
            account,
            before=before,
            after=after,
            max_pages=args.max_pages,
            max_posts=args.max_posts,
        )
        # Guest syndication may return recent tweets; keep only pre-63-day-window posts.
        posts = [p for p in posts if p.created < before]
        total_fetched += len(posts)
        streams = stats.streams_used or []
        print(
            f"\n@{account}: fetched {len(posts)} posts "
            f"(pages={stats.pages_fetched}, streams={streams or 'none'})"
        )
        if posts:
            oldest = min(p.created for p in posts)
            newest = max(p.created for p in posts)
            print(f"  range: {oldest.date()} .. {newest.date()}")

        if args.dry_run or not posts:
            continue

        inserted, skipped = cache.insert_posts_batch(
            posts,
            batch_size=args.batch_size,
            skip_existing=True,
        )
        total_inserted += inserted
        total_skipped += skipped
        print(f"  mysql: inserted={inserted}, skipped_existing={skipped}")

    print(
        f"\nDone. fetched={total_fetched} inserted={total_inserted} "
        f"skipped_existing={total_skipped}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
