#!/usr/bin/env python3
"""Import tweets from a public JSON archive into MySQL (fills gaps API/guest cannot reach)."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stock_detect.env import bootstrap  # noqa: E402
from stock_detect.fetch_window import FetchWindow, default_fetch_window  # noqa: E402
from stock_detect.models import SocialPost  # noqa: E402
from stock_detect.tweet_cache import TweetCache  # noqa: E402

DEFAULT_ARCHIVE_URL = (
    "https://raw.githubusercontent.com/yan-labs/serenity-aleabitoreddit/"
    "main/data/aleabitoreddit_tweets.json"
)
ACCOUNT_ARCHIVE_URLS: dict[str, str] = {
    "aleabitoreddit": DEFAULT_ARCHIVE_URL,
}


def _parse_created(raw: str) -> datetime | None:
    if not raw:
        return None
    try:
        created = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return created.astimezone(timezone.utc)


def _archive_row_to_post(row: dict, account: str) -> SocialPost | None:
    if row.get("isRetweet"):
        return None
    tweet_id = str(row.get("id") or "")
    if not tweet_id:
        return None
    created = _parse_created(row.get("createdAtISO") or row.get("createdAt") or "")
    if created is None:
        return None
    metrics = row.get("metrics") or {}
    score = int(metrics.get("likes") or metrics.get("like_count") or 0)
    text = (row.get("text") or "").strip()
    if not text:
        return None
    symbols: list[str] = []
    for key in ("tickers", "cashtags"):
        val = row.get(key)
        if isinstance(val, list):
            symbols.extend(str(v).upper() for v in val if v)
    return SocialPost(
        id=tweet_id,
        text=text,
        author=account,
        source="x",
        created=created,
        score=score,
        url=f"https://x.com/{account}/status/{tweet_id}",
        tickers=symbols,
    )


def load_archive(path_or_url: str) -> list[dict]:
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        with urllib.request.urlopen(path_or_url, timeout=120) as resp:  # noqa: S310
            payload = json.load(resp)
    else:
        payload = json.loads(Path(path_or_url).read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("tweets", "data", "items"):
            if isinstance(payload.get(key), list):
                return payload[key]
    raise ValueError("Unrecognized archive JSON shape")


def main() -> int:
    bootstrap()
    parser = argparse.ArgumentParser(description="Import tweet archive JSON into MySQL")
    parser.add_argument("--accounts", default="aleabitoreddit")
    parser.add_argument("--window-days", type=int, default=179)
    parser.add_argument("--after", help="Override window start YYYY-MM-DD")
    parser.add_argument("--before", help="Override window end YYYY-MM-DD")
    parser.add_argument("--archive-url", default=DEFAULT_ARCHIVE_URL)
    parser.add_argument("--archive-file", help="Local JSON file instead of URL")
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    cache = TweetCache()
    if not cache.available and not args.dry_run:
        print("Error: MYSQL_PASSWORD not set", file=sys.stderr)
        return 1

    window = default_fetch_window(window_days=args.window_days)
    if args.after:
        window = FetchWindow(
            after=datetime.strptime(args.after, "%Y-%m-%d").replace(tzinfo=timezone.utc),
            before=window.before,
            window_days=args.window_days,
        )
    if args.before:
        window = FetchWindow(
            after=window.after,
            before=datetime.strptime(args.before, "%Y-%m-%d").replace(tzinfo=timezone.utc),
            window_days=args.window_days,
        )

    source = args.archive_file or args.archive_url
    print(f"Loading archive: {source}")
    rows = load_archive(source)
    print(f"Archive rows: {len(rows)}")

    accounts = {a.strip().lstrip("@").lower() for a in args.accounts.split(",") if a.strip()}
    if not args.dry_run:
        cache.ensure_schema()

    total_inserted = 0
    total_skipped = 0
    for account in sorted(accounts):
        posts: list[SocialPost] = []
        for row in rows:
            raw_author = row.get("author") or account
            if isinstance(raw_author, dict):
                author = str(raw_author.get("screenName") or raw_author.get("screen_name") or account)
            else:
                author = str(raw_author)
            author = author.lstrip("@").lower()
            if author != account:
                continue
            post = _archive_row_to_post(row, account)
            if post is None or not window.contains(post.created):
                continue
            posts.append(post)

        print(f"\n@{account}: {len(posts)} archive posts in window")
        if not posts:
            continue
        oldest = min(p.created for p in posts)
        newest = max(p.created for p in posts)
        print(f"  range: {oldest.date()} .. {newest.date()}")

        if args.dry_run:
            continue

        inserted, skipped = cache.insert_posts_batch(
            posts,
            batch_size=args.batch_size,
            skip_existing=True,
        )
        total_inserted += inserted
        total_skipped += skipped
        print(f"  mysql: inserted={inserted} skipped_existing={skipped}")

    print(f"\nDone. inserted={total_inserted} skipped_existing={total_skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
