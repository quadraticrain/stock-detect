#!/usr/bin/env python3
"""AI 舆情分析 MySQL 辅助工具 (openclaw-v4)

用途
====
本脚本是 stock-detect 项目「每日 AI 舆情分析」定时任务的手动执行辅助工具。
原任务由 OpenClaw 在每天北京时间 23:00 自动触发，本工具用于在本地/WorkBuddy 中
手动跑一次同样的增量分析流程，方便排障、补跑与验收。

它只负责 *读写 MySQL*，不做语义分析本身 —— 语义判断由调用方（AI / 人）完成。
脚本把繁琐的 SQL、断点管理、幂等写入封装成几条子命令，避免手写易错的 SQL。

职责边界
--------
- 读：连阿里云 RDS `cache_data` 库，同步 AI 四表结构，读断点、读待分析推文
- 写：按 run_id 幂等地写入 signals / consensus / top_tickers / ai_runs（含断点）
- 不做：调用 X API、关键词词表分析、Yahoo 回测

子命令
------
- sync                  同步 AI 四表结构（建表、补列、补索引），首次执行前必须先跑
- checkpoint <account>  打印某账号最近一次成功 run 的 checkpoint (JSON)
- fetch <account>       读取断点之后的待分析推文 (JSON)，含 resume_from 信息
- write-run             从 stdin 读一个完整 run 的 JSON，幂等写入四表
- verify <account>      检查某账号是否存在同一 post_id 被多个 run 重复分析

典型手动执行流程
----------------
1. python scripts/ai_analysis_helper.py sync
2. python scripts/ai_analysis_helper.py checkpoint aleabitoreddit
3. python scripts/ai_analysis_helper.py fetch aleabitoreddit --limit 400 > batch.json
   (AI 读 batch.json，对每条推文做语义分析，组装成 run.json)
4. python scripts/ai_analysis_helper.py write-run < run.json
5. python scripts/ai_analysis_helper.py verify aleabitoreddit

环境变量
--------
- MYSQL_PASSWORD  必填（可从项目根 .env 自动加载）
- 其余连接信息（host/port/user/database）写死在 stock_detect/config.py

注意
----
- 所有时间按 UTC 写入，MySQL DATETIME(6) 无时区后缀
- run_id 命名规范：YYYYMMDDTHHMMSSZ_ai_{account}
- 排序键统一 (created_at ASC, post_id ASC)，保证断点可复现
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# 让脚本既能从仓库根跑，也能从任意目录跑
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from dotenv import load_dotenv  # type: ignore
    # override=True：shell 里可能存在过期的 MYSQL_PASSWORD（如本地占位 123456），
    # 始终以仓库 .env 中的真实凭据为准。
    load_dotenv(_REPO_ROOT / ".env", override=True)
except Exception:
    # .env 可有可无；密码也可直接走环境变量
    pass

import pymysql  # noqa: E402
from pymysql.cursors import DictCursor  # noqa: E402

from stock_detect.config import (  # noqa: E402
    MYSQL_DATABASE,
    MYSQL_HOST,
    MYSQL_PORT,
    MYSQL_TABLE_AI_CONSENSUS,
    MYSQL_TABLE_AI_RUNS,
    MYSQL_TABLE_AI_SIGNALS,
    MYSQL_TABLE_AI_TOP_TICKERS,
    MYSQL_TABLE_POSTS,
    MYSQL_USER,
)
from stock_detect.tweet_cache import TweetCache, init_mysql_cache  # noqa: E402

PROMPT_VERSION = "openclaw-v5"
DEFAULT_BATCH_LIMIT = 400


def _connect() -> pymysql.Connection:
    password = os.environ.get("MYSQL_PASSWORD", "")
    if not password:
        sys.exit("ERROR: MYSQL_PASSWORD 未设置（请写 .env 或 export MYSQL_PASSWORD=...）")
    return pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=password,
        database=MYSQL_DATABASE,
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=True,
        connect_timeout=20,
        read_timeout=60,
        write_timeout=60,
    )


def _now_utc_micro() -> str:
    """UTC 当前时间，MySQL DATETIME(6) 格式：YYYY-MM-DD HH:MM:SS.ffffff"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")


