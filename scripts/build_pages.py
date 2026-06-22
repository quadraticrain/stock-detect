#!/usr/bin/env python3
"""Run scan and write static site for GitHub Pages."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stock_detect.analyzer import SignalAnalyzer  # noqa: E402
from stock_detect.config import (  # noqa: E402
    EXTENDED_MAX_FETCH_PAGES,
    EXTENDED_MAX_FETCH_POSTS,
    FETCH_WINDOW_DAYS,
    MAX_FETCH_PAGES,
    MAX_FETCH_POSTS,
)
from stock_detect.env import bootstrap  # noqa: E402
from stock_detect.report import refresh_site, write_site  # noqa: E402


def main() -> int:
    bootstrap()
    parser = argparse.ArgumentParser(description="Build GitHub Pages report")
    parser.add_argument("--output", default="site", help="Output directory")
    parser.add_argument("--merge-from", help="Existing gh-pages dir to preserve history")
    parser.add_argument("--source", choices=["x", "wsb", "both"], default="x")
    parser.add_argument("--accounts", default="aleabitoreddit")
    parser.add_argument(
        "--window-days",
        type=int,
        default=FETCH_WINDOW_DAYS,
        help="Lookback window in days (X API covers ~63; older uses guest backfill)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=MAX_FETCH_POSTS,
        help="Max posts to fetch/analyze per run",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=MAX_FETCH_PAGES,
        help="Max API/guest pages per account",
    )
    args = parser.parse_args()

    accounts = [a.strip().lstrip("@") for a in args.accounts.split(",") if a.strip()]
    merge_path = Path(args.merge_from) if args.merge_from else None

    max_posts = min(args.limit, EXTENDED_MAX_FETCH_POSTS)
    max_pages = min(args.max_pages, EXTENDED_MAX_FETCH_PAGES)

    try:
        analyzer = SignalAnalyzer(x_accounts=accounts)
        report = analyzer.analyze(
            source=args.source,
            limit=max_posts,
            max_pages=max_pages,
            window_days=args.window_days,
        )
        out = write_site(
            args.output,
            report,
            accounts=accounts,
            merge_from=args.merge_from,
        )
        print(f"Wrote {out.resolve()}")
        return 0
    except Exception as exc:
        if merge_path and merge_path.exists():
            print(f"Scan failed ({exc}); republishing existing gh-pages content.")
            out = refresh_site(args.output, merge_path)
            print(f"Refreshed site at {out.resolve()}")
            return 0
        raise


if __name__ == "__main__":
    raise SystemExit(main())
