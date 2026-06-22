#!/usr/bin/env python3
"""生成 elonmusk 账号本批 run JSON（AI 语义判断，openclaw-v4）。

按 prompt 规则：仅当语境与 Tesla 相关时映射 TSLA；纯 SpaceX/xAI/Grok/Starship
的内容不映射 ticker（这些公司未上市或无对应 $ticker）。elonmusk 少 explicit buy，
故多数为 neutral，明确产品/技术利好才给 buy。
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone

BATCH = json.load(open("/tmp/stock-ai/elonmusk.json"))
POSTS = BATCH["posts"]
BY_ID = {p["post_id"]: p for p in POSTS}
RESUME_FROM_POST_ID = BATCH["resume_from_post_id"]
RESUME_FROM_CREATED_AT = BATCH["resume_from_created_at"]

# post_id -> [(ticker, rec, conf, reasoning), ...]
# 仅 Tesla 语境相关帖映射 TSLA；其余 67 条语境帖中纯 SpaceX/xAI/Grok 不映射
JUDGEMENTS: dict[str, list[tuple[str, str, float, str]]] = {
    "2006014310607167607": [("TSLA", "buy", 0.55, "称Tesla/SpaceX股权为其主要财富，价值随有用产品产出上升")],
    "2009169229690601494": [("TSLA", "neutral", 0.4, "个人生活帖提及Tesla，无财经信号")],
    "2011859750766383271": [("TSLA", "buy", 0.55, "'Optimustic'双关，对Optimus前景乐观")],
    "2012264588071391404": [("TSLA", "buy", 0.6, "'Cybertruck is the best vehicle Tesla has ever made'强产品评价")],
    "2013913509621289081": [("TSLA", "buy", 0.55, "Optimus将superset一切，愿景利好")],
    "2014039116854300810": [("TSLA", "buy", 0.62, "Tesla FSD激活使保险半价，安全性大幅提升")],
    "2016951758510022903": [("TSLA", "buy", 0.55, "Optimus+space AI未来产出远超地球，愿景乐观")],
    "2021663314716373227": [("TSLA", "buy", 0.55, "辩护Tesla/SpaceX政府资金仅占合计价值1%，回应质疑")],
    "2023158948501594300": [("TSLA", "neutral", 0.45, "陈述净财富主要来自Tesla/SpaceX股权，非信号")],
    "2028239958977511615": [("TSLA", "buy", 0.58, "Tesla AI4算力仅H100 1/4却能理解驾驶复杂性，效率利好")],
    "2031751255060885911": [("TSLA", "buy", 0.6, "Macrohard/Digital Optimus为xAI-Tesla联合项目，Grok为导航，协同利好")],
    "2034439451611680818": [("TSLA", "buy", 0.6, "AI5将punch above weight，Tesla AI软件栈最大化每电路效用")],
    "2035259500064907571": [("TSLA", "buy", 0.58, "Optimus+PV将成为冯诺依曼探测器，自复制机器愿景")],
    "2035506574182199757": [("TSLA", "buy", 0.65, "正式宣布TERAFAB项目，SpaceX+Tesla联合，目标万亿瓦算力/年")],
    "2035526376468394305": [("TSLA", "buy", 0.65, "SpaceXAI+Tesla TERAFAB万亿瓦算力，须上太空(美国仅0.5TW)")],
    "2036665153778000143": [("TSLA", "neutral", 0.45, "仅发Optimus图，无明确信号")],
    "2039202381683110191": [("TSLA", "neutral", 0.48, "Model S&X定制单结束，产品线调整中性偏谨慎")],
    "2044315118583066738": [("TSLA", "buy", 0.62, "Tesla AI5芯片tape out，AI6/Dojo3路线图推进")],
    "2044963895216095319": [("TSLA", "neutral", 0.45, "表情回应Tesla，无实质信号")],
    "2045309037848272993": [("TSLA", "buy", 0.6, "Tesla从物理第一性原理重设计锂精炼，降本利好")],
    "2045328655140680076": [("TSLA", "neutral", 0.45, "澄清SpaceX/Tesla是TSMC客户非竞争者，关系陈述")],
    "2045374796205039659": [("TSLA", "neutral", 0.45, "Robotaxi'harder than it looks'承认难度")],
    "2045572944420901265": [("TSLA", "buy", 0.6, "Tesla Robotaxi在Dallas&Houston上线试运营")],
    "2046013308051009791": [("TSLA", "neutral", 0.5, "FSD中国待批，上海产能为限制因素，中性偏观望")],
}


def _excerpt(text: str, limit: int = 480) -> str:
    return (text or "").replace("\n", " ").strip()[:limit]


def main() -> None:
    signals = []
    ticker_dates = defaultdict(list)
    for pid, judgements in JUDGEMENTS.items():
        p = BY_ID.get(pid)
        if not p:
            raise SystemExit(f"missing {pid}")
        for ticker, rec, conf, reasoning in judgements:
            signals.append({
                "post_id": pid,
                "ticker": ticker,
                "recommendation": rec,
                "confidence": conf,
                "reasoning": reasoning,
                "post_text_excerpt": _excerpt(p.get("text", "")),
                "post_created_at": p["created_at"],
                "post_score": int(p.get("score", 0) or 0),
            })
            ticker_dates[ticker].append((p["created_at"][:10], rec))

    # consensus（全窗口，本批即首次全窗口）
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
            "consensus_date": date,
            "ticker": ticker,
            "consensus_signal": sig,
            "buy_count": buy,
            "sell_count": sell,
            "hold_count": hold,
            "reasoning": f"{date} elonmusk 对 {ticker} buy {buy}/sell {sell}/hold {hold}，判定 {sig}。多数为产品/技术宣传隐含利好，少 explicit buy。仅供参考，非投资建议。",
        })

    # top_tickers
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
            "latest_signal": latest[ticker], "top_authors": ["elonmusk"],
            "ai_summary": f"{ticker} 被提及 {mc} 次（buy {buys[ticker]}/sell {sells[ticker]}/hold {holds[ticker]}）。elonmusk 推文多为 Tesla 产品/技术宣传，少 explicit buy。仅供参考，非投资建议。",
        })

    now = datetime.now(timezone.utc)
    run_id = now.strftime("%Y%m%dT%H%M%SZ") + "_ai_elonmusk"
    last_post = POSTS[-1]

    payload = {
        "run_id": run_id, "account": "elonmusk",
        "window_start": POSTS[0]["created_at"], "window_end": last_post["created_at"],
        "post_count": len(POSTS), "signal_count": len(signals),
        "consensus_count": len(consensus), "top_ticker_count": len(top),
        "model": "glm-5.2", "prompt_version": "openclaw-v4", "status": "partial",
        "summary": (
            f"本批处理 {len(POSTS)} 帖（断点 NULL→{last_post['post_id']}）。"
            f"elonmusk 推文 0 条显式 $TICKER，按 prompt 规则仅对 Tesla 语境相关帖做 TSLA 语义映射，"
            f"生成 {len(signals)} 条 TSLA signals（多数 neutral，明确产品/技术/战略利好才 buy，如 TERAFAB 万亿瓦算力、AI5 芯片 tape out、Robotaxi 上线、锂精炼重设计）。"
            f"纯 SpaceX/xAI/Grok/Starship 内容不映射 ticker（未上市或无对应标的）。"
            f"仍有 {BATCH['remaining_estimate']} 帖未处理，下次从 checkpoint 继续。仅供参考，非投资建议。"
        ),
        "analyzed_at": now.strftime("%Y-%m-%d %H:%M:%S.%f"),
        "resume_from_post_id": RESUME_FROM_POST_ID, "resume_from_created_at": RESUME_FROM_CREATED_AT,
        "checkpoint_post_id": last_post["post_id"], "checkpoint_post_created_at": last_post["created_at"],
        "signals": signals, "consensus": consensus, "top_tickers": top,
    }
    json.dump(payload, open("/tmp/stock-ai/elon_run.json", "w"), ensure_ascii=False, indent=1)
    print(f"signals={len(signals)} consensus={len(consensus)} top={len(top)} status=partial checkpoint={last_post['post_id']}")


if __name__ == "__main__":
    main()
