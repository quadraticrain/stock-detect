#!/usr/bin/env python3
"""Guest-only prefetch for the pre-X-API portion of an extended lookback window."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stock_detect.config import (  # noqa: E402
    DISABLED_X_ACCOUNTS,
    EXTENDED_MAX_FETCH_PAGES,
    EXTENDED_MAX_FETCH_POSTS,
    MAX_FETCH_PAGES,
    MAX_FETCH_POSTS,
)
from stock_detect.env import bootstrap  # noqa: E402
from stock_detect.fetch_budget import extended_fetch_budget  # noqa: E402
from stock_detect.fetch_window import default_fetch_window, guest_backfill_window, x_api_earliest  # noqa: E402
from stock_detect.tweet_cache import TweetCache  # noqa: E402
from stock_detect.twitter_fetcher import TwitterFetcher  # noqa: E402


def main() -> int:
    bootstrap()
    parser = argparse.ArgumentParser(
        description="Iterative guest backfill for history older than the X API floor"
    )
    parser.add_argument("--accounts", required=True, help="Comma-separated X screen names")
    parser.add_argument("--window-days", type=int, required=True, help="Full lookback window")
    parser.add_argument("--max-pages", type=int, default=MAX_FETCH_PAGES)
    parser.add_argument("--max-posts", type=int, default=MAX_FETCH_POSTS)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    cache = TweetCache()
    if not cache.available and not args.dry_run:
        print("Error: MYSQL_PASSWORD not set or pymysql missing", file=sys.stderr)
        return 1

    window = default_fetch_window(window_days=args.window_days)
    budget = extended_fetch_budget(args.window_days, args.max_posts, args.max_pages)
    if budget.guest_pages <= 0:
        print(f"Window {args.window_days}d <= X API max; guest prefetch skipped.")
        return 0

    requested_accounts = [a.strip().lstrip("@").lower() for a in args.accounts.split(",") if a.strip()]
    accounts = [a for a in requested_accounts if a not in DISABLED_X_ACCOUNTS]
    disabled = [a for a in requested_accounts if a in DISABLED_X_ACCOUNTS]
    if disabled:
        print(f"Skip disabled X accounts: {','.join(disabled)}", file=sys.stderr)
    if not accounts:
        print("No enabled X accounts to prefetch; exiting without touching MySQL.")
        return 0
    fetcher = TwitterFetcher()
    api_floor = x_api_earliest(before=window.before)

    print(
        f"Extended prefetch: window={window.after.date()}..{window.before.date()} "
        f"({args.window_days}d), guest budget pages={budget.guest_pages} "
        f"posts={budget.guest_posts} passes={budget.guest_passes}"
    )
    print(f"X API floor: {api_floor.date()}")

    if not args.dry_run:
        cache.ensure_schema()

    total_inserted = 0
    for account in accounts:
        print(f"\n@{account}")
        account_inserted = 0
        for pass_no in range(1, budget.guest_passes + 1):
            cached = cache.list_posts(account, window) if cache.available else []
            oldest = min((p.created for p in cached), default=None)
            guest_window = guest_backfill_window(window, oldest)
            if guest_window is None:
                print(f"  pass {pass_no}: guest range covered")
                break

            print(
                f"  pass {pass_no}: guest {guest_window.after.date()} .. "
                f"{guest_window.before.date()}"
            )
            posts, stats = fetcher.fetch_guest_history(
                account,
                before=guest_window.before,
                after=guest_window.after,
                max_pages=budget.guest_pages,
                max_posts=budget.guest_posts,
            )
            posts = [
                p
                for p in posts
                if guest_window.after <= p.created < guest_window.before
            ]
            print(
                f"    fetched={len(posts)} pages={stats.pages_fetched} "
                f"streams={stats.streams_used or 'none'}"
            )
            if posts:
                oldest_p = min(p.created for p in posts)
                newest_p = max(p.created for p in posts)
                print(f"    batch range: {oldest_p.date()} .. {newest_p.date()}")

            if args.dry_run or not posts:
                if not posts:
                    break
                continue

            inserted, skipped = cache.insert_posts_batch(
                posts,
                batch_size=args.batch_size,
                skip_existing=True,
            )
            account_inserted += inserted
            print(f"    mysql: inserted={inserted} skipped={skipped}")
            if inserted == 0 and skipped == len(posts):
                break

        total_inserted += account_inserted
        if cache.available:
            cached = cache.list_posts(account, window)
            if cached:
                oldest = min(p.created for p in cached)
                print(f"  window oldest after prefetch: {oldest.date()}")

    print(f"\nDone. total_inserted={total_inserted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
