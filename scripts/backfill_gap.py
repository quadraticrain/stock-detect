#!/usr/bin/env python3
"""Backfill the gap between guest historical data and CI 63-day window via X API."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stock_detect.config import (  # noqa: E402
    DEFAULT_X_ACCOUNTS,
    MAX_FETCH_PAGES,
    MAX_FETCH_POSTS,
    X_API_TIMELINE_EXCLUDES,
)
from stock_detect.env import bootstrap  # noqa: E402
from stock_detect.fetch_window import FetchStats, FetchWindow, default_fetch_window  # noqa: E402
from stock_detect.models import SocialPost  # noqa: E402
from stock_detect.tweet_cache import TweetCache  # noqa: E402
from stock_detect.twitter_fetcher import TwitterFetcher  # noqa: E402


def _parse_dt(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def _aware(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _in_gap(post: SocialPost, gap_after: datetime, gap_before: datetime) -> bool:
    created = _aware(post.created)
    return gap_after < created < gap_before


def _flush_buffer(
    cache: TweetCache,
    buffer: list[SocialPost],
    *,
    dry_run: bool,
    batch_size: int,
) -> tuple[int, int]:
    if not buffer or dry_run:
        return 0, 0 if dry_run else 0
    by_id = {p.id: p for p in buffer}
    return cache.insert_posts_batch(list(by_id.values()), batch_size=batch_size, skip_existing=True)


def main() -> int:
    bootstrap()
    parser = argparse.ArgumentParser(
        description=(
            "Fill MySQL gap between guest historical newest and CI-window oldest "
            "using official X API (batched pages + post_id dedup)"
        )
    )
    parser.add_argument(
        "--accounts",
        default=",".join(DEFAULT_X_ACCOUNTS),
        help="Comma-separated X screen names",
    )
    parser.add_argument(
        "--after",
        help="Gap lower bound YYYY-MM-DD (default: auto from MySQL guest newest)",
    )
    parser.add_argument(
        "--before",
        help="Gap upper bound YYYY-MM-DD (default: auto from MySQL CI oldest)",
    )
    parser.add_argument(
        "--pages-per-batch",
        type=int,
        default=5,
        help="Flush to MySQL after this many X API pages",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=MAX_FETCH_PAGES,
        help="Max X API pages per exclude pass",
    )
    parser.add_argument("--max-posts", type=int, default=MAX_FETCH_POSTS)
    parser.add_argument("--batch-size", type=int, default=100, help="MySQL insert batch size")
    parser.add_argument("--dry-run", action="store_true", help="Fetch only, do not write MySQL")
    args = parser.parse_args()

    cache = TweetCache()
    if not cache.available and not args.dry_run:
        print("Error: MYSQL_PASSWORD not set or pymysql missing", file=sys.stderr)
        return 1

    fetcher = TwitterFetcher()
    if not fetcher.x_api.is_configured():
        print("Error: X_BEARER_TOKEN (or OAuth) not configured", file=sys.stderr)
        return 1

    ci_window = default_fetch_window()
    accounts = [a.strip().lstrip("@").lower() for a in args.accounts.split(",") if a.strip()]

    if not args.dry_run:
        cache.ensure_schema()

    total_in_gap = 0
    total_inserted = 0
    total_skipped = 0

    for account in accounts:
        if args.after and args.before:
            gap_after = _parse_dt(args.after)
            gap_before = _parse_dt(args.before)
        else:
            detected = cache.detect_ci_gap_window(account, ci_window.after)
            if detected is None:
                print(f"\n@{account}: no gap detected (historical newest meets CI oldest)")
                continue
            gap_after, gap_before = detected

        gap_after = _aware(gap_after)
        gap_before = _aware(gap_before)
        api_floor = _aware(ci_window.after)

        if gap_after >= gap_before:
            print(f"\n@{account}: invalid gap bounds")
            continue

        if gap_before <= api_floor:
            print(
                f"\n@{account} gap: {gap_after.date()} .. {gap_before.date()}\n"
                f"  Note: entire gap is older than X API 63-day window (starts {api_floor.date()}). "
                f"Use scripts/backfill_history.py (guest) for this range; X API cannot reach it now."
            )
            continue

        api_gap_after = max(gap_after, api_floor)
        print(
            f"\n@{account} gap: {gap_after.date()} .. {gap_before.date()}\n"
            f"  X API will paginate from {api_floor.date()} and filter into gap; "
            f"posts before {api_floor.date()} need guest backfill."
        )

        window = FetchWindow(
            after=api_floor,
            before=ci_window.before,
            window_days=ci_window.window_days,
            api_start_time=True,
        )

        stats = FetchStats()
        stats.x_auth_mode = fetcher.x_api.credentials.auth_mode()
        user_id = fetcher.x_api.resolve_user_id(account, stats)
        if not user_id:
            print("  Error: could not resolve user_id", file=sys.stderr)
            continue

        state = cache.get_state(account)
        if state and state.user_id:
            user_id = state.user_id

        account_in_gap = 0
        account_inserted = 0
        account_skipped = 0
        buffer: list[SocialPost] = []
        pages_since_flush = 0
        api_batch = 0

        for exclude in X_API_TIMELINE_EXCLUDES or (None,):
            exclude_label = exclude or "none"
            print(f"  API pass exclude={exclude_label}")
            pages_since_flush = 0

            for page in fetcher.x_api.iter_timeline_pages(
                account,
                window=window,
                max_pages=args.max_pages,
                max_posts=args.max_posts,
                stats=stats,
                user_id=user_id,
                exclude=exclude,
            ):
                pages_since_flush += 1
                page_oldest = None
                for post in page:
                    created = _aware(post.created)
                    if page_oldest is None or created < page_oldest:
                        page_oldest = created
                    if _in_gap(post, gap_after, gap_before):
                        buffer.append(post)

                stop_pass = False
                if page_oldest is not None and page_oldest <= gap_after:
                    print(f"    reached gap lower bound at {page_oldest.date()}")
                    stop_pass = True

                if pages_since_flush >= args.pages_per_batch or stop_pass:
                    api_batch += 1
                    in_gap = len({p.id for p in buffer})
                    print(
                        f"    api batch {api_batch}: pages={pages_since_flush} "
                        f"in_gap={in_gap} total_api_pages={stats.pages_fetched}"
                    )
                    inserted, skipped = _flush_buffer(
                        cache, buffer, dry_run=args.dry_run, batch_size=args.batch_size
                    )
                    account_in_gap += in_gap
                    account_inserted += inserted
                    account_skipped += skipped
                    if not args.dry_run and in_gap:
                        print(f"      mysql: inserted={inserted}, skipped_existing={skipped}")
                    buffer = []
                    pages_since_flush = 0

                if stop_pass:
                    break

        if buffer:
            api_batch += 1
            in_gap = len({p.id for p in buffer})
            print(f"    api batch {api_batch} (final): in_gap={in_gap}")
            inserted, skipped = _flush_buffer(
                cache, buffer, dry_run=args.dry_run, batch_size=args.batch_size
            )
            account_in_gap += in_gap
            account_inserted += inserted
            account_skipped += skipped
            if not args.dry_run and in_gap:
                print(f"      mysql: inserted={inserted}, skipped_existing={skipped}")

        total_in_gap += account_in_gap
        total_inserted += account_inserted
        total_skipped += account_skipped
        print(
            f"  @{account} done: in_gap={account_in_gap} inserted={account_inserted} "
            f"skipped={account_skipped} api_pages={stats.pages_fetched}"
        )

    print(
        f"\nAll done. in_gap={total_in_gap} inserted={total_inserted} "
        f"skipped_existing={total_skipped}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
