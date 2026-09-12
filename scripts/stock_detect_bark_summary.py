#!/usr/bin/env python3
"""stock-detect 周报 Bark 汇总推送。

在 AI 舆情分析任务（每周日）跑完后执行：读取本次各账号最新 run，
按「提及次数」挑出重点股票，组装一条汇总消息推送到 Bark。

用法：
    .venv/bin/python scripts/stock_detect_bark_summary.py            # 分析并推送
    .venv/bin/python scripts/stock_detect_bark_summary.py --dry-run  # 只打印，不推送
    .venv/bin/python scripts/stock_detect_bark_summary.py --days 30  # 放宽 run 的创建时间窗口
    .venv/bin/python scripts/stock_detect_bark_summary.py --force    # 忽略断点强制重推
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

# 仓库根目录（本脚本位于 <repo>/scripts/ 下）
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import pymysql  # noqa: E402
import requests  # noqa: E402

from stock_detect import config  # noqa: E402
from stock_detect.env import load_env  # noqa: E402

BARK_PUSH_URL = "https://api.day.app/CXFgAnMVdZXTPvsKRgWKFo"

# 中文名来源（按优先级），均为后端代码，实时解析：
#   1. search.go 的 AllSupportStock（后端主目录）
#   2. stock_detect_chinese_names.go 的 StockDetectChineseNames（舆情推送补充目录）
# 两处都找不到就直接用股票代码，**不在本脚本里写死任何名字**。
# 推送里出现 $TICKER 就是信号：该标的还没被后端收录，可提 PR 增补。
# 后端仓库与 stock-detect 同级，均位于 /Users/rainlu/Documents/work/ 下。
GCS_ROOT = REPO_ROOT.parent / "GolangCalculateServer"
SEARCH_GO = str(GCS_ROOT / "service" / "search.go")
CHINESE_NAMES_GO = str(GCS_ROOT / "service" / "stock_detect_chinese_names.go")

# 推送断点：记住每个账号最后推过的 run_id，避免重复推送。
# run_id 形如 20260809T033546Z_ai_xxx，本身就是单调递增的排序键，
# 不需要额外的自增 ID。
STATE_PATH = str(REPO_ROOT / ".workbuddy" / "state" / "stock_detect_bark_state.json")

# 默认只看最近 14 天内创建（analyzed_at）的 run：
# 它是纯创建时间（无 ON UPDATE），周任务偶尔跳一次也能补上；
# 重复推送由上面的 run_id 断点拦住，窗口放宽不会造成重推。
DEFAULT_WINDOW_DAYS = 14


def load_chinese_names() -> dict[str, str]:
    """从后端代码解析「代码 → 中文名」。

    两个来源都在 GolangCalculateServer 里，本脚本不自带任何名字。
    """
    names: dict[str, str] = {}

    # 1) 后端主目录 AllSupportStock
    try:
        src = open(SEARCH_GO, encoding="utf-8").read()
    except OSError as exc:
        print(f"警告：读不到 {SEARCH_GO}（{exc}）")
    else:
        for symbol, body in re.findall(r'\{\s*Symbol:\s*"([^"]+)",(.*?)\n\t\},', src, re.S):
            match = re.search(r'ChineseName:\s*"([^"]*)"', body)
            if match and match.group(1):
                names[symbol] = match.group(1)
                # 港股等带后缀的（TCH.HK），裸代码也登记一份
                names.setdefault(symbol.split(".")[0], match.group(1))
    main_count = len(names)

    # 2) 舆情推送补充目录 StockDetectChineseNames
    try:
        src = open(CHINESE_NAMES_GO, encoding="utf-8").read()
    except OSError as exc:
        print(f"警告：读不到 {CHINESE_NAMES_GO}（{exc}）")
    else:
        block = re.search(r"StockDetectChineseNames\s*=\s*map\[string\]string\{(.*?)\n\}",
                          src, re.S)
        if block:
            for symbol, name in re.findall(r'"([^"]+)"\s*:\s*"([^"]+)"', block.group(1)):
                names.setdefault(symbol, name)
        else:
            print(f"警告：在 {CHINESE_NAMES_GO} 里没找到 StockDetectChineseNames")

    print(f"中文名词典：{main_count} 条（AllSupportStock）"
          f" + {len(names) - main_count} 条（StockDetectChineseNames）")
    return names


def display_ticker(ticker: str, names: dict[str, str]) -> str:
    """后端有中文名 →「中文名(TICKER)」；找不到 → 直接用 $TICKER。"""
    cn = names.get(ticker) or names.get(ticker.upper())
    return f"{cn}({ticker})" if cn else f"${ticker}"

# 账号 → 推送里显示的名字。只有这里列出的账号会进入汇总。
# 与 AI_ANALYSIS.md 的定时账号保持一致；elonmusk / justinsuntron / sunyuchentron
# 等已停止关注的账号，以及历史拼错的 aleaboreddit，都不会被推送。
ACCOUNT_LABELS = {
    "aleabitoreddit": "Alea",
    "mingchikuo": "郭明錤",
    "xueqiu:1247347556": "段永平",
    "xueqiu:1102105103": "但斌",
}

# 共识买入门槛：该博主至少在这么多帖里提到，且买入信号多于卖出
MIN_MENTIONS_FOR_CONSENSUS = 2
# 每个博主分组内，共识买入 / 其他提及各自最多列几个
MAX_CONSENSUS_TICKERS = 5
MAX_PER_ACCOUNT_TICKERS = 5


def connect():
    load_env()
    password = os.environ.get("MYSQL_PASSWORD")
    if not password:
        raise SystemExit(f"MYSQL_PASSWORD 未设置（检查 {REPO_ROOT / '.env'}）")
    return pymysql.connect(
        host=config.MYSQL_HOST,
        port=config.MYSQL_PORT,
        user=config.MYSQL_USER,
        password=password,
        database=config.MYSQL_DATABASE,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def latest_runs(conn, days: int) -> list[dict]:
    """每个账号取最近一次 completed/partial 的 run。

    analyzed_at 是 run 的**创建时间**（该列无 ON UPDATE，写入后不变）。
    """
    cutoff = dt.datetime.utcnow() - dt.timedelta(days=days)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT r.*
            FROM stock_detect_ai_runs r
            JOIN (
                SELECT account, MAX(analyzed_at) AS latest
                FROM stock_detect_ai_runs
                WHERE status IN ('completed', 'partial')
                  AND analyzed_at >= %s
                  AND account IN %s
                GROUP BY account
            ) m ON m.account = r.account AND m.latest = r.analyzed_at
            ORDER BY r.account
            """,
            (cutoff, tuple(ACCOUNT_LABELS)),
        )
        return list(cur.fetchall())