def _norm_dt(value) -> str | None:
    """把 datetime / ISO 字符串规范化为 MySQL DATETIME(6) 字符串。"""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S.%f")
    if isinstance(value, str):
        s = value.strip()
        # 兼容 ISO 8601 带 'T' / 'Z' 的情况
        s = s.replace("T", " ")
        if s.endswith("Z"):
            s = s[:-1]
        # 截到微秒即可，MySQL DATETIME(6) 支持 6 位小数
        return s
    return str(value)


# --------------------------------------------------------------------------- #
# 子命令实现
# --------------------------------------------------------------------------- #

def cmd_sync(args: argparse.Namespace) -> int:
    """同步 AI 四表结构（建表、补列、补索引）。"""
    ok = init_mysql_cache(strict=True)
    print(json.dumps({"ok": ok, "tables": [
        MYSQL_TABLE_AI_RUNS,
        MYSQL_TABLE_AI_SIGNALS,
        MYSQL_TABLE_AI_CONSENSUS,
        MYSQL_TABLE_AI_TOP_TICKERS,
    ]}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


def cmd_checkpoint(args: argparse.Namespace) -> int:
    """读取某账号最近一次成功 run 的 checkpoint。"""
    account = args.account
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT run_id, status, post_count, signal_count, consensus_count,
                       top_ticker_count, prompt_version, analyzed_at,
                       resume_from_post_id, resume_from_created_at,
                       checkpoint_post_id, checkpoint_post_created_at, summary
                FROM {MYSQL_TABLE_AI_RUNS}
                WHERE account = %s
                  AND status IN ('completed', 'partial')
                  AND checkpoint_post_id IS NOT NULL
                ORDER BY analyzed_at DESC
                LIMIT 1
                """,
                (account,),
            )
            row = cur.fetchone()
    if not row:
        print(json.dumps({
            "account": account,
            "has_checkpoint": False,
            "resume_from_post_id": None,
            "resume_from_created_at": None,
            "note": "无历史成功 run，本批为全量首次分析",
        }, ensure_ascii=False, indent=2))
        return 0
    # datetime 序列化
    for k, v in list(row.items()):
        if isinstance(v, datetime):
            row[k] = v.strftime("%Y-%m-%d %H:%M:%S.%f")
    row["account"] = account
    row["has_checkpoint"] = True
    print(json.dumps(row, ensure_ascii=False, indent=2))
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    """读取断点之后、且未在 ai_signals 出现过的待分析推文。"""
    account = args.account
    limit = args.limit
    with _connect() as conn:
        with conn.cursor() as cur:
            # 1) 读断点
            cur.execute(
                f"""
                SELECT checkpoint_post_id, checkpoint_post_created_at, status
                FROM {MYSQL_TABLE_AI_RUNS}
                WHERE account = %s
                  AND status IN ('completed', 'partial')
                  AND checkpoint_post_id IS NOT NULL
                ORDER BY analyzed_at DESC
                LIMIT 1
                """,
                (account,),
            )
            ckpt = cur.fetchone()
            if ckpt:
                resume_from_post_id = ckpt["checkpoint_post_id"]
                resume_from_created_at = ckpt["checkpoint_post_created_at"]
            else:
                resume_from_post_id = None
                resume_from_created_at = None

            # 2) 选本批待处理推文（断点之后 & 未分析过）
            cur.execute(
                f"""
                SELECT post_id, author, text, created_at, score, url, tickers, source
                FROM {MYSQL_TABLE_POSTS}
                WHERE author = %s
                  AND source <> 'ci_marker'
                  AND post_id NOT LIKE '###CI_SCAN_%%'
                  AND (
                    %s IS NULL
                    OR created_at > %s
                    OR (created_at = %s AND post_id > %s)
                  )
                  AND post_id NOT IN (
                    SELECT DISTINCT post_id FROM {MYSQL_TABLE_AI_SIGNALS} WHERE account = %s
                  )
                ORDER BY created_at ASC, post_id ASC
                LIMIT %s
                """,
                (
                    account,
                    resume_from_created_at,
                    resume_from_created_at,
                    resume_from_created_at,
                    resume_from_post_id,
                    account,
                    limit,
                ),
            )
            posts = cur.fetchall()
            # 3) 估算剩余未处理量（仅当本批打满时才需关心）
            remaining = 0
            if len(posts) >= limit:
                last = posts[-1] if posts else None
                if last:
                    cur.execute(
                        f"""
                        SELECT COUNT(*) AS cnt
                        FROM {MYSQL_TABLE_POSTS}
                        WHERE author = %s
                          AND source <> 'ci_marker'
                          AND post_id NOT LIKE '###CI_SCAN_%%'
                          AND (created_at > %s
                               OR (created_at = %s AND post_id > %s))
                          AND post_id NOT IN (
                            SELECT DISTINCT post_id FROM {MYSQL_TABLE_AI_SIGNALS} WHERE account = %s
                          )
                        """,
                        (
                            account,
                            last["created_at"],
                            last["created_at"],
                            last["post_id"],
                            account,
                        ),
                    )
                    remaining = int(cur.fetchone()["cnt"])

    def _ser(p):
        out = dict(p)
        if isinstance(out.get("created_at"), datetime):
            out["created_at"] = out["created_at"].strftime("%Y-%m-%d %H:%M:%S.%f")
        if isinstance(out.get("tickers"), str):
            try:
                out["tickers"] = json.loads(out["tickers"])
            except Exception:
                pass
        return out

    result = {
        "account": account,
        "batch_limit": limit,
        "has_checkpoint": ckpt is not None,
        "resume_from_post_id": resume_from_post_id,
        "resume_from_created_at": _norm_dt(resume_from_created_at),
        "post_count": len(posts),
        "remaining_estimate": remaining,
        "status_hint": "partial" if len(posts) >= limit else "completed",
        "posts": [_ser(p) for p in posts],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _delete_run(conn: pymysql.Connection, run_id: str) -> None:
    """幂等：删除某 run_id 在四表的旧行。"""
    with conn.cursor() as cur:
        cur.execute(f"DELETE FROM {MYSQL_TABLE_AI_SIGNALS} WHERE run_id = %s", (run_id,))
        cur.execute(f"DELETE FROM {MYSQL_TABLE_AI_CONSENSUS} WHERE run_id = %s", (run_id,))
        cur.execute(f"DELETE FROM {MYSQL_TABLE_AI_TOP_TICKERS} WHERE run_id = %s", (run_id,))
        cur.execute(f"DELETE FROM {MYSQL_TABLE_AI_RUNS} WHERE run_id = %s", (run_id,))


def cmd_write_run(args: argparse.Namespace) -> int:
    """从 stdin 读一个完整 run 的 JSON，幂等写入四表。"""
    payload = json.load(sys.stdin)

    run_id = payload["run_id"]
    account = payload["account"]
    signals = payload.get("signals", [])
    consensus = payload.get("consensus", [])
    top_tickers = payload.get("top_tickers", [])
    written_at = _now_utc_micro()

    with _connect() as conn:
        _delete_run(conn, run_id)  # 幂等
        with conn.cursor() as cur:
            # 1) signals
            for s in signals:
                cur.execute(
                    f"""
                    INSERT INTO {MYSQL_TABLE_AI_SIGNALS}
                      (run_id, post_id, account, ticker, recommendation, confidence,
                       reasoning, post_text_excerpt, post_created_at, post_score, written_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        run_id,
                        s["post_id"],
                        account,
                        s["ticker"],
                        s["recommendation"],
                        s.get("confidence"),
                        s.get("reasoning"),
                        s.get("post_text_excerpt"),
                        _norm_dt(s["post_created_at"]),
                        int(s.get("post_score", 0)),
                        written_at,
                    ),
                )
            # 2) consensus（全窗口重算，先 delete 本 run 再 insert —— delete 已在 _delete_run 完成）
            for c in consensus:
                cur.execute(
                    f"""
                    INSERT INTO {MYSQL_TABLE_AI_CONSENSUS}
                      (run_id, consensus_date, ticker, consensus_signal,
                       buy_count, sell_count, hold_count, reasoning, written_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        run_id,
                        c["consensus_date"],
                        c["ticker"],
                        c["consensus_signal"],
                        int(c.get("buy_count", 0)),
                        int(c.get("sell_count", 0)),
                        int(c.get("hold_count", 0)),
                        c.get("reasoning"),
                        written_at,
                    ),
                )
            # 3) top_tickers（全窗口重算）
            for t in top_tickers:
                authors = t.get("top_authors")
                authors_json = json.dumps(authors, ensure_ascii=False) if authors is not None else None
                cur.execute(
                    f"""
                    INSERT INTO {MYSQL_TABLE_AI_TOP_TICKERS}
                      (run_id, rank_no, ticker, mention_posts, buy_signals, sell_signals,
                       hold_signals, latest_signal, top_authors, ai_summary, written_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        run_id,
                        int(t["rank_no"]),
                        t["ticker"],
                        int(t.get("mention_posts", 0)),
                        int(t.get("buy_signals", 0)),
                        int(t.get("sell_signals", 0)),
                        int(t.get("hold_signals", 0)),
                        t.get("latest_signal", "neutral"),
                        authors_json,
                        t.get("ai_summary"),
                        written_at,
                    ),
                )
            # 4) ai_runs（含 checkpoint 四字段）
            cur.execute(
                f"""
                INSERT INTO {MYSQL_TABLE_AI_RUNS}
                  (run_id, account, window_start, window_end, post_count, signal_count,
                   consensus_count, top_ticker_count, model, prompt_version, status,
                   summary, analyzed_at, resume_from_post_id, resume_from_created_at,
                   checkpoint_post_id, checkpoint_post_created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    run_id,
                    account,
                    _norm_dt(payload["window_start"]),
                    _norm_dt(payload["window_end"]),
                    int(payload.get("post_count", len(signals))),
                    int(payload.get("signal_count", len(signals))),
                    int(payload.get("consensus_count", len(consensus))),
                    int(payload.get("top_ticker_count", len(top_tickers))),
                    payload.get("model"),
                    payload.get("prompt_version", PROMPT_VERSION),
                    payload.get("status", "completed"),
                    payload.get("summary"),
                    _norm_dt(payload.get("analyzed_at")) or written_at,
                    payload.get("resume_from_post_id"),
                    _norm_dt(payload.get("resume_from_created_at")),
                    payload.get("checkpoint_post_id"),
                    _norm_dt(payload.get("checkpoint_post_created_at")),
                ),
            )

    summary = {
        "ok": True,
        "run_id": run_id,
        "account": account,
        "status": payload.get("status"),
        "written": {
            "signals": len(signals),
            "consensus": len(consensus),
            "top_tickers": len(top_tickers),
            "ai_runs": 1,
        },
        "checkpoint_post_id": payload.get("checkpoint_post_id"),
        "checkpoint_post_created_at": _norm_dt(payload.get("checkpoint_post_created_at")),
        "resume_from_post_id": payload.get("resume_from_post_id"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    """检查某账号是否存在同一 post_id 被多个 run 重复分析。"""
    account = args.account
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT post_id, COUNT(DISTINCT run_id) AS runs
                FROM {MYSQL_TABLE_AI_SIGNALS}
                WHERE account = %s
                GROUP BY post_id
                HAVING runs > 1
                LIMIT 20
                """,
                (account,),
            )
            dup = cur.fetchall()
            cur.execute(
                f"""
                SELECT account, run_id, status, post_count, signal_count,
                       consensus_count, top_ticker_count, prompt_version,
                       analyzed_at, checkpoint_post_id
                FROM {MYSQL_TABLE_AI_RUNS}
                WHERE account = %s
                ORDER BY analyzed_at DESC
                LIMIT 10
                """,
                (account,),
            )
            recent = cur.fetchall()
    for r in recent:
        if isinstance(r.get("analyzed_at"), datetime):
            r["analyzed_at"] = r["analyzed_at"].strftime("%Y-%m-%d %H:%M:%S.%f")
    print(json.dumps({
        "account": account,
        "duplicate_signal_posts": len(dup),
        "duplicates_sample": dup[:20],
        "recent_runs": recent,
    }, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ai_analysis_helper",
        description="stock-detect AI 舆情分析 MySQL 辅助工具 (openclaw-v4)",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("sync", help="同步 AI 四表结构").set_defaults(func=cmd_sync)

    pc = sub.add_parser("checkpoint", help="读取某账号最近一次 checkpoint")
    pc.add_argument("account")
    pc.set_defaults(func=cmd_checkpoint)

    pf = sub.add_parser("fetch", help="读取断点之后的待分析推文")
    pf.add_argument("account")
    pf.add_argument("--limit", type=int, default=DEFAULT_BATCH_LIMIT,
                    help=f"单批上限，默认 {DEFAULT_BATCH_LIMIT}")
    pf.set_defaults(func=cmd_fetch)

    pw = sub.add_parser("write-run", help="从 stdin 读 JSON 写入一个完整 run")
    pw.set_defaults(func=cmd_write_run)

    pv = sub.add_parser("verify", help="检查某账号是否有重复分析")
    pv.add_argument("account")
    pv.set_defaults(func=cmd_verify)
    return p


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
