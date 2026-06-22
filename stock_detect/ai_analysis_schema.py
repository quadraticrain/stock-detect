"""MySQL schema for AI-written Signals / Consensus / Top Tickers (schema only, no auto-write)."""

from __future__ import annotations

from dataclasses import dataclass

from stock_detect.config import (
    MYSQL_SERVICE,
    MYSQL_TABLE_AI_CONSENSUS,
    MYSQL_TABLE_AI_RUNS,
    MYSQL_TABLE_AI_SIGNALS,
    MYSQL_TABLE_AI_TOP_TICKERS,
)


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


AI_ANALYSIS_TABLES: tuple[_TableDef, ...] = (
    _TableDef(
        name=MYSQL_TABLE_AI_RUNS,
        columns=(
            _ColumnDef("run_id", "VARCHAR(64) NOT NULL"),
            _ColumnDef("account", "VARCHAR(64) NOT NULL"),
            _ColumnDef("window_start", "DATETIME(6) NOT NULL"),
            _ColumnDef("window_end", "DATETIME(6) NOT NULL"),
            _ColumnDef("post_count", "INT NOT NULL DEFAULT 0"),
            _ColumnDef("signal_count", "INT NOT NULL DEFAULT 0"),
            _ColumnDef("consensus_count", "INT NOT NULL DEFAULT 0"),
            _ColumnDef("top_ticker_count", "INT NOT NULL DEFAULT 0"),
            _ColumnDef("model", "VARCHAR(64) NULL"),
            _ColumnDef("prompt_version", "VARCHAR(32) NULL"),
            _ColumnDef("status", "VARCHAR(16) NOT NULL DEFAULT 'completed'"),
            _ColumnDef("summary", "TEXT NULL"),
            _ColumnDef("analyzed_at", "DATETIME(6) NOT NULL"),
            _ColumnDef("resume_from_post_id", "VARCHAR(32) NULL"),
            _ColumnDef("resume_from_created_at", "DATETIME(6) NULL"),
            _ColumnDef("checkpoint_post_id", "VARCHAR(32) NULL"),
            _ColumnDef("checkpoint_post_created_at", "DATETIME(6) NULL"),
        ),
        primary_key=("run_id",),
        indexes=(
            _IndexDef("idx_ai_runs_account_time", ("account", "analyzed_at")),
        ),
    ),
    _TableDef(
        name=MYSQL_TABLE_AI_SIGNALS,
        columns=(
            _ColumnDef("run_id", "VARCHAR(64) NOT NULL"),
            _ColumnDef("post_id", "VARCHAR(32) NOT NULL"),
            _ColumnDef("account", "VARCHAR(64) NOT NULL"),
            _ColumnDef("ticker", "VARCHAR(16) NOT NULL"),
            _ColumnDef("recommendation", "VARCHAR(16) NOT NULL"),
            _ColumnDef("confidence", "DECIMAL(4,3) NULL"),
            _ColumnDef("reasoning", "TEXT NULL"),
            _ColumnDef("post_text_excerpt", "VARCHAR(512) NULL"),
            _ColumnDef("post_created_at", "DATETIME(6) NOT NULL"),
            _ColumnDef("post_score", "INT NOT NULL DEFAULT 0"),
            _ColumnDef("written_at", "DATETIME(6) NOT NULL"),
        ),
        primary_key=("run_id", "post_id", "ticker"),
        indexes=(
            _IndexDef("idx_ai_signals_ticker", ("run_id", "ticker")),
            _IndexDef("idx_ai_signals_post", ("post_id",)),
        ),
    ),
    _TableDef(
        name=MYSQL_TABLE_AI_CONSENSUS,
        columns=(
            _ColumnDef("run_id", "VARCHAR(64) NOT NULL"),
            _ColumnDef("consensus_date", "DATE NOT NULL"),
            _ColumnDef("ticker", "VARCHAR(16) NOT NULL"),
            _ColumnDef("consensus_signal", "VARCHAR(16) NOT NULL"),
            _ColumnDef("buy_count", "INT NOT NULL DEFAULT 0"),
            _ColumnDef("sell_count", "INT NOT NULL DEFAULT 0"),
            _ColumnDef("hold_count", "INT NOT NULL DEFAULT 0"),
            _ColumnDef("reasoning", "TEXT NULL"),
            _ColumnDef("written_at", "DATETIME(6) NOT NULL"),
        ),
        primary_key=("run_id", "consensus_date", "ticker"),
        indexes=(_IndexDef("idx_ai_consensus_ticker", ("run_id", "ticker")),),
    ),
    _TableDef(
        name=MYSQL_TABLE_AI_TOP_TICKERS,
        columns=(
            _ColumnDef("run_id", "VARCHAR(64) NOT NULL"),
            _ColumnDef("rank_no", "INT NOT NULL"),
            _ColumnDef("ticker", "VARCHAR(16) NOT NULL"),
            _ColumnDef("mention_posts", "INT NOT NULL DEFAULT 0"),
            _ColumnDef("buy_signals", "INT NOT NULL DEFAULT 0"),
            _ColumnDef("sell_signals", "INT NOT NULL DEFAULT 0"),
            _ColumnDef("hold_signals", "INT NOT NULL DEFAULT 0"),
            _ColumnDef("latest_signal", "VARCHAR(16) NOT NULL DEFAULT 'neutral'"),
            _ColumnDef("top_authors", "JSON NULL"),
            _ColumnDef("ai_summary", "TEXT NULL"),
            _ColumnDef("written_at", "DATETIME(6) NOT NULL"),
        ),
        primary_key=("run_id", "rank_no"),
        indexes=(
            _IndexDef("idx_ai_top_tickers_ticker", ("run_id", "ticker")),
        ),
    ),
)
