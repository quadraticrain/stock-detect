#!/usr/bin/env python3
"""Analyze X posts from MySQL cache and emit report JSON (no fetch, no static site)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stock_detect.analyzer import SignalAnalyzer  # noqa: E402
from stock_detect.config import FETCH_WINDOW_DAYS  # noqa: E402
from stock_detect.ci_scan_metadata import merge_ci_scan_metadata  # noqa: E402
from stock_detect.env import bootstrap  # noqa: E402
from stock_detect.fetch_window import default_fetch_window  # noqa: E402
from stock_detect.report_payload import report_to_dict  # noqa: E402
from stock_detect.tweet_cache import TweetCache  # noqa: E402


def _parse_accounts(value: str) -> list[str]:
    return [a.strip().lstrip("@") for a in value.split(",") if a.strip()]


def analyze_from_cache(
    accounts: list[str],
    *,
    window_days: int = FETCH_WINDOW_DAYS,
    sp500_only: bool = False,
) -> dict:
    bootstrap()
    cache = TweetCache()
    window = default_fetch_window(window_days=window_days)
    posts = []
    for account in accounts:
        posts.extend(cache.list_posts(account, window))

    analyzer = SignalAnalyzer(x_accounts=accounts)
    report = analyzer.analyze(
        source="x",
        posts=posts,
        window_days=window_days,
        all_cashtags=not sp500_only,
        sp500_only=sp500_only,
    )
    payload = report_to_dict(report, accounts=accounts)
    return merge_ci_scan_metadata(payload, accounts, cache)


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze MySQL-cached X posts")
    parser.add_argument("--accounts", default="aleabitoreddit")
    parser.add_argument("--window-days", type=int, default=FETCH_WINDOW_DAYS)
    parser.add_argument("--sp500-only", action="store_true")
    args = parser.parse_args()

    accounts = _parse_accounts(args.accounts)
    payload = analyze_from_cache(
        accounts,
        window_days=args.window_days,
        sp500_only=args.sp500_only,
    )
    print(json.dumps(payload, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