def load_state() -> dict:
    try:
        with open(STATE_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def save_state(state: dict) -> None:
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_PATH)  # 原子替换，避免写一半坏掉


def filter_new_runs(runs: list[dict], state: dict) -> list[dict]:
    """丢弃已经推过的 run（按 run_id 断点）。"""
    pushed = state.get("last_pushed_run_id", {})
    fresh = []
    for run in runs:
        if pushed.get(run["account"]) == run["run_id"]:
            print(f"  跳过 {run['account']}：run {run['run_id']} 已推过")
            continue
        fresh.append(run)
    return fresh


def top_tickers(conn, run_id: str) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT rank_no, ticker, mention_posts, buy_signals, sell_signals,
                   hold_signals, latest_signal
            FROM stock_detect_ai_top_tickers
            WHERE run_id = %s
            ORDER BY mention_posts DESC, buy_signals DESC, rank_no ASC
            """,
            (run_id,),
        )
        return list(cur.fetchall())


def build_message(runs: list[dict], per_run_tickers: dict[str, list[dict]],
                  names: dict[str, str]) -> tuple[str, str] | None:
    """按博主分组组装推送正文，每个博主下面再分共识买入 / 其他提及。"""
    total_posts = sum(r["post_count"] or 0 for r in runs)

    blocks: list[str] = []
    for run in runs:
        rows = per_run_tickers.get(run["run_id"], [])
        if not rows:
            continue
        label = ACCOUNT_LABELS[run["account"]]

        # 该博主的共识买入：提及够多 + 买入压过卖出
        consensus = [
            r for r in rows
            if (r["mention_posts"] or 0) >= MIN_MENTIONS_FOR_CONSENSUS
            and (r["buy_signals"] or 0) > (r["sell_signals"] or 0)
        ]
        consensus.sort(key=lambda r: (-(r["mention_posts"] or 0), -(r["buy_signals"] or 0), r["ticker"]))
        # 记下所有符合共识条件的（包括被数量上限挤掉的），
        # 避免它们回流到「提及」里造成误导
        consensus_tickers = {r["ticker"] for r in consensus}
        consensus = consensus[:MAX_CONSENSUS_TICKERS]

        # 其他提及：没进共识买入的，仍按提及数排
        others = [r for r in rows if r["ticker"] not in consensus_tickers][:MAX_PER_ACCOUNT_TICKERS]

        lines = [f"【{label}】{run['post_count'] or 0} 帖"]
        if consensus:
            picks = "、".join(
                f"{display_ticker(r['ticker'], names)}×{r['mention_posts']}" for r in consensus
            )
            lines.append(f"  共识买入：{picks}")
        if others:
            picks = "、".join(
                f"{display_ticker(r['ticker'], names)}×{r['mention_posts']}" for r in others
            )
            lines.append(f"  提及：{picks}")
        blocks.append("\n".join(lines))

    if not blocks:
        return None

    title = f"📈 stock-detect 周报｜共 {total_posts} 帖"
    body = "\n".join(blocks)
    return title, body


def push_bark(title: str, body: str) -> None:
    resp = requests.post(
        BARK_PUSH_URL,
        json={
            "title": title,
            "body": body,
            "group": "stock-detect",
            "level": "active",
        },
        timeout=15,
    )
    resp.raise_for_status()
    print("Bark 推送成功:", resp.text[:200])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="只打印，不推送（不写断点）")
    parser.add_argument("--days", type=int, default=DEFAULT_WINDOW_DAYS,
                        help=f"只看最近 N 天内创建的 run（默认 {DEFAULT_WINDOW_DAYS}）")
    parser.add_argument("--force", action="store_true",
                        help="忽略断点，强制重推（补推/调试用）")
    args = parser.parse_args()

    conn = connect()
    try:
        runs = latest_runs(conn, args.days)
        if not runs:
            print(f"最近 {args.days} 天内没有 AI run，跳过推送")
            return 0

        state = load_state()
        if args.force:
            print("[force] 忽略推送断点")
        else:
            runs = filter_new_runs(runs, state)
            if not runs:
                print("所有账号的最新 run 都已推过，跳过推送")
                return 0

        per_run = {r["run_id"]: top_tickers(conn, r["run_id"]) for r in runs}
    finally:
        conn.close()

    print("参与汇总的 run:")
    for r in runs:
        print(f"  {r['account']:22s} {r['run_id']} posts={r['post_count']} "
              f"signals={r['signal_count']} status={r['status']} "
              f"analyzed_at={r['analyzed_at']} tickers={len(per_run[r['run_id']])}")

    names = load_chinese_names()

    built = build_message(runs, per_run, names)
    if built is None:
        print("本次没有任何 ticker 数据，跳过推送")
        return 0

    title, body = built
    print("\n--- 推送内容 ---")
    print(title)
    print(body)
    print(f"（{len(body)} 字）")

    if args.dry_run:
        print("\n[dry-run] 未实际推送，断点也未更新")
        return 0

    push_bark(title, body)

    # 推送成功才写断点；推失败会抛异常，下次还能重试
    state.setdefault("last_pushed_run_id", {})
    for run in runs:
        state["last_pushed_run_id"][run["account"]] = run["run_id"]
    state["last_pushed_at"] = dt.datetime.now().isoformat(timespec="seconds")
    save_state(state)
    print(f"断点已更新: {STATE_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
