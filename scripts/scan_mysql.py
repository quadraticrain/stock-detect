#!/usr/bin/env python3
"""Fetch X timelines into MySQL (CI scan; no GitHub Pages)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stock_detect.analyzer import SignalAnalyzer  # noqa: E402
from stock_detect.config import (  # noqa: E402
    DISABLED_X_ACCOUNTS,
    EXTENDED_MAX_FETCH_PAGES,
    EXTENDED_MAX_FETCH_POSTS,
    FETCH_WINDOW_DAYS,
    MAX_FETCH_PAGES,
    MAX_FETCH_POSTS,
)
from stock_detect.env import bootstrap  # noqa: E402


def main() -> int:
    bootstrap()
    parser = argparse.ArgumentParser(description="Fetch X posts into MySQL")
    parser.add_argument("--source", choices=["x", "wsb", "both"], default="x")
    parser.add_argument("--accounts", default="aleabitoreddit")
    parser.add_argument("--window-days", type=int, default=FETCH_WINDOW_DAYS)
    parser.add_argument("--limit", type=int, default=MAX_FETCH_POSTS)
    parser.add_argument("--max-pages", type=int, default=MAX_FETCH_PAGES)
    args = parser.parse_args()

    requested_accounts = [a.strip().lstrip("@").lower() for a in args.accounts.split(",") if a.strip()]
    accounts = [a for a in requested_accounts if a not in DISABLED_X_ACCOUNTS]
    disabled = [a for a in requested_accounts if a in DISABLED_X_ACCOUNTS]
    if disabled:
        print(f"Skip disabled X accounts: {','.join(disabled)}", file=sys.stderr)
    if args.source in {"x", "both"} and not accounts:
        print("No enabled X accounts to fetch; exiting without touching MySQL.")
        return 0
    max_posts = min(args.limit, EXTENDED_MAX_FETCH_POSTS)
    max_pages = min(args.max_pages, EXTENDED_MAX_FETCH_PAGES)

    analyzer = SignalAnalyzer(x_accounts=accounts)
    report = analyzer.analyze(
        source=args.source,
        limit=max_posts,
        max_pages=max_pages,
        window_days=args.window_days,
    )
    stats = report.fetch_stats
    api_new = stats.api_posts_new if stats else None
    print(
        f"Scan OK: posts={report.fetched_posts} signals={len(report.signals)} "
        f"api_new={api_new} accounts={','.join(accounts)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
