#!/usr/bin/env python3
"""生成 elonmusk 账号本批 run JSON（AI 语义判断，openclaw-v5.1）。

v5.1 规则变更（vs v5）：
- SpaceX 已于 2026-06-12 在 NASDAQ IPO（代码 SPCX），xAI 已并入 SpaceX
- SpaceX/Starlink/xAI/Grok/Starship 提及 → SPCX 直接映射（类型 B）
- 同时保留 TSLA 次要传导信号（Musk 财富集中效应，confidence 0.4-0.5）
- Optimus/Neuralink 仍为未上市实体 → TSLA（Type C 影响传导）
- TSMC 供应链语境 → TSM；BTC/DOGE 加密提及 → BTC
- elonmusk 因少 explicit buy，confidence 整体下调 0.1
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
# v5.1: SpaceX/Starlink/xAI/Grok/Starship → SPCX（直接映射）；Optimus/Neuralink → TSLA（Type C）；TSMC→TSM；DOGE→BTC
JUDGEMENTS: dict[str, list[tuple[str, str, float, str]]] = {
    # ── 2025-12 ──
    "2003894829424824683": [("SPCX", "neutral", 0.5, "SpaceX 愿景帖，直接映射 SPCX（已上市），纯哲学无明确利好"), ("TSLA", "neutral", 0.4, "Musk 财富集中传导 TSLA，弱")],
    "2006014310607167607": [("SPCX", "buy", 0.55, "称 Tesla/SpaceX 股权为主要财富，SpaceX → SPCX 直接利好"), ("TSLA", "buy", 0.5, "Tesla 股权同时利好 TSLA")],
    "2006108047609930069": [("SPCX", "buy", 0.55, "xAI 买第三栋楼算力达 2GW，xAI 已并入 SpaceX → SPCX"), ("TSLA", "neutral", 0.45, "xAI-Tesla JV 协同传导 TSLA")],
    "2006834169637384470": [("SPCX", "neutral", 0.45, "Grok 救人故事，Grok 属 SpaceX 生态，SPCX 粘性利好")],

    # ── 2026-01 ──
    "2008786684058759375": [("SPCX", "neutral", 0.42, "'Grok is on the side of the angels'产品评价，SPCX 弱传导")],
    "2009169229690601494": [("TSLA", "neutral", 0.4, "个人生活帖提及 Tesla，无财经信号")],
    "2011859750766383271": [("TSLA", "buy", 0.5, "'Optimustic'双关，Optimus 为 Tesla 产品线，愿景传导 TSLA")],
    "2012264588071391404": [("TSLA", "buy", 0.55, "'Cybertruck is the best vehicle Tesla has ever made'强产品评价 TSLA")],
    "2013913509621289081": [("TSLA", "buy", 0.5, "Optimus 将 superset 一切，Tesla 人形机器人愿景传导 TSLA")],
    "2014039116854300810": [("TSLA", "buy", 0.6, "Tesla FSD 激活使保险半价，安全性大幅提升，产品利好 TSLA")],
    "2014257541652291939": [("SPCX", "neutral", 0.42, "Grok 视频模式功能介绍，Grok 属 SpaceX 生态 SPCX")],
    "2014881720948973907": [("SPCX", "neutral", 0.45, "xAI 团队做 For You AI 分栏，xAI 属 SpaceX → SPCX"), ("TSLA", "neutral", 0.4, "xAI-Tesla AI 战略一体化传导")],
    "2016381026809868635": [("SPCX", "neutral", 0.4, "'Can you Imagine?'Grok Imagine 生态，SPCX 弱传导")],
    "2016575739655504070": [("TSLA", "neutral", 0.42, "Neuralink 团队成果，关联实体弱传导 TSLA（Type C，仍未上市）")],
    "2016951758510022903": [("TSLA", "buy", 0.5, "Optimus+space AI 未来产出远超地球，Optimus 为 Tesla 产品 TSLA")],
    "2016974845477568675": [("SPCX", "neutral", 0.42, "Grok Imagine 1.0 生成量超所有人，Grok 属 SpaceX SPCX")],
    "2017074862775554136": [("SPCX", "neutral", 0.5, "SpaceX 提供轨道位置感知服务，SPCX 品牌利好")],
    "2018483071046054074": [("SPCX", "buy", 0.6, "SpaceX&xAI 合并为一公司，SPCX 商业版图整合强利好")],

    # ── 2026-02 ──
    "2020559688236945573": [("SPCX", "neutral", 0.5, "Starship Super Heavy 基础设施，SPCX 技术里程碑")],
    "2020964809999777996": [("SPCX", "neutral", 0.48, "SpaceX 建月球旅行系统，SPCX 愿景利好")],
    "2021663314716373227": [("SPCX", "buy", 0.5, "辩护 SpaceX 政府资金仅占合计价值 1%，回应质疑 SPCX 利好"), ("TSLA", "buy", 0.5, "同时辩护 Tesla 政府资金，TSLA 利好")],
    "2021673886157607383": [("SPCX", "neutral", 0.45, "xAI 重组提升执行速度，xAI 属 SpaceX 组织利好 SPCX")],
    "2022693118978724277": [("SPCX", "neutral", 0.42, "招聘 xAI，组织扩张弱传导 SPCX")],
    "2023158948501594300": [("SPCX", "neutral", 0.5, "称净财富主要来自 Tesla/SpaceX 股权，SpaceX → SPCX"), ("TSLA", "neutral", 0.45, "Tesla 股权财富集中传导 TSLA")],
    "2023880206721970544": [("SPCX", "neutral", 0.4, "Grok 4.20 评价，Grok 属 SpaceX SPCX 弱传导")],
    "2024799518181700017": [("SPCX", "neutral", 0.42, "Grok 目标陈述（truth-seeking 等），SPCX 战略传导")],

    # ── 2026-03 ──
    "2028239958977511615": [("TSLA", "buy", 0.55, "Tesla AI4 算力仅 H100 1/4 却能理解驾驶复杂性，效率利好 TSLA")],
    "2028261823678759335": [("SPCX", "neutral", 0.45, "Starlink 武器系统 TOS 限制，Starlink 属 SpaceX SPCX 合规声明")],
    "2029828010808152526": [("SPCX", "neutral", 0.38, "让 Grok 做 vulgar roast，Grok 属 SpaceX SPCX 社交互动")],
    "2030159267689632121": [("SPCX", "neutral", 0.42, "'Only Grok speaks the truth'品牌宣传 SPCX 弱传导")],
    "2031751255060885911": [("SPCX", "buy", 0.55, "Macrohard/Digital Optimus 为 xAI-SpaceX 项目，Grok 导航 SPCX 利好"), ("TSLA", "buy", 0.55, "xAI-Tesla JV 协同传导 TSLA")],
    "2032344783126217196": [("SPCX", "neutral", 0.38, "Made with Grok Imagine，Grok 属 SpaceX SPCX 产品使用")],
    "2032816322929897506": [("SPCX", "buy", 0.5, "xAI 将今年追平并 3 年远超，xAI 属 SpaceX SPCX 战略利好"), ("TSLA", "neutral", 0.45, "xAI-Tesla AI 战略一体化传导")],
    "2034362846184886525": [("SPCX", "neutral", 0.4, "Grok 每周变好，Grok 属 SpaceX SPCX 产品迭代")],
    "2034439451611680818": [("TSLA", "buy", 0.58, "AI5 将 punch above weight，Tesla AI 软件栈利好 TSLA")],
    "2034526226703077652": [("SPCX", "neutral", 0.5, "称 Google 赢地球 AI、SpaceX 赢太空，SPCX 定位陈述")],
    "2034546076318122165": [("SPCX", "neutral", 0.4, "Grok Imagine Chibi 模板，Grok 属 SpaceX SPCX")],
    "2035259500064907571": [("TSLA", "buy", 0.5, "Optimus+PV 将成冯诺依曼探测器，Optimus 为 Tesla 产品 TSLA")],
    "2035506574182199757": [("SPCX", "buy", 0.65, "正式宣布 TERAFAB 项目 SpaceX+Tesla 联合万亿瓦算力，SPCX 强利好"), ("TSLA", "buy", 0.6, "TERAFAB 为 SpaceX+Tesla JV，TSLA 强利好")],
    "2035526376468394305": [("SPCX", "buy", 0.65, "SpaceXAI+Tesla TERAFAB 万亿瓦算力须上太空，SPCX 强战略利好"), ("TSLA", "buy", 0.55, "Tesla 参与 TERAFAB 传导利好 TSLA")],
    "2036665153778000143": [("TSLA", "neutral", 0.42, "发 Optimus 图，Tesla 产品展示弱传导 TSLA")],
    "2038397888884355410": [("SPCX", "neutral", 0.42, "Grok 多语言理解+内容推荐，Grok 属 SpaceX SPCX 生态粘性")],
    "2039202381683110191": [("TSLA", "neutral", 0.48, "Model S&X 定制单结束，Tesla 产品线调整中性偏谨慎 TSLA")],

    # ── 2026-04 ──
    "2041754402239975479": [("SPCX", "buy", 0.55, "SpaceXAI Colossus 2 有 7 个模型在训练，SPCX 算力扩张利好")],
    "2044250132296986737": [("SPCX", "neutral", 0.48, "Starship static fire 成功，SPCX 技术里程碑")],
    "2044315118583066738": [("TSLA", "buy", 0.6, "Tesla AI5 芯片 tape out，AI6/Dojo3 路线图推进，TSLA 强技术利好")],
    "2044961915554910455": [("SPCX", "neutral", 0.4, "xAI beta 评价，xAI 属 SpaceX SPCX 产品迭代")],
    "2044963895216095319": [("TSLA", "neutral", 0.38, "表情回应 Tesla，无实质信号 TSLA")],
    "2045271616146334038": [("SPCX", "neutral", 0.4, "xAI 追赶进度，xAI 属 SpaceX SPCX 组织陈述")],
    "2045285099680252417": [("SPCX", "neutral", 0.42, "Grok 4.3 早期 beta，Grok 属 SpaceX SPCX 产品迭代")],
    "2045292691248840918": [("SPCX", "neutral", 0.38, "Grok groks，Grok 属 SpaceX SPCX 社交互动")],
    "2045293644693770630": [("SPCX", "neutral", 0.45, "0.5T 训练 checkpoint 1T 模型 5 天后完成，xAI 算力传导 SPCX")],
    "2045293976287141993": [("SPCX", "neutral", 0.38, "Grok groks，Grok 属 SpaceX SPCX 社交互动")],
    "2045309037848272993": [("TSLA", "buy", 0.58, "Tesla 从物理第一性原理重设计锂精炼，降本利好 TSLA")],
    "2045328655140680076": [("SPCX", "neutral", 0.42, "澄清 SpaceX/Tesla 是 TSMC 客户非竞争者，SPCX context"), ("TSLA", "neutral", 0.42, "Tesla 也是 TSMC 客户，TSLA context"), ("TSM", "neutral", 0.4, "TSMC 作为 SpaceX/Tesla 芯片供应商，供应链语境")],
    "2045374796205039659": [("TSLA", "neutral", 0.4, "Robotaxi 'harder than it looks'承认难度 TSLA")],
    "2045572944420901265": [("TSLA", "buy", 0.6, "Tesla Robotaxi 在 Dallas&Houston 上线试运营，TSLA 里程碑利好")],
    "2045577407571374193": [("SPCX", "neutral", 0.42, "Grok 图像理解改进中，Grok 属 SpaceX SPCX 产品迭代")],
    "2045590599206875216": [("SPCX", "neutral", 0.45, "Grok 4.4 将两倍大小(1T)，Grok 属 SpaceX SPCX 算力扩张")],
    "2045764979882938640": [("SPCX", "neutral", 0.42, "Grok 5 预告，Grok 属 SpaceX SPCX 产品路线图")],
    "2046013308051009791": [("TSLA", "neutral", 0.48, "FSD 中国待批，上海产能为限制因素，TSLA 中性偏观望")],
    "2046110741430981016": [("SPCX", "neutral", 0.42, "0.5T Grok 训练数据少 1T 即将发布，Grok 属 SpaceX SPCX")],
    "2046123487589507120": [("SPCX", "neutral", 0.38, "Grok 表情回应，Grok 属 SpaceX SPCX 社交互动")],
    "2046129320549331352": [("SPCX", "neutral", 0.4, "努力让 Grok 在 X 外更有用，Grok 属 SpaceX SPCX 产品战略")],
    "2046224802315137391": [("SPCX", "neutral", 0.38, "Grok 表情互动，Grok 属 SpaceX SPCX 社交")],
    "2046225338397528566": [("SPCX", "neutral", 0.38, "Grok Imagine，Grok 属 SpaceX SPCX 产品使用")],
    "2046310627002679570": [("SPCX", "neutral", 0.4, "Grok analysis，Grok 属 SpaceX SPCX 产品使用")],
    "2046404769040810159": [("BTC", "neutral", 0.4, "DOGE 止欺诈提及，加密语境但非 Tesla 传导")],
    "2046405057332097524": [("SPCX", "neutral", 0.38, "Grok 社交互动，Grok 属 SpaceX SPCX")],
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

    # consensus（全窗口）
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
            "reasoning": f"{date} elonmusk 对 {ticker} buy {buy}/sell {sell}/hold {hold}/neutral {counts['neutral']}，判定 {sig}。SPCX=SpaceX/xAI/Grok 直接映射；TSLA=Optimus/FSD/Robotaxi/AI5 + 财富传导；TSM=供应链；BTC=加密语境。仅供参考，非投资建议。",
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
            "ai_summary": f"{ticker} 被提及 {mc} 次（buy {buys[ticker]}/sell {sells[ticker]}/hold {holds[ticker]}）。v5.1：SpaceX/xAI/Grok/Starlink → SPCX 直接映射（SpaceX 2026-06-12 IPO）；Optimus/FSD/Robotaxi/AI5 → TSLA；TSMC → TSM；DOGE → BTC。仅供参考，非投资建议。",
        })

    now = datetime.now(timezone.utc)
    run_id = now.strftime("%Y%m%dT%H%M%SZ") + "_ai_elonmusk"
    last_post = POSTS[-1]

    payload = {
        "run_id": run_id, "account": "elonmusk",
        "window_start": POSTS[0]["created_at"], "window_end": last_post["created_at"],
        "post_count": len(POSTS), "signal_count": len(signals),
        "consensus_count": len(consensus), "top_ticker_count": len(top),
        "model": "glm-5.2", "prompt_version": "openclaw-v5", "status": "partial",
        "summary": (
            f"本批 v5.1 规则处理 {len(POSTS)} 帖（断点 NULL→{last_post['post_id']}）。"
            f"v5.1 关键修正：SpaceX 已于 2026-06-12 在 NASDAQ IPO（代码 SPCX），xAI 已并入 SpaceX。"
            f"SpaceX/Starlink/xAI/Grok/Starship 提及 → SPCX 直接映射（类型 B）；"
            f"Optimus/Neuralink 仍走 Type C → TSLA；TSMC → TSM；DOGE → BTC。"
            f"生成 {len(signals)} 条 signals："
            f"SPCX {mention.get('SPCX',0)}（buy {buys.get('SPCX',0)}）、"
            f"TSLA {mention.get('TSLA',0)}（buy {buys.get('TSLA',0)}）、"
            f"TSM {mention.get('TSM',0)}、BTC {mention.get('BTC',0)}。"
            f"v5 仅 70 条全 TSLA，v4 仅 24 条全 TSLA。SpaceX 终于独立可见。"
            f"仍有 {BATCH['remaining_estimate']} 帖未处理，下次从 checkpoint 继续。仅供参考，非投资建议。"
        ),
        "analyzed_at": now.strftime("%Y-%m-%d %H:%M:%S.%f"),
        "resume_from_post_id": RESUME_FROM_POST_ID, "resume_from_created_at": RESUME_FROM_CREATED_AT,
        "checkpoint_post_id": last_post["post_id"], "checkpoint_post_created_at": last_post["created_at"],
        "signals": signals, "consensus": consensus, "top_tickers": top,
    }
    json.dump(payload, open("/tmp/stock-ai/elon_run_v5.json", "w"), ensure_ascii=False, indent=1)
    print(f"signals={len(signals)} consensus={len(consensus)} top={len(top)} status=partial checkpoint={last_post['post_id']}")
    for t in ["SPCX", "TSLA", "TSM", "BTC"]:
        print(f"  {t}: mentions={mention.get(t,0)} buy={buys.get(t,0)}")


if __name__ == "__main__":
    main()
