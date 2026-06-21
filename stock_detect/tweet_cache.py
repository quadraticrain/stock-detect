"""MySQL-backed X post cache for deduplication and incremental API fetches."""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterator

from stock_detect.config import (
    MYSQL_DATABASE,
    MYSQL_HOST,
    MYSQL_PORT,
    MYSQL_TABLE_POSTS,
    MYSQL_TABLE_STATE,
    MYSQL_USER,
)
from stock_detect.fetch_window import FetchWindow
from stock_detect.models import SocialPost

try:
    import pymysql
    from pymysql.cursors import DictCursor
except ImportError:  # pragma: no cover - optional at import time
    pymysql = None
    DictCursor = None

_schema_synced = False


@dataclass(frozen=True)
class _ColumnDef:
    name: str
    definition: str


@dataclass(frozen=True)
class _IndexDef:
    name: str
    columns: tuple[str, ...]


@dataclass(frozen=True)
class _TableDef:
    name: str
    columns: tuple[_ColumnDef, ...]
    primary_key: tuple[str, ...]
    indexes: tuple[_IndexDef, ...] = ()


_TABLES: tuple[_TableDef, ...] = (
    _TableDef(
        name=MYSQL_TABLE_POSTS,
        columns=(
            _ColumnDef("post_id", "VARCHAR(32) NOT NULL"),
            _ColumnDef("author", "VARCHAR(64) NOT NULL"),
            _ColumnDef("text", "TEXT NOT NULL"),
            _ColumnDef("created_at", "DATETIME(6) NOT NULL"),
            _ColumnDef("score", "INT NOT NULL DEFAULT 0"),
            _ColumnDef("url", "VARCHAR(512) NOT NULL"),
            _ColumnDef("tickers", "JSON NULL"),
            _ColumnDef("source", "VARCHAR(16) NOT NULL DEFAULT 'x'"),
            _ColumnDef("fetched_at", "DATETIME(6) NOT NULL"),
        ),
        primary_key=("post_id",),
        indexes=(_IndexDef("idx_author_created", ("author", "created_at")),),
    ),
    _TableDef(
        name=MYSQL_TABLE_STATE,
        columns=(
            _ColumnDef("account", "VARCHAR(64) NOT NULL"),
            _ColumnDef("user_id", "VARCHAR(32) NULL"),
            _ColumnDef("last_tweet_id", "VARCHAR(32) NULL"),
            _ColumnDef("last_fetch_at", "DATETIME(6) NULL"),
        ),
        primary_key=("account",),
    ),
)


@dataclass
class FetchState:
    account: str
    user_id: str | None = None
    last_tweet_id: str | None = None
    last_fetch_at: datetime | None = None


def init_mysql_cache(*, strict: bool = False) -> bool:
    """Sync MySQL tables at process startup. Returns True when schema is ready."""
    cache = TweetCache()
    if not cache.available:
        return False
    try:
        cache.sync_schema()
        return True
    except Exception:
        if strict:
            raise
        return False


