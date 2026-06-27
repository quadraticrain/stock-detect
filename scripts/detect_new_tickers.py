#!/usr/bin/env python3
"""Detect first-time ticker mentions in the last 24h and push Bark alerts.

Designed to run after the daily AI incremental analysis (Beijing 23:00).
Batch-processes multiple X accounts in one MySQL round-trip per time window.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stock_detect.config import (  # noqa: E402
    BARK_PUSH_URL,
    CI_SCHEDULED_X_ACCOUNTS_CSV,
    NEW_TICKER_LOOKBACK_HOURS,
    active_scheduled_x_accounts,
)
from stock_detect.env import bootstrap  # noqa: E402
from stock_detect.new_ticker_alert import (  # noqa: E402
    load_new_ticker_hits,
    push_bark_alerts,
)
from stock_detect.tweet_cache import TweetCache  # noqa: E402


def _parse_accounts(value: str) -> list[str]:
    return [a.strip().lstrip("@").lower() for a in value.split(",") if a.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Detect new tickers in recent posts and push Bark alerts",
    )
    parser.add_argument(
        "--accounts",
        default=",".join(active_scheduled_x_accounts()),
        help=f"Comma-separated X slugs (default: active CI accounts, full list: {CI_SCHEDULED_X_ACCOUNTS_CSV})",
    )
    parser.add_argument(
        "--lookback-hours",
        type=int,
        default=NEW_TICKER_LOOKBACK_HOURS,
        help="Recent window in hours (default: 24)",
    )
    parser.add_argument(
        "--bark-url",
        default=BARK_PUSH_URL,
        help="Bark push endpoint",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print hits as JSON without sending Bark notifications",
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="Send Bark notifications (default when not --dry-run)",
    )
    args = parser.parse_args()

    accounts = _parse_accounts(args.accounts)
    if not accounts:
        print("ERROR: no accounts specified", file=sys.stderr)
        return 1

    bootstrap()
    cache = TweetCache()
    if not cache.available:
        print("ERROR: MySQL cache is not configured (set MYSQL_PASSWORD)", file=sys.stderr)
        return 1

    hits = load_new_ticker_hits(
        cache,
        accounts,
        lookback_hours=args.lookback_hours,
    )

    payload = [
        {
            "author": hit.author,
            "ticker": hit.ticker,
            "post_id": hit.post_id,
            "post_url": hit.post_url,
            "created_at": hit.created_at.isoformat(),
        }
        for hit in hits
    ]
    print(json.dumps({"accounts": accounts, "hits": payload}, indent=2, ensure_ascii=False))

    should_push = args.push or not args.dry_run
    if should_push and hits:
        push_bark_alerts(hits, bark_url=args.bark_url, dry_run=args.dry_run)
        if not args.dry_run:
            print(f"Pushed {len(hits)} Bark alert(s)", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
