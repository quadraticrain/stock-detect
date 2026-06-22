#!/usr/bin/env python3
"""Report MySQL tweet coverage for accounts and a lookback window."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stock_detect.config import FETCH_WINDOW_DAYS, X_API_MAX_DAYS  # noqa: E402
from stock_detect.env import bootstrap  # noqa: E402
from stock_detect.fetch_window import default_fetch_window, x_api_earliest  # noqa: E402
from stock_detect.tweet_cache import TweetCache  # noqa: E402


def main() -> int:
    bootstrap()
    parser = argparse.ArgumentParser(description="MySQL tweet coverage report")
    parser.add_argument("--accounts", required=True, help="Comma-separated X screen names")
    parser.add_argument(
        "--window-days",
        type=int,
        default=FETCH_WINDOW_DAYS,
        help="Target lookback window in days",
    )
    args = parser.parse_args()

    cache = TweetCache()
    if not cache.available:
        print("Error: MYSQL_PASSWORD not set or pymysql missing", file=sys.stderr)
        return 1

    accounts = [a.strip().lstrip("@").lower() for a in args.accounts.split(",") if a.strip()]
    window = default_fetch_window(window_days=args.window_days)
    api_floor = x_api_earliest(before=window.before)

    print(f"Target window: {window.after.date()} .. {window.before.date()} ({args.window_days} days)")
    print(f"X API floor (~{X_API_MAX_DAYS}d): {api_floor.date()}")
    print()

    for account in accounts:
        posts = cache.list_posts(account, window)
        total = cache.account_created_bounds(account)
        print(f"@{account}")
        print(f"  all-time in MySQL: min={_fmt(total[0])} max={_fmt(total[1])}")

        if not posts:
            print("  in-window posts: 0")
            print("  coverage: 0% (no data in target window)")
            print()
            continue

        oldest = min(p.created for p in posts)
        newest = max(p.created for p in posts)
        span_days = max(0, (newest - oldest).days)
        target_span = max(1, (window.before - window.after).days)
        coverage_pct = min(100.0, span_days / target_span * 100.0)

        pre_api = sum(1 for p in posts if p.created < api_floor)
        api_range = sum(1 for p in posts if p.created >= api_floor)

        print(f"  in-window posts: {len(posts)}")
        print(f"  oldest: {_fmt(oldest)}  newest: {_fmt(newest)}")
        print(f"  span: {span_days} days / target {target_span} days ({coverage_pct:.1f}%)")
        print(f"  by source era: guest-era (<{api_floor.date()})={pre_api}, api-era (>={api_floor.date()})={api_range}")

        gap_to_start = (oldest - window.after).days
        if gap_to_start > 0:
            print(f"  gap at window start: {gap_to_start} days missing before oldest cached post")
        elif oldest <= window.after:
            print("  window start: reached (oldest post at or before window.after)")

        if span_days >= target_span - 1:
            print("  verdict: FULL window coverage (within 1 day)")
        elif span_days >= X_API_MAX_DAYS - 1 and pre_api == 0:
            print(f"  verdict: API-era only (~{X_API_MAX_DAYS}d max); guest backfill needed for older range")
        else:
            print("  verdict: PARTIAL — likely hit page/post caps or guest depth limits")
        print()

    return 0


def _fmt(moment: datetime | None) -> str:
    if moment is None:
        return "—"
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


if __name__ == "__main__":
    raise SystemExit(main())