class TweetCache:
    """Read/write cached X posts in shared MySQL (investment_cache / cache_data)."""

    def __init__(self, *, password: str | None = None):
        self.password = password if password is not None else os.environ.get("MYSQL_PASSWORD", "")

    @property
    def available(self) -> bool:
        return bool(self.password and pymysql is not None)

    @contextmanager
    def _connection(self):
        if not self.available:
            raise RuntimeError("MySQL cache is not configured (set MYSQL_PASSWORD)")
        conn = pymysql.connect(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=self.password,
            database=MYSQL_DATABASE,
            charset="utf8mb4",
            cursorclass=DictCursor,
            autocommit=True,
            connect_timeout=20,
            read_timeout=45,
            write_timeout=45,
        )
        try:
            yield conn
        finally:
            conn.close()

    def sync_schema(self, *, force: bool = False) -> None:
        """Create tables and apply additive schema changes (columns/indexes)."""
        global _schema_synced
        if _schema_synced and not force:
            return

        with self._connection() as conn:
            with conn.cursor() as cur:
                for table in _TABLES:
                    self._create_table(cur, table)
                    self._sync_columns(cur, table)
                    self._sync_indexes(cur, table)

        _schema_synced = True

    def ensure_schema(self) -> None:
        """Backward-compatible alias for sync_schema()."""
        self.sync_schema()

    @staticmethod
    def _create_table(cur, table: _TableDef) -> None:
        column_sql = ",\n".join(f"{col.name} {col.definition}" for col in table.columns)
        pk_sql = f", PRIMARY KEY ({', '.join(table.primary_key)})" if table.primary_key else ""
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {table.name} (
                {column_sql}
                {pk_sql}
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )

    @staticmethod
    def _column_name(row: dict) -> str:
        for key, value in row.items():
            if key.lower() == "column_name":
                return str(value)
        raise KeyError("column_name")

    @staticmethod
    def _index_name(row: dict) -> str:
        for key, value in row.items():
            if key.lower() == "index_name":
                return str(value)
        raise KeyError("index_name")

    @staticmethod
    def _sync_columns(cur, table: _TableDef) -> None:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            """,
            (MYSQL_DATABASE, table.name),
        )
        existing = {TweetCache._column_name(row).lower() for row in cur.fetchall()}
        for column in table.columns:
            if column.name.lower() in existing:
                continue
            cur.execute(
                f"ALTER TABLE {table.name} ADD COLUMN {column.name} {column.definition}"
            )

    @staticmethod
    def _sync_indexes(cur, table: _TableDef) -> None:
        if not table.indexes:
            return
        cur.execute(
            """
            SELECT index_name
            FROM information_schema.statistics
            WHERE table_schema = %s AND table_name = %s
            GROUP BY index_name
            """,
            (MYSQL_DATABASE, table.name),
        )
        existing = {TweetCache._index_name(row).lower() for row in cur.fetchall()}
        for index in table.indexes:
            if index.name.lower() in existing:
                continue
            cols = ", ".join(index.columns)
            cur.execute(f"CREATE INDEX {index.name} ON {table.name} ({cols})")

    def get_state(self, account: str) -> FetchState | None:
        account = account.lstrip("@").lower()
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT account, user_id, last_tweet_id, last_fetch_at
                    FROM {MYSQL_TABLE_STATE}
                    WHERE account = %s
                    """,
                    (account,),
                )
                row = cur.fetchone()
        if not row:
            return None
        return FetchState(
            account=row["account"],
            user_id=row.get("user_id"),
            last_tweet_id=row.get("last_tweet_id"),
            last_fetch_at=row.get("last_fetch_at"),
        )

    def save_state(
        self,
        account: str,
        *,
        user_id: str | None = None,
        last_tweet_id: str | None = None,
    ) -> None:
        account = account.lstrip("@").lower()
        now = datetime.now(timezone.utc)
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO {MYSQL_TABLE_STATE}
                        (account, user_id, last_tweet_id, last_fetch_at)
                    VALUES (%s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        user_id = COALESCE(VALUES(user_id), user_id),
                        last_tweet_id = COALESCE(VALUES(last_tweet_id), last_tweet_id),
                        last_fetch_at = VALUES(last_fetch_at)
                    """,
                    (account, user_id, last_tweet_id, now.replace(tzinfo=None)),
                )

    def upsert_posts(self, posts: list[SocialPost]) -> int:
        if not posts:
            return 0
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        inserted = 0
        with self._connection() as conn:
            with conn.cursor() as cur:
                for post in posts:
                    created = post.created
                    if created.tzinfo is not None:
                        created = created.astimezone(timezone.utc).replace(tzinfo=None)
                    cur.execute(
                        f"""
                        INSERT IGNORE INTO {MYSQL_TABLE_POSTS}
                            (post_id, author, text, created_at, score, url, tickers, source, fetched_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            post.id,
                            post.author.lower(),
                            post.text,
                            created,
                            post.score,
                            post.url,
                            json.dumps(post.tickers),
                            post.source,
                            now,
                        ),
                    )
                    inserted += cur.rowcount
        return inserted

    def list_posts(self, account: str, window: FetchWindow) -> list[SocialPost]:
        account = account.lstrip("@").lower()
        after = window.after.astimezone(timezone.utc).replace(tzinfo=None)
        before = window.before.astimezone(timezone.utc).replace(tzinfo=None)
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT post_id, author, text, created_at, score, url, tickers, source
                    FROM {MYSQL_TABLE_POSTS}
                    WHERE author = %s AND created_at >= %s AND created_at <= %s
                    ORDER BY created_at DESC
                    """,
                    (account, after, before),
                )
                rows = cur.fetchall()
        posts: list[SocialPost] = []
        for row in rows:
            created = row["created_at"]
            if isinstance(created, datetime) and created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            tickers = row.get("tickers") or "[]"
            if isinstance(tickers, str):
                tickers = json.loads(tickers)
            posts.append(
                SocialPost(
                    id=str(row["post_id"]),
                    text=row["text"],
                    author=row["author"],
                    source=row.get("source") or "x",
                    created=created,
                    score=int(row.get("score") or 0),
                    url=row["url"],
                    tickers=list(tickers),
                )
            )
        return posts

    def prune_before(self, account: str, cutoff: datetime) -> int:
        account = account.lstrip("@").lower()
        if cutoff.tzinfo is not None:
            cutoff = cutoff.astimezone(timezone.utc).replace(tzinfo=None)
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    DELETE FROM {MYSQL_TABLE_POSTS}
                    WHERE author = %s AND created_at < %s
                    """,
                    (account, cutoff),
                )
                return cur.rowcount

    @staticmethod
    def newest_tweet_id(posts: list[SocialPost]) -> str | None:
        if not posts:
            return None
        newest = max(posts, key=lambda p: (p.created, p.id))
        return newest.id
