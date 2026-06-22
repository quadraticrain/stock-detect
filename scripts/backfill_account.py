#!/usr/bin/env python3
"""Backfill missing tweet ranges for an account (guest + deep API gap fill)."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.import_tweet_archive import ACCOUNT_ARCHIVE_URLS  # noqa: E402
from stock_detect.config import (  # noqa: E402
    EXTENDED_MAX_FETCH_PAGES,
    EXTENDED_MAX_FETCH_POSTS,
    MAX_FETCH_PAGES,
    MAX_FETCH_POSTS,
    X_API_MAX_DAYS,
)
from stock_detect.env import bootstrap  # noqa: E402
from stock_detect.fetch_window import FetchWindow, default_fetch_window, x_api_earliest  # noqa: E402
from stock_detect.tweet_cache import TweetCache  # noqa: E402


def _month_starts(after: datetime, before: datetime) -> list[datetime]:
    cur = datetime(after.year, after.month, 1, tzinfo=timezone.utc)
    end = before if before.tzinfo else before.replace(tzinfo=timezone.utc)
    months: list[datetime] = []
    while cur < end:
        months.append(cur)
        if cur.month == 12:
            cur = datetime(cur.year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            cur = datetime(cur.year, cur.month + 1, 1, tzinfo=timezone.utc)
    return months


def detect_sparse_months(
    cache: TweetCache,
    account: str,
    window: FetchWindow,
) -> list[tuple[datetime, datetime]]:
    """Return month ranges inside window with zero cached posts."""
    posts = cache.list_posts(account, window)
    by_month = {p.created.strftime("%Y-%m") for p in posts}
    gaps: list[tuple[datetime, datetime]] = []
    for start in _month_starts(window.after, window.before):
        key = start.strftime("%Y-%m")
        if key in by_month:
            continue
        if start.month == 12:
            end = datetime(start.year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            end = datetime(start.year, start.month + 1, 1, tzinfo=timezone.utc)
        end = min(end, window.before)
        if end <= start:
            continue
        gaps.append((start, end))
    return gaps


def main() -> int:
    bootstrap()
    parser = argparse.ArgumentParser(description="Fill missing ranges for an X account in MySQL")
    parser.add_argument("--accounts", required=True)
    parser.add_argument("--window-days", type=int, default=179)
    parser.add_argument("--max-pages", type=int, default=MAX_FETCH_PAGES)
    parser.add_argument("--max-posts", type=int, default=MAX_FETCH_POSTS)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    import subprocess

    pages = min(args.max_pages, EXTENDED_MAX_FETCH_PAGES)
    posts = min(args.max_posts, EXTENDED_MAX_FETCH_POSTS)
    window = default_fetch_window(window_days=args.window_days)
    api_floor = x_api_earliest(before=window.before)
    accounts = [a.strip().lstrip("@").lower() for a in args.accounts.split(",") if a.strip()]

    cache = TweetCache()
    if not cache.available and not args.dry_run:
        print("Error: MYSQL_PASSWORD not set", file=sys.stderr)
        return 1

    for account in accounts:
        print(f"\n=== @{account} window {window.after.date()} .. {window.before.date()} ===")

        if not args.dry_run:
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "extended_prefetch.py"),
                    "--accounts",
                    account,
                    "--window-days",
                    str(args.window_days),
                    "--max-pages",
                    str(pages),
                    "--max-posts",
                    str(posts),
                ],
                check=True,
            )

        hist_max = cache.account_created_bounds(account, created_before=window.after)[1]
        if hist_max and hist_max < window.after:
            gap_after = hist_max + timedelta(microseconds=1)
            gap_before = window.after
            print(f"Historical→window gap: {gap_after.date()} .. {gap_before.date()}")
            if not args.dry_run:
                subprocess.run(
                    [
                        sys.executable,
                        str(ROOT / "scripts" / "backfill_gap.py"),
                        "--accounts",
                        account,
                        "--after",
                        gap_after.strftime("%Y-%m-%d"),
                        "--before",
                        gap_before.strftime("%Y-%m-%d"),
                        "--max-pages",
                        str(pages),
                        "--max-posts",
                        str(posts),
                    ],
                    check=True,
                )

        sparse = detect_sparse_months(cache, account, window)
        archive_url = os.environ.get("TWEET_ARCHIVE_URL", "").strip() or ACCOUNT_ARCHIVE_URLS.get(account, "")
        if sparse and archive_url:
            print(f"Sparse months detected; importing archive {archive_url}")
            if not args.dry_run:
                subprocess.run(
                    [
                        sys.executable,
                        str(ROOT / "scripts" / "import_tweet_archive.py"),
                        "--accounts",
                        account,
                        "--window-days",
                        str(args.window_days),
                        "--archive-url",
                        archive_url,
                    ],
                    check=True,
                )
                sparse = detect_sparse_months(cache, account, window)

        for gap_after, gap_before in sparse:
            print(f"Sparse month gap: {gap_after.date()} .. {gap_before.date()}")
            if args.dry_run:
                continue
            if gap_before <= api_floor:
                subprocess.run(
                    [
                        sys.executable,
                        str(ROOT / "scripts" / "backfill_gap.py"),
                        "--accounts",
                        account,
                        "--after",
                        gap_after.strftime("%Y-%m-%d"),
                        "--before",
                        gap_before.strftime("%Y-%m-%d"),
                        "--max-pages",
                        str(pages),
                        "--max-posts",
                        str(posts),
                    ],
                    check=True,
                )
            else:
                subprocess.run(
                    [
                        sys.executable,
                        str(ROOT / "scripts" / "backfill_history.py"),
                        "--accounts",
                        account,
                        "--after",
                        gap_after.strftime("%Y-%m-%d"),
                        "--before",
                        gap_before.strftime("%Y-%m-%d"),
                        "--max-pages",
                        str(pages),
                        "--max-posts",
                        str(posts),
                    ],
                    check=True,
                )

        if not args.dry_run:
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "mysql_coverage.py"),
                    "--accounts",
                    account,
                    "--window-days",
                    str(args.window_days),
                ],
                check=True,
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
