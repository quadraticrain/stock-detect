#!/usr/bin/env python3
"""Resolve CI fetch caps from workflow inputs (auto-scale extended windows)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stock_detect.config import (  # noqa: E402
    EXTENDED_MAX_FETCH_PAGES,
    EXTENDED_MAX_FETCH_POSTS,
    FETCH_WINDOW_DAYS,
    MAX_FETCH_PAGES,
    MAX_FETCH_POSTS,
    X_API_MAX_DAYS,
)
from stock_detect.fetch_budget import extended_fetch_budget  # noqa: E402


def resolve_caps(window_days: int, max_posts: int, max_pages: int) -> tuple[int, int]:
    posts = min(max(max_posts, MAX_FETCH_POSTS), EXTENDED_MAX_FETCH_POSTS)
    pages = min(max(max_pages, MAX_FETCH_PAGES), EXTENDED_MAX_FETCH_PAGES)
    if window_days > X_API_MAX_DAYS:
        extra = window_days - X_API_MAX_DAYS
        posts = min(EXTENDED_MAX_FETCH_POSTS, max(posts, MAX_FETCH_POSTS + extra * 80))
        pages = min(EXTENDED_MAX_FETCH_PAGES, max(pages, MAX_FETCH_PAGES + extra * 3))
    return posts, pages


def main() -> int:
    parser = argparse.ArgumentParser(description="Print resolved CI fetch caps")
    parser.add_argument("--window-days", type=int, default=FETCH_WINDOW_DAYS)
    parser.add_argument("--max-posts", type=int, default=MAX_FETCH_POSTS)
    parser.add_argument("--max-pages", type=int, default=MAX_FETCH_PAGES)
    parser.add_argument("--format", choices=["env", "json"], default="env")
    args = parser.parse_args()

    posts, pages = resolve_caps(args.window_days, args.max_posts, args.max_pages)
    budget = extended_fetch_budget(args.window_days, posts, pages)

    if args.format == "json":
        import json

        print(
            json.dumps(
                {
                    "max_posts": posts,
                    "max_pages": pages,
                    "guest_prefetch": args.window_days > X_API_MAX_DAYS,
                    "guest_pages": budget.guest_pages,
                    "guest_posts": budget.guest_posts,
                    "guest_passes": budget.guest_passes,
                    "api_pages": budget.api_pages,
                    "api_posts": budget.api_posts,
                }
            )
        )
        return 0

    print(f"MAX_POSTS={posts}")
    print(f"MAX_PAGES={pages}")
    print(f"GUEST_PREFETCH={'1' if args.window_days > X_API_MAX_DAYS else '0'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
