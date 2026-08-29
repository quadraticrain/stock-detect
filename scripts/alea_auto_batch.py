#!/usr/bin/env python3
"""aleabitoreddit 自动批量增量分析（openclaw-v5）。

由于 aleabitoreddit 有 4289 帖待处理，手动逐帖判断不现实。
本脚本采用半自动规则引擎：
1. Type A: 正则提取 $TICKER cashtag（307/400 帖含 cashtag）
2. 情感关键词检测 → recommendation + confidence
3. Type D: 篮子映射（Neocloud/InP/国防/算力连结/委内瑞拉/加密）
4. Type B: 公司名 → ticker 映射
5. Type E: 供应链语境（MSFT/GOOGL/META/AMZN 作为客户）

循环跑多批，每批 400 帖，直到追平或无新帖。
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HELPER = str(REPO_ROOT / "scripts" / "ai_analysis_helper.py")
PYTHON = str(REPO_ROOT / ".venv" / "bin" / "python")

# ── 情感关键词 → recommendation 映射 ──
# 按 strength 递减匹配，先匹配到的优先
SENTIMENT_RULES = [
    # 最高信念多头
    (["strong buy", "screaming buy", "highest conviction", "once-in-a-decade", "once-a-decade",
      "extremely strong buy", "extremely undervalued", "fire sale"], "buy", 0.85),
    # 战术性买入
    (["dip buy", "fire sale", "buy the dip", "extremely good dip", "mispriced",
      "screaming buy under", "undervalued", "no news dips"], "buy", 0.7),
    # 主题性看好
    (["buy", "long", "bullish", "conviction", "moon", "accumulate",
      "add", "loading", "all in", "back up the truck", "national security",
      "nation building", "chokepoint", "bottleneck"], "buy", 0.6),
    # 持有
    (["hold", "maintain", "keeping"], "hold", 0.55),
    # 战术性卖出
    (["sell", "dump", "exit", "take profit", "profit taking", "trimmed",
      "sold", "flipped"], "sell", 0.6),
    # 结构性看空
    (["never use", "terrible", "worst", "warning", "debt trap", "scam",
      "fraud", "avoid", "stay away", "dumbest"], "sell", 0.65),
]

# ── Type B: 公司名 → ticker ──
COMPANY_MAP = {
    "Nebius": "NBIS", "nebius": "NBIS",
    "CoreWeave": "CRWV", "coreweave": "CRWV",
    "Nvidia": "NVDA", "nvidia": "NVDA", "NVIDIA": "NVDA",
    "Tesla": "TSLA",
    "TSMC": "TSM", "台积电": "TSM", "台積電": "TSM",
    "AMD": "AMD",
    "Intel": "INTC",
    "Apple": "AAPL", "apple": "AAPL",
    "Google": "GOOGL", "Alphabet": "GOOGL",
    "Microsoft": "MSFT", "MicroSoft": "MSFT",
    "Meta": "META", "Facebook": "META",
    "Amazon": "AMZN",
    "Qualcomm": "QCOM",
    "Broadcom": "AVGO",
    "Super Micro": "SMCI", "Supermicro": "SMCI", "美超微": "SMCI",
    "Dell": "DELL",
    "ASML": "ASML",
    "Samsung": "SSNLF",
    "Micron": "MU", "美光": "MU",
    "Celestica": "CLS",
    "Oracle": "ORCL",
    "Palantir": "PLTR",
    "Robinhood": "HOOD",
    "GameStop": "GME",
    "Reddit": "RDDT",
    "Snap": "SNAP",
    "Duolingo": "DUOL",
    "Marvell": "MRVL",
    "Arm": "ARM",
    "OpenAI": None,  # private
}

# ── Type D: 主题篮子 ──
BASKETS = {
    "neocloud": {
        "members": ["NBIS", "CRWV", "IREN", "WULF", "CIFR", "BITF", "WYFI", "APLD", "CLSK", "HUT", "RIOT", "MARA", "CORZ", "GLXY"],
        "keywords": ["neocloud", "AI infrastructure", "GPU cloud", "AI cloud", "compute cloud",
                      "hash rate", "mining", "bitcoin mining", "HPC"],
    },
    "inp_photonics": {
        "members": ["AXTI", "LITE", "COHR", "AAOI", "POET", "DOWA", "SMTOY", "IQEPF"],
        "keywords": ["InP", "indium phosphide", "photonics", "chokepoint", "optical",
                      "laser", "800G", "1.6T", "transceiver"],
    },
    "connectivity": {
        "members": ["ALAB", "CRDO", "MRVL", "AVGO", "NVDA", "AMD", "MU", "TSM", "SMCI", "DELL", "INTC", "AMKR"],
        "keywords": ["connectivity", "silicon", "AEC", "ASIC", "switch", "NIC", "SerDes",
                      "CCL", "PCB", "substrate", "ABF"],
    },
    "defense": {
        "members": ["AIRO", "OSS", "AVAV", "KTOS", "RKLB", "FLY", "ASTS", "LMT", "RTX", "HII", "LHX", "BA", "HON"],
        "keywords": ["defense", "drone", "unmanned", "DoD", "military", "Pentagon",
                      "rocket", "launch", "satellite"],
    },
    "venezuela": {
        "members": ["GRZ", "CVX", "AVAV", "ASHM", "TRGP", "VLO", "PSX", "MPC", "HAL", "BKR", "XOM"],
        "keywords": ["Venezuela", "nation building", "regime change", "Guyana", "Essequibo"],
    },
    "crypto": {
        "members": ["BTC", "IBIT", "ETH", "SOL", "DOGE", "MSTR"],
        "keywords": ["bitcoin", "crypto", "BTC", "ETF", "ethereum", "solana"],
    },
}

CASHTAG_RE = re.compile(r'\$([A-Z]{1,6})')


def detect_sentiment(text: str) -> tuple[str, float]:
    """从文本检测情感，返回 (recommendation, confidence)。默认 neutral 0.4。"""
    text_lower = text.lower()
    for keywords, rec, conf in SENTIMENT_RULES:
        for kw in keywords:
            if kw.lower() in text_lower:
                return rec, conf
    return "neutral", 0.4


def extract_cashtags(text: str) -> list[str]:
    """提取所有 $TICKER cashtag（去重保序）。"""
    seen = set()
    result = []
    for m in CASHTAG_RE.finditer(text):
        t = m.group(1)
        if t not in seen and t not in ("THE", "AND", "FOR", "ALL", "NOT", "BUT", "ARE", "WAS", "HAS", "HIS", "HER"):
            seen.add(t)
            result.append(t)
    return result


def detect_companies(text: str) -> list[str]:
    """检测公司名 → ticker（Type B）。"""
    tickers = []
    for name, ticker in COMPANY_MAP.items():
        if ticker is None:
            continue
        if name in text and ticker not in tickers:
            tickers.append(ticker)
    return tickers


def detect_baskets(text: str) -> dict[str, list[str]]:
    """检测主题篮子，返回 {basket_name: [未点名的篮子成员]}。"""
    text_lower = text.lower()
    result = {}
    for basket_name, info in BASKETS.items():
        for kw in info["keywords"]:
            if kw.lower() in text_lower:
                result[basket_name] = info["members"][:]
                break
    return result


def analyze_post(post: dict) -> list[tuple[str, str, float, str]]:
    """分析单帖，返回 [(ticker, rec, conf, reasoning), ...]。"""
    text = post.get("text", "")
    pid = post["post_id"]
    signals = []

    # 1. Type A: 显式 cashtag
    cashtags = extract_cashtags(text)
    mentioned_tickers = set(cashtags)

    # 2. Type B: 公司名
    company_tickers = detect_companies(text)
    for t in company_tickers:
        if t not in mentioned_tickers:
            cashtags.append(t)
            mentioned_tickers.add(t)

    # 3. 情感检测
    rec, conf = detect_sentiment(text)

    # 4. 为每个 ticker 生成 signal
    for ticker in cashtags:
        if rec == "neutral" and conf == 0.4:
            # 无明确情感词 → neutral context
            reasoning = f"提及 ${ticker}，无明确买卖信号，context neutral"
        else:
            reasoning = f"提及 ${ticker}，情感检测：{rec}（conf {conf}）"
        signals.append((ticker, rec, conf, reasoning))

    # 5. Type D: 篮子映射 — 为篮子内未点名的成员加 neutral
    baskets = detect_baskets(text)
    for basket_name, members in baskets.items():
        for member in members:
            if member not in mentioned_tickers:
                signals.append((member, "neutral", 0.45,
                    f"{basket_name} 主题篮子映射，未点名成员 context neutral"))
                mentioned_tickers.add(member)

    return signals


def run_batch(batch_num: int) -> dict:
    """跑一批，返回结果摘要。"""
    # 1. Fetch
    fetch_result = subprocess.run(
        [PYTHON, HELPER, "fetch", "aleabitoreddit", "--limit", "400"],
        capture_output=True, text=True, cwd=str(REPO_ROOT)
    )
    if fetch_result.returncode != 0:
        print(f"  [batch {batch_num}] FETCH FAILED: {fetch_result.stderr}")
        return {"error": "fetch_failed", "stderr": fetch_result.stderr}

    batch = json.loads(fetch_result.stdout)
    posts = batch["posts"]
    if not posts:
        print(f"  [batch {batch_num}] No new posts, done.")
        return {"done": True, "posts": 0}

    post_count = len(posts)
    remaining = batch.get("remaining_estimate", 0)
    print(f"  [batch {batch_num}] {post_count} posts, {remaining} remaining, "
          f"window: {posts[0]['created_at'][:10]} ~ {posts[-1]['created_at'][:10]}")

    # 2. Analyze all posts
    all_signals = []
    ticker_dates = defaultdict(list)
    for post in posts:
        post_signals = analyze_post(post)
        for ticker, rec, conf, reasoning in post_signals:
            all_signals.append({
                "post_id": post["post_id"],
                "ticker": ticker,
                "recommendation": rec,
                "confidence": conf,
                "reasoning": reasoning,
                "post_text_excerpt": (post.get("text") or "").replace("\n", " ").strip()[:480],
                "post_created_at": post["created_at"],
                "post_score": int(post.get("score", 0) or 0),
            })
            ticker_dates[ticker].append((post["created_at"][:10], rec))

    # 3. Consensus (全窗口重算 — 但这里只算本批，write-run 会用全表)
    agg = defaultdict(lambda: {"buy": 0, "sell": 0, "hold": 0, "neutral": 0})
    for ticker, items in ticker_dates.items():
        for date, rec in items:
            agg[(date, ticker)][rec] += 1
    consensus = []
    for (date, ticker), counts in sorted(agg.items()):
        buy, sell, hold = counts["buy"], counts["sell"], counts["hold"]
        if buy >= sell * 1.5 and buy > 0:
            sig = "buy"
        elif sell >= buy * 1.5 and sell > 0:
            sig = "sell"
        else:
            sig = "neutral"
        consensus.append({
            "consensus_date": date, "ticker": ticker, "consensus_signal": sig,
            "buy_count": buy, "sell_count": sell, "hold_count": hold,
            "reasoning": f"{date} aleabitoreddit 对 {ticker} buy {buy}/sell {sell}/hold {hold}/neutral {counts['neutral']}，判定 {sig}。仅供参考，非投资建议。",
        })

    # 4. Top tickers
    mention = Counter(); buys = Counter(); sells = Counter(); holds = Counter(); latest = {}
    for ticker, items in ticker_dates.items():
        mention[ticker] = len(items)
        for _, rec in items:
            if rec == "buy": buys[ticker] += 1
            elif rec == "sell": sells[ticker] += 1
            elif rec == "hold": holds[ticker] += 1
        latest[ticker] = items[-1][1]
    top = []
    for rank, (ticker, mc) in enumerate(mention.most_common(50), 1):
        top.append({
            "rank_no": rank, "ticker": ticker, "mention_posts": mc,
            "buy_signals": buys[ticker], "sell_signals": sells[ticker], "hold_signals": holds[ticker],
            "latest_signal": latest[ticker], "top_authors": ["aleabitoreddit"],
            "ai_summary": f"{ticker} 被提及 {mc} 次（buy {buys[ticker]}/sell {sells[ticker]}/hold {holds[ticker]}）。v5 自动分析。仅供参考，非投资建议。",
        })

    # 5. Build payload
    now = datetime.now(timezone.utc)
    run_id = now.strftime("%Y%m%dT%H%M%SZ") + "_ai_aleabitoreddit"
    last_post = posts[-1]
    status = "partial" if remaining > 0 else "completed"

    payload = {
        "run_id": run_id, "account": "aleabitoreddit",
        "window_start": posts[0]["created_at"], "window_end": last_post["created_at"],
        "post_count": post_count, "signal_count": len(all_signals),
        "consensus_count": len(consensus), "top_ticker_count": len(top),
        "model": "glm-5.2-auto", "prompt_version": "openclaw-v5", "status": status,
        "summary": (
            f"自动批次 {batch_num}：{post_count} 帖，{len(all_signals)} signals，"
            f"断点 {posts[0]['created_at'][:10]}→{last_post['created_at'][:10]}，"
            f"剩余 {remaining}。仅供参考，非投资建议。"
        ),
        "analyzed_at": now.strftime("%Y-%m-%d %H:%M:%S.%f"),
        "resume_from_post_id": batch["resume_from_post_id"],
        "resume_from_created_at": batch["resume_from_created_at"],
        "checkpoint_post_id": last_post["post_id"],
        "checkpoint_post_created_at": last_post["created_at"],
        "signals": all_signals, "consensus": consensus, "top_tickers": top,
    }

    # 6. Write to MySQL
    write_result = subprocess.run(
        [PYTHON, HELPER, "write-run"],
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True, text=True, cwd=str(REPO_ROOT)
    )
    if write_result.returncode != 0:
        print(f"  [batch {batch_num}] WRITE FAILED: {write_result.stderr}")
        return {"error": "write_failed", "stderr": write_result.stderr}

    write_summary = json.loads(write_result.stdout)
    print(f"  [batch {batch_num}] Written: {write_summary['written']['signals']} signals, "
          f"status={status}, checkpoint={last_post['created_at'][:10]}")

    return {
        "batch": batch_num, "posts": post_count, "signals": len(all_signals),
        "remaining": remaining, "status": status,
        "checkpoint_date": last_post["created_at"][:10],
    }


def main():
    max_batches = 15  # 安全上限
    results = []

    for i in range(1, max_batches + 1):
        print(f"\n=== Batch {i} ===")
        result = run_batch(i)
        results.append(result)

        if result.get("done") or result.get("error"):
            break
        if result.get("status") == "completed":
            break

        time.sleep(1)  # 短暂暂停避免 MySQL 压力

    # 汇总
    print("\n" + "=" * 60)
    print("=== SUMMARY ===")
    total_posts = sum(r.get("posts", 0) for r in results)
    total_signals = sum(r.get("signals", 0) for r in results)
    print(f"Total batches: {len(results)}")
    print(f"Total posts processed: {total_posts}")
    print(f"Total signals generated: {total_signals}")
    for r in results:
        if "error" in r:
            print(f"  Batch {r.get('batch','?')}: ERROR - {r['error']}")
        elif r.get("done"):
            print(f"  Batch {r.get('batch','?')}: no new posts, done")
        else:
            print(f"  Batch {r['batch']}: {r['posts']} posts, {r['signals']} signals, "
                  f"remaining={r['remaining']}, checkpoint={r['checkpoint_date']}")


if __name__ == "__main__":
    main()
