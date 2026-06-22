#!/usr/bin/env python3
"""Remove one X account's cached posts, fetch state, and AI analysis rows from MySQL.

Manual-only CLI: not imported or invoked by CI, cron, or scan/analyze code paths.
Use --dry-run first, then confirm interactively (or --yes for automation).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stock_detect.config import (  # noqa: E402
    MYSQL_TABLE_AI_CONSENSUS,
    MYSQL_TABLE_AI_RUNS,
    MYSQL_TABLE_AI_SIGNALS,
    MYSQL_TABLE_AI_TOP_TICKERS,
    MYSQL_TABLE_POSTS,
    MYSQL_TABLE_STATE,
)
from stock_detect.env import bootstrap  # noqa: E402
from stock_detect.tweet_cache import TweetCache  # noqa: E402


def _count(cur, table: str, where: str, params: str | tuple[str, ...] | list[str]) -> int:
    if isinstance(params, str):
        params = (params,)
    cur.execute(f"SELECT COUNT(*) AS c FROM {table} WHERE {where}", params)
    return int(cur.fetchone()["c"])


def purge_account(cache: TweetCache, account: str, *, dry_run: bool) -> dict[str, int]:
    slug = account.lstrip("@").lower()
    with cache._connection() as conn:
        conn.autocommit(False)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT run_id FROM {MYSQL_TABLE_AI_RUNS} WHERE LOWER(account) = %s",
                    (slug,),
                )
                run_ids = [row["run_id"] for row in cur.fetchall()]

                before = {
                    "posts": _count(cur, MYSQL_TABLE_POSTS, "LOWER(author) = %s", slug),
                    "fetch_state": _count(cur, MYSQL_TABLE_STATE, "LOWER(account) = %s", slug),
                    "ai_runs": _count(cur, MYSQL_TABLE_AI_RUNS, "LOWER(account) = %s", slug),
                    "ai_signals": _count(
                        cur, MYSQL_TABLE_AI_SIGNALS, "LOWER(account) = %s", slug
                    ),
                }
                if run_ids:
                    placeholders = ", ".join(["%s"] * len(run_ids))
                    before["ai_consensus"] = _count(
                        cur,
                        MYSQL_TABLE_AI_CONSENSUS,
                        f"run_id IN ({placeholders})",
                        tuple(run_ids),
                    )
                    before["ai_top_tickers"] = _count(
                        cur,
                        MYSQL_TABLE_AI_TOP_TICKERS,
                        f"run_id IN ({placeholders})",
                        tuple(run_ids),
                    )
                else:
                    before["ai_consensus"] = 0
                    before["ai_top_tickers"] = 0

                if dry_run:
                    conn.rollback()
                    return before

                if run_ids:
                    placeholders = ", ".join(["%s"] * len(run_ids))
                    cur.execute(
                        f"DELETE FROM {MYSQL_TABLE_AI_SIGNALS} WHERE run_id IN ({placeholders})",
                        run_ids,
                    )
                    cur.execute(
                        f"DELETE FROM {MYSQL_TABLE_AI_CONSENSUS} WHERE run_id IN ({placeholders})",
                        run_ids,
                    )
                    cur.execute(
                        f"DELETE FROM {MYSQL_TABLE_AI_TOP_TICKERS} WHERE run_id IN ({placeholders})",
                        run_ids,
                    )
                cur.execute(
                    f"DELETE FROM {MYSQL_TABLE_AI_SIGNALS} WHERE LOWER(account) = %s",
                    (slug,),
                )
                cur.execute(
                    f"DELETE FROM {MYSQL_TABLE_AI_RUNS} WHERE LOWER(account) = %s",
                    (slug,),
                )
                cur.execute(
                    f"DELETE FROM {MYSQL_TABLE_POSTS} WHERE LOWER(author) = %s",
                    (slug,),
                )
                cur.execute(
                    f"DELETE FROM {MYSQL_TABLE_STATE} WHERE LOWER(account) = %s",
                    (slug,),
                )
            conn.commit()
            return before
        except Exception:
            conn.rollback()
            raise


def main() -> int:
    bootstrap()
    parser = argparse.ArgumentParser(description="Purge one account from stock-detect MySQL tables")
    parser.add_argument("--account", required=True, help="X screen name, e.g. HillaryClinton")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print row counts only; do not delete",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip interactive confirmation",
    )
    args = parser.parse_args()

    cache = TweetCache()
    if not cache.available:
        print("Error: MYSQL_PASSWORD not set or pymysql missing", file=sys.stderr)
        return 1

    account = args.account.strip()
    if not args.dry_run and not args.yes:
        print(f"This will permanently delete MySQL data for @{account.lstrip('@')}.")
        confirm = input("Type the account slug to confirm: ").strip().lstrip("@").lower()
        if confirm != account.lstrip("@").lower():
            print("Aborted.")
            return 1

    removed = purge_account(cache, account, dry_run=args.dry_run)
    label = "would remove" if args.dry_run else "removed"
    print(f"{label} @{account.lstrip('@')}:")
    for key, value in removed.items():
        print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
