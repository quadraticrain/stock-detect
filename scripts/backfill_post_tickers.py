#!/usr/bin/env python3
"""Backfill stock_detect_x_posts.tickers from text cashtags when X API entities were empty."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stock_detect.config import MYSQL_TABLE_POSTS  # noqa: E402
from stock_detect.env import bootstrap  # noqa: E402
from stock_detect.post_tickers import merge_ticker_lists, resolve_post_tickers, tickers_json  # noqa: E402
from stock_detect.tweet_cache import TweetCache  # noqa: E402


def main() -> int:
    bootstrap()
    parser = argparse.ArgumentParser(description="Backfill tickers JSON on cached X posts")
    parser.add_argument("--accounts", default="", help="Comma-separated authors; default all")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    accounts = [a.strip().lstrip("@").lower() for a in args.accounts.split(",") if a.strip()]
    cache = TweetCache()
    if not cache.available:
        print("MySQL not configured (MYSQL_PASSWORD)", file=sys.stderr)
        return 1

    where = "source <> 'ci_marker' AND post_id NOT LIKE '###CI_SCAN_%'"
    params: list = []
    if accounts:
        placeholders = ", ".join(["%s"] * len(accounts))
        where += f" AND author IN ({placeholders})"
        params.extend(accounts)

    updated = 0
    scanned = 0
    with cache._connection() as conn:  # noqa: SLF001
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT post_id, author, text, tickers, source
                FROM {MYSQL_TABLE_POSTS}
                WHERE {where}
                """,
                params,
            )
            rows = cur.fetchall()
            for row in rows:
                scanned += 1
                existing_raw = row.get("tickers")
                existing: list[str] = []
                if existing_raw:
                    if isinstance(existing_raw, str):
                        existing = json.loads(existing_raw)
                    elif isinstance(existing_raw, list):
                        existing = list(existing_raw)
                from stock_detect.models import SocialPost

                post = SocialPost(
                    id=str(row["post_id"]),
                    text=row["text"],
                    author=row["author"],
                    source=row.get("source") or "x",
                    created=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
                    score=0,
                    url="",
                    tickers=existing,
                )
                resolved = resolve_post_tickers(post)
                merged = merge_ticker_lists(existing, resolved)
                if merged == existing:
                    continue
                updated += 1
                if args.dry_run:
                    print(f"would update {post.id} @{post.author}: {existing} -> {merged}")
                    continue
                cur.execute(
                    f"UPDATE {MYSQL_TABLE_POSTS} SET tickers = %s WHERE post_id = %s",
                    (tickers_json(merged), post.id),
                )
    print(f"scanned={scanned} updated={updated} dry_run={args.dry_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
