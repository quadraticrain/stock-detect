#!/usr/bin/env python3
"""Local Xueqiu fetch with automatic cookie refresh from local Chrome.

Flow:
1. Load the current `XUEQIU_COOKIE` from `.env`.
2. Probe the Xueqiu timeline API to detect an expired/invalid cookie.
3. If invalid, read a fresh cookie from the local Chromium browser and persist
   it back to `.env` (via `scripts/sync_xueqiu_cookie_secret.py`).
4. Fetch the scheduled Xueqiu users' posts into MySQL.
5. On any hard failure, push a Bark alert so a re-login to Xueqiu can be done.

Intended to replace the "Fetch Xueqiu into MySQL" step in the GitHub Actions
workflow, so the cookie no longer has to be synced to a GitHub Secret.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stock_detect.config import FETCH_WINDOW_DAYS, MAX_FETCH_PAGES, MAX_FETCH_POSTS, SCHEDULED_XUEQIU_USERS  # noqa: E402
from stock_detect.env import bootstrap, load_env  # noqa: E402
from stock_detect.fetch_window import default_fetch_window  # noqa: E402
from stock_detect.tweet_cache import TweetCache  # noqa: E402
from stock_detect.xueqiu_fetcher import XueqiuFetcher  # noqa: E402

from scripts import sync_xueqiu_cookie_secret as cookie_sync  # noqa: E402

BARK_PUSH_URL = "https://api.day.app/CXFgAnMVdZXTPvsKRgWKFo"
DOMAIN = "xueqiu.com"


def _push_bark(title: str, body: str) -> None:
    try:
        import requests

        requests.post(
            BARK_PUSH_URL,
            json={"title": title, "body": body, "group": "stock-detect", "level": "timeSensitive"},
            timeout=15,
        ).raise_for_status()
    except Exception as exc:  # noqa: BLE001 — Bark is best-effort
        print(f"Bark push failed: {exc}", file=sys.stderr)


def _refresh_cookie() -> str:
    """Pull a fresh cookie from Chrome and persist to `.env`; return the header."""
    source, header = cookie_sync.best_cookie_header(DOMAIN)
    cookie_sync.write_env_cookie(header)
    load_env()
    fresh = os.environ.get("XUEQIU_COOKIE", "")
    print(f"Refreshed Xueqiu cookie from {source}; cookie_count={header.count(';') + 1}")
    return fresh


def main() -> int:
    bootstrap()
    cookie = os.environ.get("XUEQIU_COOKIE", "")

    fetcher = XueqiuFetcher(cookie=cookie)
    if not cookie or not fetcher.cookie_is_valid():
        print("Xueqiu cookie missing or expired; refreshing from local Chrome...", file=sys.stderr)
        try:
            cookie = _refresh_cookie()
        except Exception as exc:  # noqa: BLE001
            msg = f"雪球 cookie 刷新失败（Chrome 可能未登录雪球）：{exc}"
            print(msg, file=sys.stderr)
            _push_bark("雪球 cookie 刷新失败", msg)
            return 2
        fetcher = XueqiuFetcher(cookie=cookie)
        if not fetcher.cookie_is_valid():
            msg = "雪球 cookie 刷新后仍无效，请在本机 Chrome 重新登录雪球后重试。"
            print(msg, file=sys.stderr)
            _push_bark("雪球 cookie 仍无效", msg)
            return 2

    cache = TweetCache()
    if not cache.available:
        print("MySQL unavailable; set MYSQL_PASSWORD", file=sys.stderr)
        return 2
    cache.sync_schema()

    window = default_fetch_window(window_days=FETCH_WINDOW_DAYS)
    total = inserted = skipped = 0
    for user_id in SCHEDULED_XUEQIU_USERS:
        posts = fetcher.fetch_user_posts(
            user_id, window=window, max_pages=MAX_FETCH_PAGES, max_posts=MAX_FETCH_POSTS
        )
        new_count, skipped_count = cache.insert_posts_batch(posts)
        total += len(posts)
        inserted += new_count
        skipped += skipped_count
        print(f"xueqiu user={user_id} fetched={len(posts)} inserted={new_count} skipped={skipped_count}")

    print(f"Xueqiu OK: posts={total} inserted={inserted} skipped={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
