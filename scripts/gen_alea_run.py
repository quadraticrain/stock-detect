#!/usr/bin/env python3
"""生成 aleabitoreddit 账号本批 run JSON（AI 语义判断，openclaw-v4）。

本文件承载 AI 对 307 条含 ticker 推文的语义分析结果（recommendation/confidence/
reasoning），与 ai_analysis_helper.py write-run 配合写入四表。判断由 AI 阅读原文后
给出，非关键词词表。
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone

BATCH = json.load(open("/tmp/stock-ai/aleabitoreddit.json"))
POSTS = BATCH["posts"]
BY_ID = {p["post_id"]: p for p in POSTS}
RESUME_FROM_POST_ID = BATCH["resume_from_post_id"]
RESUME_FROM_CREATED_AT = BATCH["resume_from_created_at"]

# 每条: post_id -> [(ticker, rec, conf, reasoning), ...]
# rec: buy|hold|sell|neutral
JUDGEMENTS: dict[str, list[tuple[str, str, float, str]]] = {
    "1966512870251749588": [("HIMS", "buy", 0.72, "42%空头利率+110亿市值盈利高增长，暗示轧空潜力"), ("GME", "neutral", 0.4, "仅作轧空类比提及"), ("OPEN", "neutral", 0.4, "仅上下文提及")],
    "1968015339666682082": [("OPEN", "sell", 0.6, "称跟随MartinShkreli做OPEN是'dumbest idea'"), ("QBTS", "neutral", 0.4, "附带提及")],
    "1969115361736896720": [("NBIS", "buy", 0.9, "自述买入50万美元，'highest conviction'，目标价225")],
    "1969151544320016527": [("NBIS", "buy", 0.88, "加仓至100万+，MSFT/GOOGL为客户，目标价225"), ("NVDA", "neutral", 0.4, "作行业对比提及")],
    "1970165804311388542": [("NBIS", "buy", 0.85, "'screaming buy on every dip'，'once-in-a-decade'")],
    "1970496881349546218": [("NBIS", "buy", 0.85, "'once-a-decade'，'mispriced'，'screaming buy under $130'")],
    "1970880728994107816": [("NBIS", "buy", 0.8, "持仓75万+，5天浮盈9.3万，'extremely undervalued'")],
    "1970908938796400881": [("NBIS", "buy", 0.7, "展示1年630%回报，NBIS为核心持仓"), ("HOOD", "neutral", 0.45, "历史持仓提及"), ("UPWK", "neutral", 0.45, "历史持仓提及")],
    "1970933043855872074": [("BKKT", "neutral", 0.35, "提及但主题是批评其他账号封锁回复")],
    "1970995733659779574": [("NBIS", "buy", 0.72, "建议组合权重30%为最高"), ("RKLB", "neutral", 0.45, "组合4%配置"), ("IREN", "neutral", 0.45, "组合配置提及")],
    "1971270859898880420": [("NBIS", "neutral", 0.5, "批评付费课程，提及但无明确信号"), ("IREN", "neutral", 0.5, "附带提及"), ("BMNR", "neutral", 0.5, "附带提及")],
    "1971599988204634554": [("CIFR", "buy", 0.7, "加仓CIFR 1月看涨期权"), ("NBIS", "buy", 0.72, "加仓10万NBIS看涨期权"), ("IREN", "neutral", 0.45, "附带提及")],
    "1971677620623540346": [("HOOD", "sell", 0.62, "明确'NEVER USE $HOOD'用于大账户")],
    "1972016308662513748": [("NBIS", "buy", 0.82, "Neocloud核心，1.5M+投入，200-300%+回报"), ("CRWV", "buy", 0.78, "Mag7合同标的，核心标的"), ("CIFR", "neutral", 0.5, "Neocloud bucket提及"), ("IREN", "neutral", 0.5, "Neocloud bucket提及"), ("WULF", "neutral", 0.5, "Neocloud bucket提及"), ("WYFI", "neutral", 0.5, "Neocloud bucket提及"), ("BITF", "neutral", 0.5, "附带提及"), ("SLNH", "neutral", 0.5, "附带提及"), ("GRRR", "neutral", 0.5, "附带提及")],
    "1972055327370809666": [("PLTR", "neutral", 0.45, "称对方观点'hilariously wrong'但agree to disagree"), ("DUOL", "neutral", 0.45, "同上")],
    "1972367879858470974": [("NBIS", "buy", 0.6, "期权策略核心持仓示例"), ("CIFR", "neutral", 0.45, "策略示例提及"), ("HIMS", "neutral", 0.45, "策略示例提及")],
    "1972677721290682505": [("VIRT", "buy", 0.62, "'interesting stock'作非对称波动对冲"), ("IREN", "neutral", 0.45, "附带提及"), ("NBIS", "neutral", 0.45, "附带提及")],
    "1972769926302855553": [("NBIS", "buy", 0.85, "'Extremely Strong Buy'"), ("ETOR", "buy", 0.8, "'Extremely Strong Buy'"), ("LTC", "buy", 0.8, "'Extremely Strong Buy'"), ("VIRT", "buy", 0.8, "'Extremely Strong Buy'"), ("AMZN", "buy", 0.72, "'Buy'"), ("SMCI", "buy", 0.72, "'Buy'"), ("TGT", "buy", 0.72, "'Buy'"), ("CRM", "buy", 0.72, "'Buy'"), ("TSM", "buy", 0.72, "'Buy'"), ("CRDO", "buy", 0.72, "'Buy'"), ("SG", "buy", 0.72, "'Buy'"), ("CIFR", "buy", 0.72, "'Buy'"), ("LULU", "buy", 0.72, "'Buy'"), ("SLNH", "buy", 0.72, "'Buy'"), ("ORCL", "buy", 0.72, "'Buy'"), ("MSTR", "buy", 0.72, "'Buy'"), ("RIOT", "buy", 0.72, "'Buy'"), ("MARA", "buy", 0.72, "'Buy'"), ("IREN", "hold", 0.6, "'Hold'")],
    "1972919111987671265": [("NBIS", "buy", 0.6, "作为最高信念标的被点名"), ("RR", "neutral", 0.45, "众包讨论提及")],
    "1973102864701726752": [("NBIS", "neutral", 0.5, "批评'be patient'心态，强调方法论，提及非信号")],
    "1973188544186425368": [("VIRT", "neutral", 0.5, "宏观交易思路提及"), ("VIX", "neutral", 0.5, "波动率对冲提及")],
    "1973458076994007226": [("NBIS", "buy", 0.62, "图表模式推理看好"), ("CIFR", "neutral", 0.45, "同行业提及")],
    "1973533335147389092": [("RKLB", "buy", 0.65, "波段交易教学示例，看好走势")],
    "1973693781888417816": [("NBIS", "buy", 0.78, "MSFT 17B合同+META 14B，'billions to trillions'涌入Neocloud")],
    "1973799361332326443": [("NBIS", "buy", 0.8, "对比HOOD 1000%+涨幅，认为NBIS更具潜力"), ("HOOD", "neutral", 0.5, "历史涨幅对比提及")],
    "1974167533226955118": [("NBIS", "buy", 0.62, "期权卖出策略核心标的"), ("CIFR", "neutral", 0.45, "策略提及"), ("AMZN", "neutral", 0.45, "策略提及"), ("HIMS", "neutral", 0.45, "策略提及"), ("RKLB", "neutral", 0.45, "策略提及"), ("TGT", "neutral", 0.45, "策略提及")],
    "1974283913905517009": [("RDDT", "buy", 0.8, "'Strong Buy'"), ("SNAP", "buy", 0.8, "'Strong Buy'"), ("AMZN", "buy", 0.8, "'Strong Buy'"), ("ETOR", "buy", 0.8, "'Strong Buy'"), ("NBIS", "buy", 0.8, "'Strong Buy'"), ("LTC", "buy", 0.8, "'Strong Buy'"), ("UPWK", "buy", 0.72, "'Buy'"), ("MSTR", "buy", 0.72, "'Buy'"), ("ORCL", "buy", 0.72, "'Buy'"), ("TGT", "buy", 0.72, "'Buy'"), ("CIFR", "buy", 0.72, "'Buy'"), ("VIRT", "buy", 0.72, "'Buy'"), ("CRDO", "buy", 0.72, "'Buy'"), ("WULF", "buy", 0.72, "'Buy'"), ("SOFI", "buy", 0.72, "'Buy'"), ("META", "buy", 0.72, "'Buy'"), ("HOOD", "buy", 0.72, "'Buy'"), ("IREN", "hold", 0.55, "Hold段提及")],
    "1974570974361358400": [("RGTI", "sell", 0.6, "称对方名单'terrible'，不认同RGTI等选择"), ("OKLO", "sell", 0.6, "同上'terrible list'"), ("JOBY", "sell", 0.6, "同上"), ("OPEN", "sell", 0.6, "同上"), ("IONQ", "sell", 0.6, "同上")],
    "1974576290125795760": [("JOBY", "neutral", 0.5, "批评付费课程，提及非信号"), ("OPEN", "neutral", 0.5, "同上"), ("RGTI", "neutral", 0.5, "同上")],
    "1974734053070053566": [("OKLO", "neutral", 0.55, "讨论ATH泡沫风险，半开玩笑择时"), ("RGTI", "neutral", 0.55, "同上")],
    "1975027478373748808": [("NBIS", "buy", 0.6, "备兑看涨期权被动复利教学核心标的")],
    "1975155632811507945": [("AMD", "buy", 0.72, "OpenAI百亿级合同+叙事变化，预期重估")],
    "1975205333254447126": [("SNAP", "buy", 0.7, "'flipped from Sell to Buy'，最大支出转为收入"), ("META", "neutral", 0.5, "对比提及"), ("RDDT", "neutral", 0.5, "对比提及")],
    "1975294794370064468": [("SPRB", "buy", 0.6, "研究TA-ERT突破性酶疗法，若获批有潜力")],
    "1975327662903337144": [("NBIS", "buy", 0.75, "'extremely good dip buy'，回调买入"), ("CIFR", "neutral", 0.5, "Neocloud持稳提及"), ("IREN", "neutral", 0.5, "同上")],
    "1975334113726079397": [("SPRB", "buy", 0.65, "2小时+3.7万盈利，已获利了结大部分")],
    "1975612208286736451": [("ORCL", "neutral", 0.55, "ORCL GPUaaS遇困对Neocloud利好，ORCL本身中性"), ("NBIS", "buy", 0.7, "利好Nebius"), ("CIFR", "neutral", 0.5, "Neocloud提及"), ("CRWV", "neutral", 0.5, "Neocloud提及"), ("IREN", "neutral", 0.5, "Neocloud提及"), ("WYFI", "neutral", 0.5, "Neocloud提及")],
    "1975823367258394863": [("IREN", "buy", 0.6, "大额回报后讨论税务结构，暗示持仓盈利"), ("AMD", "buy", 0.6, "同上")],
    "1976001305866080372": [("WLAC", "buy", 0.65, "Boost SPAC Neocloud IPO前置套利，3个月耐心"), ("GOOGL", "neutral", 0.5, "可能backstop提及"), ("CIFR", "neutral", 0.5, "附带提及")],
    "1976033094932234314": [("AMD", "buy", 0.6, "ETF成分+10%重估"), ("WLAC", "buy", 0.6, "ETF成分"), ("FLNC", "neutral", 0.5, "ETF成分提及"), ("MU", "neutral", 0.5, "ETF成分提及"), ("FLY", "buy", 0.6, "ETF新增+3%"), ("SEI", "neutral", 0.5, "ETF成分提及"), ("DFLI", "neutral", 0.5, "ETF成分提及")],
    "1976057641999925300": [("FLY", "buy", 0.7, "Eclipse可复用火箭2026首射，45亿市值'mega moat'"), ("RKLB", "neutral", 0.5, "同行业对比提及")],
    "1976370622633755115": [("NBIS", "buy", 0.85, "'next Microsoft'，季度收入1亿→20-30亿，55-75%毛利")],
    "1976484532326105414": [("WWR", "buy", 0.6, "中国稀土出口限制触发买入"), ("DFLI", "buy", 0.6, "同上主题")],
    "1976662977106596031": [("FLY", "buy", 0.72, "详细阐述Firefly火箭论点，可复用中运力"), ("RKLB", "neutral", 0.5, "对比提及")],
    "1976771236215808119": [("IREN", "neutral", 0.5, "市场大跌背景提及，非明确信号")],
    "1977079938835718513": [("IBIT", "buy", 0.8, "'Strong Buy'"), ("LTC", "buy", 0.8, "'Strong Buy'"), ("WLAC", "buy", 0.8, "'Strong Buy'"), ("NBIS", "buy", 0.8, "'Strong Buy'"), ("MP", "buy", 0.8, "'Strong Buy'"), ("TSM", "buy", 0.8, "'Strong Buy'(明年)"), ("ETOR", "buy", 0.8, "'Strong Buy'"), ("DKNG", "buy", 0.8, "'Strong Buy'"), ("SNAP", "buy", 0.8, "'Strong Buy'"), ("UPWK", "buy", 0.72, "'Buy'"), ("CRDO", "buy", 0.72, "'Buy'"), ("ALAB", "buy", 0.72, "'Buy'"), ("HOOD", "buy", 0.72, "'Buy'"), ("IREN", "neutral", 0.5, "附带提及"), ("RKLB", "neutral", 0.5, "附带提及"), ("FLY", "neutral", 0.5, "附带提及"), ("AMZN", "neutral", 0.5, "附带提及"), ("WULF", "neutral", 0.5, "附带提及")],
    "1977495210063286491": [("HOOD", "buy", 0.7, "6大最高信念多头之一"), ("RKLB", "buy", 0.7, "6大最高信念多头之一"), ("TSM", "buy", 0.7, "6大最高信念多头之一"), ("BTC", "buy", 0.7, "6大最高信念多头之一"), ("NBIS", "buy", 0.78, "最高信念多头")],
    "1977812041969926614": [("NBIS", "buy", 0.85, "1年目标价上调至450，重申买入"), ("CIFR", "neutral", 0.5, "Neocloud提及"), ("IREN", "neutral", 0.5, "Neocloud提及"), ("WLAC", "neutral", 0.5, "Neocloud提及"), ("WULF", "neutral", 0.5, "Neocloud提及"), ("WYFI", "neutral", 0.5, "Neocloud提及"), ("TSM", "neutral", 0.5, "提及"), ("AMD", "neutral", 0.5, "提及"), ("BITF", "neutral", 0.5, "提及"), ("FLNC", "neutral", 0.5, "提及")],
    "1978183356777922651": [("NBIS", "buy", 0.82, "Neocloud Deck核心'Head'"), ("WLAC", "buy", 0.7, "Deck'Left Arm'"), ("IREN", "buy", 0.7, "Deck'Right Arm'"), ("CIFR", "buy", 0.7, "Deck'Left Leg'"), ("WULF", "buy", 0.7, "Deck'Right Leg'"), ("TSM", "neutral", 0.5, "提及"), ("GLXY", "neutral", 0.5, "提及"), ("FLNC", "neutral", 0.5, "提及")],
    "1978247373089358249": [("NBIS", "buy", 0.8, "'AI是最大国安竞赛'，NBIS为新基础设施")],
    "1978365814941384882": [("ALAB", "buy", 0.75, "'Strong Buy'"), ("CRDO", "buy", 0.75, "'Strong Buy'"), ("NBIS", "buy", 0.75, "'Strong Buy'"), ("WLAC", "buy", 0.75, "'Strong Buy'"), ("LTC", "buy", 0.75, "'Strong Buy'"), ("TSM", "buy", 0.75, "'Strong Buy'"), ("BTC", "buy", 0.75, "'Strong Buy'"), ("AMZN", "buy", 0.7, "'Buy'"), ("SMCI", "buy", 0.7, "'Buy'"), ("CIFR", "buy", 0.7, "'Buy'"), ("CRWV", "buy", 0.7, "'Buy'"), ("WULF", "buy", 0.7, "'Buy'"), ("IREN", "neutral", 0.5, "提及"), ("BITF", "neutral", 0.5, "提及"), ("BZAI", "neutral", 0.5, "提及"), ("FLNC", "neutral", 0.5, "提及"), ("GLXY", "neutral", 0.5, "提及"), ("GRAB", "neutral", 0.5, "提及"), ("NKLR", "neutral", 0.5, "提及"), ("RBRK", "neutral", 0.5, "提及"), ("SEA", "neutral", 0.5, "提及"), ("SEI", "neutral", 0.5, "提及"), ("SLNH", "neutral", 0.5, "提及")],
    "1978511244710617534": [("NBIS", "buy", 0.68, "'No news dips are a nice gift'，回调加仓看涨期权")],
    "1978955578652398061": [("GLD", "neutral", 0.55, "黄金ATH宏观讨论，非明确信号")],
    "1979087229038530782": [("NBIS", "buy", 0.65, "降息前关注加仓位置"), ("ALAB", "neutral", 0.5, "提及"), ("BTC", "neutral", 0.5, "提及"), ("RKLB", "neutral", 0.5, "提及"), ("TSM", "neutral", 0.5, "提及")],
    "1979201376115921139": [("NBIS", "buy", 0.8, "'Fire sale'，加仓30万看涨期权，10%回调=买入机会")],
    "1979346235606863918": [("NBIS", "neutral", 0.4, "X变现数据帖，非股票信号")],
    "1979685872800010548": [("ETOR", "neutral", 0.5, "复盘亏损持仓与教训，-19.58%"), ("VIRT", "neutral", 0.5, "亏损持仓复盘"), ("GRRR", "neutral", 0.5, "亏损持仓复盘"), ("SG", "neutral", 0.5, "亏损持仓复盘"), ("SNAP", "neutral", 0.5, "亏损持仓复盘")],
    "1979976235825635419": [("NBIS", "buy", 0.75, "'Fire Sale'"), ("ALAB", "buy", 0.7, "评级提及"), ("AMZN", "buy", 0.7, "评级提及"), ("CRDO", "buy", 0.7, "评级提及"), ("FLY", "buy", 0.7, "评级提及"), ("HIMS", "buy", 0.7, "评级提及"), ("IBIT", "buy", 0.7, "评级提及"), ("LTC", "buy", 0.7, "评级提及"), ("RDDT", "buy", 0.7, "评级提及"), ("SMCI", "buy", 0.7, "评级提及"), ("SNAP", "buy", 0.7, "评级提及"), ("TSM", "buy", 0.7, "评级提及"), ("WLAC", "buy", 0.7, "评级提及"), ("AMKR", "neutral", 0.5, "附带提及")],
    "1980287888077312390": [("TE", "buy", 0.65, "建仓T1 Energy，5万股+4月看涨期权"), ("FLNC", "neutral", 0.5, "能源持仓提及"), ("EOSE", "neutral", 0.5, "附带提及")],
    "1980413318973333927": [("NBIS", "buy", 0.78, "-17%回调无基本面变化，目标价400"), ("ASTS", "neutral", 0.5, "历史类比提及"), ("GOOGL", "neutral", 0.5, "附带提及"), ("HOOD", "neutral", 0.5, "附带提及")],
    "1980786077003833508": [("NBIS", "buy", 0.75, "机构吸纳零售恐慌筹码，机构持仓38%"), ("HOOD", "neutral", 0.5, "附带提及")],
    "1981009544546591207": [("NBIS", "buy", 0.82, "加仓20万看涨期权，'time to buy'，机构布局")],
    "1981201004931739734": [("NBIS", "buy", 0.7, "国安AI标的"), ("RKLB", "buy", 0.65, "国安Space标的"), ("TE", "buy", 0.65, "国安Energy标的"), ("RGTI", "neutral", 0.5, "Quantum国安提及"), ("IONQ", "neutral", 0.5, "Quantum国安提及"), ("MP", "neutral", 0.5, "提及"), ("QBTS", "neutral", 0.5, "提及")],
    "1981351114655346809": [("NBIS", "buy", 0.82, "1年目标400/1000亿市值，详细估值推演")],
    "1981759104831115698": [("NBIS", "buy", 0.78, "零售恐慌送至94，强调基本面未变")],
    "1981904072761565532": [("CRCL", "sell", 0.65, "'Huge warning'，低流通+IPO解禁风险")],
    "1981981029029298374": [("NBIS", "buy", 0.8, "'$NBIS is superior'，卖出其他Neocloud集中到NBIS"), ("IREN", "sell", 0.6, "卖出该Neocloud"), ("CIFR", "sell", 0.6, "卖出该Neocloud"), ("BITF", "sell", 0.6, "卖出该Neocloud"), ("WULF", "sell", 0.6, "卖出该Neocloud"), ("WYFI", "sell", 0.6, "卖出该Neocloud")],
    "1982428584431251483": [("NBIS", "buy", 0.8, "重申NBIS优于IREN等，整合持仓"), ("IREN", "sell", 0.6, "被整合卖出"), ("CIFR", "neutral", 0.5, "辩论提及"), ("CRWV", "neutral", 0.5, "辩论提及"), ("ORCL", "neutral", 0.5, "报告引用提及")],
    "1982931539836187074": [("CRWV", "buy", 0.65, "Neocloud论点兑现+12.7%"), ("NBIS", "buy", 0.65, "+17.5%"), ("WULF", "buy", 0.65, "+28.8%"), ("IREN", "buy", 0.65, "+55.2%"), ("CIFR", "neutral", 0.5, "提及"), ("BITF", "neutral", 0.5, "提及"), ("WYFI", "neutral", 0.5, "提及"), ("GRRR", "neutral", 0.5, "提及")],
    "1983030739332673923": [("CIFR", "sell", 0.62, "卖出CIFR等矿工转向全栈Neocloud"), ("IREN", "sell", 0.62, "同上"), ("WYFI", "sell", 0.62, "同上"), ("WULF", "sell", 0.62, "同上"), ("NBIS", "buy", 0.7, "全栈Neocloud更优"), ("CRWV", "neutral", 0.5, "提及")],
    "1983399179759300943": [("NBIS", "buy", 0.65, "Neocloud核心标的宏观分析"), ("IREN", "neutral", 0.5, "提及"), ("CIFR", "neutral", 0.5, "提及"), ("ALAB", "buy", 0.6, "Connectivity"), ("CRDO", "buy", 0.6, "Connectivity"), ("CLS", "neutral", 0.5, "提及"), ("RKLB", "buy", 0.6, "Robotics/Space"), ("RR", "neutral", 0.5, "提及"), ("TE", "neutral", 0.5, "提及"), ("MP", "neutral", 0.5, "提及"), ("FLNC", "neutral", 0.5, "提及"), ("EOSE", "neutral", 0.5, "提及"), ("ONDS", "neutral", 0.5, "提及"), ("KTOS", "neutral", 0.5, "提及"), ("DGXX", "neutral", 0.5, "提及"), ("CCCX", "neutral", 0.5, "提及"), ("SEI", "neutral", 0.5, "提及")],
    "1983791002436694520": [("TSLA", "neutral", 0.5, "软体机器人主题提及"), ("AXTI", "buy", 0.6, "InP瓶颈标的提及"), ("LITE", "buy", 0.6, "SiPh提及"), ("GOOGL", "neutral", 0.5, "提及"), ("NVDA", "neutral", 0.5, "提及"), ("INTC", "neutral", 0.5, "提及"), ("TSM", "neutral", 0.5, "提及"), ("IREN", "neutral", 0.5, "提及"), ("NBIS", "neutral", 0.5, "提及"), ("CRWD", "neutral", 0.5, "提及"), ("CSCO", "neutral", 0.5, "提及"), ("MSFT", "neutral", 0.5, "提及"), ("RKLB", "neutral", 0.5, "提及"), ("ASTS", "neutral", 0.5, "提及"), ("PATH", "neutral", 0.5, "提及"), ("AMZN", "neutral", 0.5, "提及"), ("AMD", "neutral", 0.5, "提及"), ("POET", "neutral", 0.5, "提及"), ("AVGO", "neutral", 0.5, "提及"), ("XRP", "neutral", 0.5, "提及"), ("PYPL", "neutral", 0.5, "提及"), ("HOOD", "neutral", 0.5, "提及"), ("SOFI", "neutral", 0.5, "提及"), ("ASOZF", "neutral", 0.5, "提及"), ("AKAM", "neutral", 0.5, "提及"), ("ALAB", "neutral", 0.5, "提及"), ("CRDO", "neutral", 0.5, "提及"), ("CRCL", "neutral", 0.5, "提及"), ("ONDS", "neutral", 0.5, "提及"), ("HUT", "neutral", 0.5, "提及"), ("BOA", "neutral", 0.4, "提及"), ("V", "neutral", 0.5, "提及")],
    "1983895786590200266": [("META", "buy", 0.72, "加仓6位数1-2月看涨期权，基本面完好")],
    "1984293587295866986": [("NBIS", "buy", 0.7, "全栈Neocloud与矿工分化，利好NBIS"), ("CIFR", "neutral", 0.5, "矿工提及"), ("BITF", "neutral", 0.5, "矿工提及"), ("CLSK", "neutral", 0.5, "矿工提及"), ("IREN", "neutral", 0.5, "矿工提及"), ("WULF", "neutral", 0.5, "矿工提及")],
    "1984599773094265248": [("FI", "sell", 0.6, "批评'CHEAP'贴无实质分析"), ("NVO", "neutral", 0.5, "同上批评提及")],
    "1984837960735285593": [("CRWV", "buy", 0.65, "Neocloud生态首位662亿市值"), ("NBIS", "buy", 0.7, "328亿市值核心"), ("IREN", "neutral", 0.5, "生态提及"), ("APLD", "neutral", 0.5, "生态提及"), ("CLSK", "neutral", 0.5, "生态提及"), ("CIFR", "neutral", 0.5, "生态提及"), ("HIVE", "neutral", 0.5, "生态提及"), ("HUT", "neutral", 0.5, "生态提及"), ("RIOT", "neutral", 0.5, "生态提及"), ("WULF", "neutral", 0.5, "生态提及"), ("WYFI", "neutral", 0.5, "生态提及")],
    "1985175534133993567": [("IBIT", "buy", 0.7, "11-12月非对称回报核心标的"), ("META", "buy", 0.7, "核心标的"), ("NBIS", "buy", 0.78, "核心标的")],
    "1985334909108433014": [("IREN", "buy", 0.7, "获MSFT 97亿GPU云合同+20%预付款"), ("CIFR", "neutral", 0.5, "提及")],
    "1985409592608899479": [("NBIS", "buy", 0.7, "NBIS与MSFT交易利润率优于IREN"), ("IREN", "neutral", 0.5, "对比提及"), ("MSFT", "neutral", 0.5, "客户提及")],
    "1985770241532838347": [("META", "buy", 0.8, "'Fire Sale'"), ("NBIS", "buy", 0.8, "'Fire Sale'"), ("IBIT", "buy", 0.8, "'Fire Sale'"), ("RDDT", "buy", 0.75, "'Strong Buys'"), ("RKLB", "buy", 0.75, "'Strong Buys'"), ("WLAC", "buy", 0.75, "'Strong Buys'"), ("CIFR", "buy", 0.75, "'Strong Buys'"), ("LTC", "buy", 0.75, "'Strong Buys'"), ("SOL", "buy", 0.75, "'Strong Buys'"), ("CORZ", "buy", 0.75, "'Strong Buys'"), ("ALAB", "neutral", 0.5, "提及"), ("AMD", "neutral", 0.5, "提及"), ("AMZN", "neutral", 0.5, "提及"), ("CRDO", "neutral", 0.5, "提及"), ("DELL", "neutral", 0.5, "提及"), ("FLNC", "neutral", 0.5, "提及"), ("MU", "neutral", 0.5, "提及"), ("SMCI", "neutral", 0.5, "提及"), ("TE", "neutral", 0.5, "提及"), ("TSM", "neutral", 0.5, "提及")],
    "1985989016219508993": [("KRKNF", "neutral", 0.55, "发布投机研究，无持仓计划"), ("OSS", "neutral", 0.55, "同上投机研究")],
    "1986483611202400672": [("NBIS", "buy", 0.7, "忽略噪音持有Neocloud赢家"), ("IREN", "neutral", 0.55, "持有提及"), ("CIFR", "neutral", 0.55, "持有提及"), ("META", "neutral", 0.5, "提及"), ("MSFT", "neutral", 0.5, "客户提及")],
    "1986883096692830292": [("SMCI", "neutral", 0.5, "回调-26%提及非信号"), ("RKLB", "neutral", 0.5, "回调-19.85%提及"), ("CRCL", "neutral", 0.5, "回调提及"), ("NBIS", "neutral", 0.5, "回调-19.14%提及"), ("WYFI", "neutral", 0.5, "回调提及"), ("ALAB", "neutral", 0.5, "提及"), ("AMD", "neutral", 0.5, "提及"), ("ASTS", "neutral", 0.5, "提及"), ("CRDO", "neutral", 0.5, "提及"), ("HOOD", "neutral", 0.5, "提及"), ("IREN", "neutral", 0.5, "提及")],
    "1987610303752970252": [("IREN", "neutral", 0.5, "宏观背景提及"), ("NBIS", "buy", 0.6, "连接点分析利好")],
    "1988048592754589970": [("WULF", "buy", 0.7, "ER正面，170亿TCV+520MW HPC"), ("CIFR", "neutral", 0.5, "Neocloud提及"), ("CRWV", "neutral", 0.5, "Neocloud提及")],
    "1988221135759290725": [("NBIS", "buy", 0.85, "ARR超预期+30亿META超算合同，2026 ARR 7-90亿"), ("META", "neutral", 0.5, "客户提及")],
    "1988227411054653710": [("NBIS", "buy", 0.85, "财报超预期，7-90亿ARR+30亿META合同+Cursor客户")],
    "1988237492596994341": [("NBIS", "buy", 0.85, "'Absolute Blowout Earnings'，30亿META+Cursor+170亿MSFT"), ("META", "neutral", 0.5, "客户提及"), ("MSFT", "neutral", 0.5, "客户提及")],
    "1988537251530469620": [("NBIS", "buy", 0.75, "Northland目标价205基础上推演更高PT")],
    "1988644630175547407": [("NBIS", "buy", 0.82, "240亿市值做80亿前瞻ARR，目标30% EBITDA"), ("META", "neutral", 0.5, "提及"), ("MSFT", "neutral", 0.5, "提及")],
    "1988993526517100814": [("NBIS", "buy", 0.68, "高Beta AI板块回调30-45%中提及NBIS为核心受害者"), ("IREN", "neutral", 0.5, "提及"), ("META", "neutral", 0.5, "提及"), ("GOOGL", "neutral", 0.5, "提及"), ("WULF", "neutral", 0.5, "提及")],
    "1989258180552175977": [("NBIS", "buy", 0.7, "13F机构资金强烈正面7/10"), ("WULF", "buy", 0.7, "8.5/10高度正面"), ("CIFR", "neutral", 0.5, "提及"), ("CRWV", "neutral", 0.5, "提及"), ("IREN", "sell", 0.6, "机构资金负面")],
    "1989352983348589023": [("IREN", "neutral", 0.5, "周跌37.88%提及"), ("NBIS", "neutral", 0.5, "月跌35.27%提及")],
    "2004569946492453003": [("AXTI", "buy", 0.82, "InP基板瓶颈，控制60-70%全球供应，AI产业瓶颈"), ("SMTOY", "buy", 0.72, "InP双寡头之一317亿市值"), ("AMZN", "neutral", 0.5, " hyperscaler提及"), ("GOOGL", "neutral", 0.5, "提及"), ("META", "neutral", 0.5, "提及"), ("MSFT", "neutral", 0.5, "提及"), ("NVDA", "neutral", 0.5, "提及")],
    "2004572018327572855": [("MU", "buy", 0.6, "HBM瓶颈2025体现"), ("AXTI", "buy", 0.7, "未来hyperscaler ASIC部署瓶颈"), ("COHR", "buy", 0.6, "光子学受益")],
    "2004574162283802728": [("LITE", "buy", 0.7, "持有LITE光子学标的"), ("AAOI", "buy", 0.7, "持有AAOI"), ("AXTI", "buy", 0.78, "持有AXTI，垂直整合")],
    "2004577553714163817": [("LITE", "neutral", 0.55, "讨论InP瓶颈尚未显现但将出现"), ("AXTI", "neutral", 0.55, "同上讨论")],
    "2004597823602655744": [("AXTI", "buy", 0.7, "6亿公司成为AI贸易瓶颈")],
    "2004622136837898647": [("AXTI", "buy", 0.75, "InP极端瓶颈，AXTI+SMTOY控制60%+"), ("SMTOY", "buy", 0.7, "双寡头")],
    "2004730915747217784": [("AXTI", "buy", 0.78, "令人警惕的是7亿公司AXTI扼住西方AI咽喉"), ("SMTOY", "buy", 0.7, "同上"), ("LITE", "neutral", 0.5, "提及")],
    "2004801510736068809": [("AXTI", "buy", 0.78, "向AI领袖示警InP短缺瓶颈"), ("SMTOY", "buy", 0.7, "同上")],
    "2004936335702753729": [("AXTI", "buy", 0.82, "'InP Chokepoint'，7亿小公司卡住NVDA/META/GOOGL/MSFT AI建设"), ("SMTOY", "buy", 0.72, "双寡头"), ("LITE", "buy", 0.65, "光子学受益"), ("COHR", "buy", 0.65, "光子学受益"), ("AMZN", "neutral", 0.5, "hyperscaler提及"), ("MRVL", "neutral", 0.5, "提及"), ("NVDA", "neutral", 0.5, "提及"), ("META", "neutral", 0.5, "提及"), ("GOOGL", "neutral", 0.5, "提及"), ("MSFT", "neutral", 0.5, "提及")],
    "2004952198275571862": [("LITE", "buy", 0.7, "定价权强涨幅大"), ("COHR", "buy", 0.7, "同上"), ("AXTI", "buy", 0.75, "垂直整合深入")],
    "2004957163857608734": [("AVGO", "neutral", 0.55, "Penn fab仍需InP基板"), ("AXTI", "buy", 0.7, "基板供应提及")],
    "2005048872805302692": [("AXTI", "buy", 0.72, "挑战读者指出7亿公司为AI瓶颈")],
    "2005054690573385895": [("LITE", "buy", 0.65, "赞赏相关帖子"), ("POET", "neutral", 0.5, "提及"), ("AAOI", "neutral", 0.5, "提及"), ("COHR", "neutral", 0.5, "提及"), ("MRVL", "neutral", 0.5, "提及")],
    "2005069537142866204": [("AXTI", "buy", 0.7, "7亿市值有风险但垂直整合"), ("SMTOY", "neutral", 0.55, "对比提及300亿+市值")],
    "2005081885563912607": [("AAOI", "neutral", 0.5, "光子学交易机会提及"), ("MRVL", "neutral", 0.5, "提及"), ("POET", "neutral", 0.5, "提及"), ("GOOGL", "neutral", 0.5, "提及"), ("LITE", "neutral", 0.5, "提及"), ("COHR", "neutral", 0.5, "提及"), ("AXTI", "buy", 0.65, "核心瓶颈标的")],
    "2005126729321378158": [("AXTI", "neutral", 0.55, "不主张买入，澄清误解，强调中国供应链风险"), ("MU", "neutral", 0.5, "HBM对比提及")],
    "2005317480424829202": [("AXTI", "buy", 0.65, "建模标准化InP所有权"), ("DOWA", "neutral", 0.5, "上游提及")],
    "2005485130958430440": [("AXTI", "buy", 0.82, "'Bottleneck within a Bottleneck'，AXTI|SMTOY双寡头控制60%+InP"), ("SMTOY", "buy", 0.72, "双寡头"), ("DOWA", "neutral", 0.5, "上游提及")],
    "2005514423876633005": [("COHR", "buy", 0.7, "领先美国虚拟整合公司但仍受InP瓶颈"), ("AXTI", "buy", 0.7, "瓶颈核心")],
    "2005518962445209817": [("AXTI", "buy", 0.75, "AI建设点失效研究笔记"), ("LITE", "neutral", 0.5, "提及"), ("COHR", "neutral", 0.5, "提及"), ("AVGO", "neutral", 0.5, "提及"), ("GOOGL", "neutral", 0.5, "提及"), ("MSFT", "neutral", 0.5, "提及")],
    "2005523875665444971": [("GOOGL", "neutral", 0.5, "若直接向DOWA采购提及"), ("DOWA", "neutral", 0.5, "上游提及"), ("AXTI", "buy", 0.72, "拥有全供应链+激光级InP大部分")],
    "2005532674975539513": [("AXTI", "buy", 0.8, "供应链最底层+1/3 InP基板"), ("DOWA", "neutral", 0.5, "提及"), ("AAOI", "neutral", 0.5, "提及"), ("LITE", "neutral", 0.5, "提及"), ("AMZN", "neutral", 0.5, "提及"), ("MSFT", "neutral", 0.5, "提及"), ("MRVL", "neutral", 0.5, "提及"), ("AVGO", "neutral", 0.5, "提及"), ("POET", "neutral", 0.5, "提及"), ("TPU", "neutral", 0.4, "产品提及")],
    "2005540569888780797": [("DOWA", "neutral", 0.55, "西方AI ramp讨论提及"), ("AXTI", "buy", 0.7, "瓶颈核心"), ("COHR", "neutral", 0.5, "提及")],
    "2005568879180021805": [("MSFT", "neutral", 0.5, "ASIC程序名被自动过滤，调侃提及")],
    "2005654662616387783": [("AXTI", "buy", 0.85, "CEO称占InP供应链40%，7亿公司控制万亿产业瓶颈")],
    "2005857302960841161": [("CRWV", "neutral", 0.5, "B300集群BOM讨论提及"), ("NBIS", "neutral", 0.5, "提及"), ("IREN", "neutral", 0.5, "提及")],
    "2005918544924664315": [("AXTI", "buy", 0.72, "半开玩笑但InP瓶颈/供应冲击是认真的，关键材料博弈"), ("LITE", "neutral", 0.5, "提及"), ("DOWA", "neutral", 0.5, "提及"), ("NVDA", "neutral", 0.5, "提及"), ("AMZN", "neutral", 0.5, "提及"), ("GOOGL", "neutral", 0.5, "提及"), ("MSFT", "neutral", 0.5, "提及")],
    "2005922423988715702": [("AXTI", "neutral", 0.55, "纠正InP价格数据，事实性补充")],
    "2005945821989368245": [("IQEPF", "sell", 0.6, "在卖公司+台湾子公司，债务陷阱风险")],
    "2005963686578642987": [("COHR", "buy", 0.75, "领先美国InP基板生产+新6寸晶圆厂"), ("AXTI", "buy", 0.7, "瓶颈提及"), ("DOWA", "neutral", 0.5, "上游提及"), ("LITE", "neutral", 0.5, "提及")],
    "2005969650077827256": [("AXTI", "buy", 0.65, "个人认为是好公司但有细节，基板生产是Sumitomo小部分收入")],
    "2005972815493885957": [("CRCL", "buy", 0.65, "喜欢Fintech稳定币标的"), ("NBIS", "buy", 0.7, "AI增长篮子核心"), ("IREN", "neutral", 0.5, "提及"), ("CIFR", "neutral", 0.5, "提及"), ("WULF", "neutral", 0.5, "提及"), ("NVDA", "neutral", 0.5, "提及"), ("AMD", "neutral", 0.5, "提及"), ("GOOGL", "neutral", 0.5, "提及"), ("MSFT", "neutral", 0.5, "提及"), ("AMZN", "neutral", 0.5, "提及"), ("TSM", "neutral", 0.5, "提及"), ("LITE", "buy", 0.6, "光子学篮子"), ("COHR", "buy", 0.6, "光子学篮子"), ("AAOI", "buy", 0.6, "光子学篮子"), ("AXTI", "buy", 0.78, "瓶颈核心")],
    "2005999653045862540": [("AXTI", "buy", 0.7, "已买AXTI最远期看涨期权，若有2027行权价会买")],
    "2006013108817678779": [("NBIS", "buy", 0.72, "700%+ ARR增长至7-90亿"), ("IREN", "buy", 0.65, "34亿+ ARR"), ("CIFR", "neutral", 0.5, "Neocloud提及"), ("WULF", "neutral", 0.5, "提及"), ("MSFT", "neutral", 0.5, "客户提及"), ("GOOGL", "neutral", 0.5, "提及")],
    "2006044118271610995": [("IREN", "neutral", 0.55, "具体讨论IREN MSFT预付款计算")],
    "2006063101486190958": [("MSFT", "neutral", 0.5, "预付款讨论提及"), ("IREN", "neutral", 0.5, "同上")],
    "2006101880988950622": [("NVDA", "hold", 0.55, "'prove it stage'，盈利能力强但需验证")],
    "2006301094394335399": [("MRVL", "buy", 0.78, "Maia ramp收入是MRVL FY收入两倍，市场严重低估"), ("AMZN", "neutral", 0.5, "客户提及"), ("MSFT", "neutral", 0.5, "客户提及"), ("AVGO", "neutral", 0.5, "提及"), ("META", "neutral", 0.5, "提及")],
    "2006306821632667832": [("POET", "buy", 0.6, "通过Celestial间接受益MRVL"), ("MRVL", "buy", 0.65, "Maia ramp利好"), ("AAOI", "neutral", 0.5, "光子学提及")],
    "2006401069363126671": [("MRVL", "buy", 0.7, "回应分析师claim，机构布局")],
    "2006434445205930103": [("MSTR", "buy", 0.6, "1月效应均值回归，-53.9%超跌"), ("HIMS", "buy", 0.6, "-41.9%超跌"), ("SMCI", "buy", 0.6, "超跌反弹候选"), ("SNAP", "neutral", 0.5, "提及"), ("MRVL", "neutral", 0.5, "提及")],
    "2006439143895875813": [("GOOGL", "buy", 0.65, "140买入做多，基本面无变化仅情绪翻转")],
    "2006442583757828201": [("NVDA", "hold", 0.55, "可辩论空头case(hyperscaler自建ASIC)，但看数字"), ("SMCI", "neutral", 0.5, "提及"), ("SNAP", "neutral", 0.5, "提及"), ("HIMS", "neutral", 0.5, "提及")],
    "2006447840072183848": [("PINS", "buy", 0.6, "6个月-28%超跌，候选标的")],
    "2006449819116806486": [("NBIS", "buy", 0.72, "5合1高Beta标的，波动大但核心"), ("CRWV", "neutral", 0.5, "同业提及"), ("MSFT", "neutral", 0.5, "客户提及")],
    "2006709693012467774": [("AXTI", "buy", 0.72, "2026 newsletter主题InP瓶颈核心"), ("LITE", "buy", 0.65, "SiPh主题"), ("NBIS", "buy", 0.7, "Neocloud主题"), ("TSLA", "neutral", 0.5, "软体机器人主题提及"), ("ONDS", "neutral", 0.5, "提及"), ("GOOGL", "neutral", 0.5, "提及"), ("NVDA", "neutral", 0.5, "提及"), ("INTC", "neutral", 0.5, "提及"), ("TSM", "neutral", 0.5, "提及"), ("V", "neutral", 0.5, "提及"), ("BOA", "neutral", 0.4, "提及"), ("IREN", "neutral", 0.5, "提及"), ("HUT", "neutral", 0.5, "提及"), ("CRWD", "neutral", 0.5, "提及"), ("CSCO", "neutral", 0.5, "提及"), ("MSFT", "neutral", 0.5, "提及"), ("RKLB", "neutral", 0.5, "提及"), ("ASTS", "neutral", 0.5, "提及"), ("PATH", "neutral", 0.5, "提及"), ("AMZN", "neutral", 0.5, "提及"), ("AMD", "neutral", 0.5, "提及"), ("POET", "neutral", 0.5, "提及"), ("AVGO", "neutral", 0.5, "提及"), ("XRP", "neutral", 0.5, "提及"), ("PYPL", "neutral", 0.5, "提及"), ("HOOD", "neutral", 0.5, "提及"), ("SOFI", "neutral", 0.5, "提及"), ("ASOZF", "neutral", 0.5, "提及"), ("AKAM", "neutral", 0.5, "提及"), ("ALAB", "neutral", 0.5, "提及"), ("CRDO", "neutral", 0.5, "提及"), ("CRCL", "neutral", 0.5, "提及")],
    "2006747117038010730": [("NVDA", "neutral", 0.5, "CPO讨论提及")],
    "2006748273760153734": [("SHMD", "buy", 0.65, "类似ASML的玻璃基板设备供应商，70%设备份额"), ("ASML", "neutral", 0.5, "类比提及")],
    "2006748783770833027": [("SHMD", "buy", 0.6, "周末深入研究SHMD，玻璃基板生产受益")],
    "2006754865351966806": [("LMND", "neutral", 0.5, "AI副产物提及"), ("PLTR", "buy", 0.6, "基础性演进标的更感兴趣")],
    "2006779022509031445": [("AMZN", "neutral", 0.5, "机器人部门提及"), ("TSLA", "neutral", 0.5, "机器人部门提及"), ("XPEV", "neutral", 0.5, "提及"), ("RR", "neutral", 0.5, "提及")],
    "2006964097515180284": [("AXTI", "buy", 0.65, "瓶颈主题延续提及"), ("SHMD", "buy", 0.65, "瓶颈主题")],
    "2006970261288137153": [("SMCI", "buy", 0.6, "可能选SMCI"), ("FIG", "neutral", 0.5, "Figma税务收割提及")],
    "2007012514488623118": [("SHMD", "buy", 0.65, "研究中，AVGO为客户+3亿市值上行空间大"), ("AVGO", "neutral", 0.5, "客户提及")],
    "2007071108831338685": [("TTD", "buy", 0.8, "'Strong Buy'"), ("SMCI", "buy", 0.8, "'Strong Buy'"), ("AIRO", "buy", 0.8, "'Strong Buy'"), ("INTC", "buy", 0.8, "'Strong Buy'"), ("HIMS", "buy", 0.8, "'Strong Buy'"), ("AXTI", "buy", 0.8, "'Strong Buy'"), ("TSM", "buy", 0.8, "'Strong Buy'"), ("NBIS", "buy", 0.8, "'Strong Buy'"), ("CIFR", "buy", 0.8, "'Strong Buy'"), ("HUT", "buy", 0.8, "'Strong Buy'"), ("IREN", "buy", 0.8, "'Strong Buy'"), ("WULF", "buy", 0.8, "'Strong Buy'"), ("GLXY", "buy", 0.8, "'Strong Buy'"), ("TSSI", "buy", 0.8, "'Strong Buy'"), ("META", "buy", 0.8, "'Strong Buy'"), ("ETOR", "buy", 0.8, "'Strong Buy'"), ("CRCL", "buy", 0.8, "'Strong Buy'"), ("KRKNF", "buy", 0.8, "'Strong Buy'"), ("ONDS", "buy", 0.8, "'Strong Buy'"), ("GEMI", "buy", 0.8, "'Strong Buy'"), ("NVDA", "buy", 0.72, "'Buy'"), ("MU", "buy", 0.72, "'Buy'"), ("AMKR", "buy", 0.72, "'Buy'"), ("SNAP", "buy", 0.72, "'Buy'"), ("RDDT", "buy", 0.72, "'Buy'"), ("AAOI", "buy", 0.72, "'Buy'"), ("COHR", "buy", 0.72, "'Buy'"), ("FISV", "buy", 0.72, "'Buy'"), ("FLY", "buy", 0.72, "'Buy'"), ("DJT", "buy", 0.72, "'Buy'"), ("LITE", "buy", 0.72, "'Buy'"), ("AMZN", "buy", 0.72, "'Buy'"), ("MRVL", "buy", 0.72, "'Buy'"), ("AVGO", "buy", 0.72, "'Buy'"), ("OSS", "buy", 0.72, "'Buy'"), ("BULL", "buy", 0.72, "'Buy'"), ("ORCL", "buy", 0.72, "'Buy'"), ("CRDO", "buy", 0.72, "'Buy'"), ("ALAB", "buy", 0.72, "'Buy'"), ("RGTI", "buy", 0.72, "'Buy'"), ("QBTS", "buy", 0.72, "'Buy'"), ("BMNR", "buy", 0.72, "'Buy'"), ("ETH", "neutral", 0.5, "提及"), ("PLTR", "buy", 0.72, "'Buy'"), ("WMT", "buy", 0.72, "'Buy'"), ("RKLB", "buy", 0.72, "'Buy'")],
    "2007073654979326364": [("WYFI", "buy", 0.65, "T2级+NScale 8.65亿协议，估值回撤后买入"), ("NBIS", "neutral", 0.55, "提及"), ("IREN", "neutral", 0.55, "提及"), ("CIFR", "neutral", 0.55, "提及"), ("WULF", "neutral", 0.55, "提及"), ("SLNH", "sell", 0.6, "除SLNH外都是极稳买入")],
    "2007084099174047817": [("SKC", "buy", 0.6, "Absolics CPO首梯队标的2.5亿市值"), ("NVDA", "neutral", 0.5, "CPO提及"), ("AVGO", "neutral", 0.5, "提及"), ("MRVL", "neutral", 0.5, "提及"), ("SHMD", "neutral", 0.5, "提及"), ("INTC", "neutral", 0.5, "提及")],
    "2007099013913616665": [("SMCI", "buy", 0.72, "PEG<0.5 vs DELL 1.2，收入50% Y/Y增长"), ("DELL", "neutral", 0.5, "对比提及")],
    "2007100073252098393": [("CRCL", "buy", 0.6, "不依赖以太坊，USDC多链可用"), ("SOL", "neutral", 0.5, "链提及"), ("USDC", "neutral", 0.4, "稳定币提及")],
    "2007113531158908939": [("AIRO", "buy", 0.65, "从基金/垂直看AIRO，20B Groq退出类比"), ("MSTR", "neutral", 0.5, "类比提及"), ("ONDS", "neutral", 0.5, "提及"), ("SMCI", "neutral", 0.5, "提及"), ("AVAV", "neutral", 0.5, "提及")],
    "2007133630154584128": [("OSS", "buy", 0.6, "边缘计算/代工2026热门主题"), ("SKYT", "buy", 0.6, "同上")],
    "2007135756511522942": [("CRWV", "buy", 0.65, "+10%表现好"), ("CIFR", "buy", 0.65, "+10%"), ("AAOI", "neutral", 0.5, "提及"), ("NBIS", "buy", 0.65, "+7%"), ("SMCI", "buy", 0.65, "+6%"), ("MRVL", "buy", 0.6, "+5%"), ("MSTR", "buy", 0.6, "+5%"), ("TSM", "buy", 0.6, "+5%")],
    "2007154198983651473": [("AXTI", "buy", 0.6, "董事会成员离世属例行程序，Northland 1亿融资扩产")],
    "2007202015940931878": [("AXTI", "buy", 0.75, "InP短缺与价差套利，市场研究显示类似HBM短缺"), ("NVDA", "neutral", 0.5, "提及"), ("COHR", "neutral", 0.5, "提及"), ("LITE", "neutral", 0.5, "提及"), ("MSFT", "neutral", 0.5, "提及"), ("AMZN", "neutral", 0.5, "提及"), ("DOWA", "neutral", 0.5, "提及")],
    "2007207971013677388": [("AXTI", "buy", 0.7, "中国暂停镓锗出口禁令至2026/11/27，利好AXTI窗口")],
    "2007210829117304953": [("GOOGL", "neutral", 0.5, "TPU建设需LITE/AXTI"), ("LITE", "buy", 0.6, "OCS需求"), ("AXTI", "buy", 0.75, "基板瓶颈，CEO称40% InP供应链")],
    "2007336559000117561": [("AXTI", "buy", 0.7, "日文帖，CEO称占InP供应链40%，7亿公司卡AI基础设施")],
    "2007340991989330098": [("AXTI", "buy", 0.7, "日文帖，个人估算InP基板30%+原料25-30%")],
    "2007346907941937452": [("AXTI", "buy", 0.65, "1亿融资扩产，产能封顶销售")],
    "2007382889911201983": [("AXTI", "neutral", 0.55, "InP平行类比达美乐，调侃提及"), ("DPZ", "neutral", 0.4, "调侃提及")],
    "2007387427820978510": [("CF", "buy", 0.65, "委内瑞拉局势利好重硫/氨/氮肥 disrupting"), ("CVE", "buy", 0.6, "提及"), ("VLO", "buy", 0.6, "提及"), ("LDOS", "neutral", 0.5, "国防提及"), ("AVAV", "buy", 0.6, "国防"), ("HII", "neutral", 0.5, "国防提及"), ("LHX", "neutral", 0.5, "国防提及"), ("BA", "neutral", 0.5, "国防提及"), ("RTX", "neutral", 0.5, "国防提及"), ("HON", "neutral", 0.5, "国防提及")],
    "2007406571752681725": [("CF", "buy", 0.65, "二阶效应含特立尼达多巴哥氨出口 disrupting")],
    "2007408596666200318": [("KRKNF", "buy", 0.6, "个人最爱之一")],
    "2007472856574373893": [("ASHM", "buy", 0.6, "政权更迭后买入信号"), ("GHM", "neutral", 0.5, "提及"), ("MVZ", "neutral", 0.5, "提及"), ("ENR", "neutral", 0.5, "提及"), ("AMTB", "neutral", 0.5, "提及"), ("CVX", "buy", 0.6, "石油"), ("SU", "neutral", 0.5, "提及")],
    "2007482618405945681": [("TRGP", "buy", 0.6, "美国战争利好，国家建设+新油储机会")],
    "2007489901877436756": [("ASHM", "buy", 0.65, "国家建设机会"), ("HLI", "neutral", 0.5, "困境债务提及"), ("LAZ", "neutral", 0.5, "困境债务提及"), ("GHM", "neutral", 0.5, "提及"), ("TRGP", "buy", 0.6, "石油"), ("CVX", "buy", 0.65, "石油"), ("VLO", "buy", 0.6, "石油"), ("PSX", "buy", 0.6, "石油")],
    "2007513114720551033": [("ASHM", "buy", 0.65, "国家建设稀有最佳机会"), ("CVX", "buy", 0.65, "资源金矿")],
    "2007514976177836145": [("ASHM", "buy", 0.62, "3个月+推翻国防部长，但Trump评论提及"), ("CVX", "buy", 0.62, "同上")],
    "2007516190487535904": [("PLTR", "neutral", 0.5, "调侃'委内瑞拉人终于知道PLTR 350 P/E为何'")],
    "2007649811621880238": [("GRZ", "buy", 0.7, "美国控制委内瑞拉17T+石油+2T+矿产，2026淘金热"), ("RMLFF", "buy", 0.6, "同上"), ("COP", "neutral", 0.5, "提及"), ("CVX", "buy", 0.65, "石油"), ("XOM", "neutral", 0.5, "提及"), ("TDW", "neutral", 0.5, "提及"), ("OI", "neutral", 0.5, "提及")],
    "2007653270102388974": [("GRZ", "buy", 0.72, "机构大多措手不及，散户难得机会")],
    "2007658287559573926": [("LMT", "neutral", 0.55, "国防提及，不让机构抢跑散户")],
    "2007682243276443931": [("GRZ", "buy", 0.65, "政权更迭后冻结资产解封"), ("ASHM", "buy", 0.65, "同上"), ("IBKR", "neutral", 0.5, "券商提及")],
    "2007685024704016879": [("CRWV", "buy", 0.6, "GPU编排软件复杂，仍有瓶颈"), ("NBIS", "buy", 0.6, "同上")],
    "2007752385599270959": [("HOOD", "neutral", 0.5, "自述能记忆HOOD历史波动事件")],
    "2007758407948788162": [("GDRZF", "buy", 0.7, "国家建设组合，+95.83%当日"), ("ASHM", "buy", 0.65, "+5.2%"), ("CVX", "buy", 0.6, "+5.19%"), ("AVAV", "buy", 0.65, "+14.7%"), ("HII", "neutral", 0.5, "+3.82%"), ("TRGP", "neutral", 0.5, "-3.14%")],
    "2007788288137171171": [("AXTI", "buy", 0.6, "AXTI子公司获批上市?")],
    "2007812299634213007": [("NBIS", "buy", 0.6, "欢迎回归，NBIS社区早期点出")],
    "2007823102622007454": [("OI", "sell", 0.6, "从名单移除OI")],
    "2007823817889263721": [("OI", "sell", 0.6, "移除OI，已出售仲裁权")],
    "2007872395990937749": [("BTC", "buy", 0.65, "委内瑞拉600亿+比特币影子储备"), ("MSTR", "buy", 0.6, "BTC代理提及")],
    "2008011715263476012": [("CXV", "buy", 0.6, "美国接管委内瑞拉长期利好CXV")],
    "2008155137018155478": [("ONDS", "buy", 0.72, "FinX组合+33.26%首位"), ("SKYT", "buy", 0.65, "+27.46%"), ("TE", "buy", 0.65, "+22.62%"), ("MU", "buy", 0.6, "+13.98%"), ("ASTS", "neutral", 0.5, "提及"), ("BMNR", "neutral", 0.5, "提及"), ("IREN", "neutral", 0.5, "提及"), ("CIFR", "neutral", 0.5, "提及"), ("AXTI", "neutral", 0.5, "提及"), ("KRKNF", "neutral", 0.5, "提及"), ("NBIS", "neutral", 0.5, "提及"), ("POET", "neutral", 0.5, "提及"), ("RKLB", "neutral", 0.5, "提及"), ("HOOD", "neutral", 0.5, "提及"), ("ZETA", "neutral", 0.5, "提及")],
    "2008156597873471936": [("ONDS", "neutral", 0.5, "等权组合ONDS=RKLB"), ("RKLB", "neutral", 0.5, "同上")],
    "2008157864792080568": [("PLTR", "neutral", 0.5, "PLTR/TSLA上季减少被ZETA取代"), ("TSLA", "neutral", 0.5, "同上"), ("ZETA", "neutral", 0.5, "新进入")],
    "2008235337643086305": [("GDRZF", "buy", 0.72, "国家建设组合启动+95.83%"), ("AVAV", "buy", 0.7, "+14.7%"), ("CVX", "buy", 0.65, "+5.19%"), ("ASHM", "buy", 0.65, "+5.2%"), ("HII", "neutral", 0.55, "+3.82%"), ("TRGP", "neutral", 0.5, "-3.14%")],
    "2008238953053454511": [("NBIS", "neutral", 0.55, "2500万ATM发行+与CRWV表现挂钩"), ("CRWV", "neutral", 0.5, "提及"), ("HUT", "buy", 0.6, "colo玩家表现好"), ("CIFR", "buy", 0.6, "同上"), ("WULF", "neutral", 0.5, "提及"), ("IREN", "neutral", 0.5, "提及")],
    "2008240303220892044": [("GDRZF", "buy", 0.72, "3.6亿市值+11亿已裁决索赔，价值洼地")],
    "2008334038726050249": [("AIRO", "buy", 0.72, "3亿市值+2亿订单积压+6000万现金，P/S低")],
    "2008339827624997004": [("VLO", "buy", 0.65, "即时利润扩张同意"), ("CVX", "buy", 0.7, "成为未公开的美国政府国家建设代理")],
    "2008352067765837942": [("CVX", "buy", 0.7, "Trump可能补贴委内瑞拉油企"), ("VLO", "buy", 0.65, "同上"), ("PSX", "buy", 0.6, "同上"), ("MPC", "buy", 0.6, "同上"), ("HAL", "neutral", 0.5, "提及"), ("BKR", "neutral", 0.5, "提及")],
    "2008355980858511802": [("CVX", "buy", 0.72, "唯一留在委内瑞拉，基本控制该国产能")],
    "2008425368966062263": [("VLO", "buy", 0.62, "最安全之一"), ("AVAV", "buy", 0.62, "同上"), ("CVX", "buy", 0.62, "同上")],
    "2008454507823591467": [("AIRO", "buy", 0.72, "已建仓3天+23%，市场未知国防股"), ("ONDS", "neutral", 0.5, "对比提及"), ("AVAV", "neutral", 0.5, "对比提及"), ("RKLB", "neutral", 0.5, "对比提及")],
    "2008501407247376433": [("COHR", "buy", 0.7, "比LITE更喜欢COHR，已卖LITE换仓"), ("LITE", "sell", 0.6, "卖出于385"), ("NBIS", "neutral", 0.5, "提及")],
    "2008504206475616633": [("CIEN", "sell", 0.6, "明确'不持有CIEN'")],
    "2008532157405552809": [("AIRO", "buy", 0.7, "递延收入非损失，下季确认，抛售被误解")],
    "2008545900877279485": [("IREN", "neutral", 0.55, "批评Mike Alfred拉抬砸盘")],
    "2008582578186678307": [("AXTI", "buy", 0.8, "中国出口管制核打击日本竞争对手，AXTI成InP垄断")],
    "2008589181501517850": [("AXTI", "buy", 0.7, "双刃剑：难出口日本损收入，但成垄断")],
    "2008591523059847514": [("LITE", "neutral", 0.5, "AI供应链突依赖单一供应商，不利"), ("COHR", "neutral", 0.5, "同上"), ("GOOGL", "neutral", 0.5, "同上"), ("NVDA", "neutral", 0.5, "同上"), ("AXTI", "buy", 0.65, "垄断地位")],
    "2008592416421601528": [("SMTOY", "neutral", 0.55, "日本巨头InP仅小部分业务，股票本身OK但中国受限")],
    "2008633673743298617": [("MU", "neutral", 0.5, "HBM瓶颈提及"), ("AXTI", "buy", 0.7, "InP瓶颈将更甚")],
    "2008635617018868008": [("AXTI", "buy", 0.82, "中国封杀日本InP后成单点失效垄断，AI建设依赖"), ("NVDA", "neutral", 0.5, "提及"), ("GOOGL", "neutral", 0.5, "提及"), ("MSFT", "neutral", 0.5, "提及"), ("META", "neutral", 0.5, "提及")],
    "2008636261976674661": [("AXTI", "buy", 0.65, "2026-2027当前架构会被瓶颈，美国终将绕过"), ("LITE", "neutral", 0.5, "提及"), ("COHR", "neutral", 0.5, "提及")],
    "2008638002323452260": [("MSFT", "neutral", 0.5, "材料价ATH西方付溢价提及"), ("AMZN", "neutral", 0.5, "同上"), ("META", "neutral", 0.5, "同上"), ("NVDA", "neutral", 0.5, "同上")],
    "2008706766574678180": [("AXTI", "buy", 0.7, "2026日历年风险极小，若停出口AI建设无法ramp")],
    "2008711844983435291": [("OUST", "neutral", 0.5, "询问对方是否有OUST论点")],
    "2008808147755168039": [("AXTI", "buy", 0.7, "日文帖，出口管制后AXTI垄断，今日+20%涨幅应更大")],
    "2008854319806787681": [("CRDO", "buy", 0.7, "25.7%回调加仓，CES误报机会"), ("AMZN", "neutral", 0.5, "线缆颜色误报提及"), ("AXTI", "neutral", 0.5, "提及")],
    "2008869090497302547": [("AMZN", "neutral", 0.5, "线缆颜色误报澄清"), ("CRDO", "buy", 0.68, "误报致跌，看多"), ("AXTI", "neutral", 0.5, "提及")],
    "2008877319239487537": [("MRVL", "neutral", 0.5, "MRVL多次宣布AEC杀手未兑现"), ("AMD", "neutral", 0.5, "类比AMD称击败NVDA"), ("NVDA", "neutral", 0.5, "提及"), ("CRDO", "neutral", 0.5, "提及"), ("AXTI", "neutral", 0.5, "提及")],
    "2008880903431586243": [("CRDO", "buy", 0.65, "TA图表130水平个人买入")],
    "2008882283592417631": [("LITE", "neutral", 0.55, "行业转向光子学，InP基板论点")],
    "2008885171156811870": [("CRDO", "buy", 0.6, "更多是交易，跌35%+落刀难择时"), ("SNDK", "neutral", 0.5, "提及"), ("MU", "neutral", 0.5, "提及"), ("AIRO", "neutral", 0.5, "提及")],
    "2008885741066375328": [("CRDO", "buy", 0.6, "波段交易，非大仓位"), ("MRVL", "neutral", 0.5, "误报提及")],
    "2008910857003221451": [("OSS", "buy", 0.78, "建仓OSS，1.55亿市值无人机蜂群/幽灵舰队/边缘AI")],
    "2008914099456164320": [("AXTI", "buy", 0.7, "AXTI/AIRO一周+50%"), ("AIRO", "buy", 0.7, "同上"), ("OSS", "buy", 0.7, "看好，尤其委内瑞拉入侵后")],
    "2008932076264046635": [("OSS", "buy", 0.8, "1.55亿市值已用于委内瑞拉美军，极度兴奋")],
    "2008933754904133680": [("AXTI", "buy", 0.65, "AXTI/AIRO近期有趣"), ("AIRO", "buy", 0.65, "同上"), ("OSS", "buy", 0.7, "好奇走势")],
    "2008934638073590160": [("KRKNF", "buy", 0.6, "长期了解喜欢"), ("OSS", "buy", 0.7, "上行更高故选OSS")],
    "2008941799382057128": [("AXTI", "buy", 0.65, "AXTI/AIRO基于公开信息的新颖综合"), ("AIRO", "buy", 0.65, "同上"), ("OSS", "buy", 0.7, "同上")],
    "2008944566800691442": [("OSS", "buy", 0.7, "等待观察能否6个月到10亿市值")],
    "2008961193365688542": [("AAOI", "neutral", 0.5, "AAOI绑定MSFT Maia，下调估值"), ("MSFT", "neutral", 0.5, "客户提及"), ("MRVL", "neutral", 0.5, "因此跌4%")],
    "2009041831296946384": [("AXTI", "buy", 0.7, "7n铟原料价格飙升，影响NVDA/LITE/COHR/MSFT/GOOGL"), ("NVDA", "neutral", 0.5, "提及"), ("LITE", "neutral", 0.5, "提及"), ("COHR", "neutral", 0.5, "提及"), ("MSFT", "neutral", 0.5, "提及"), ("GOOGL", "neutral", 0.5, "提及")],
    "2009042732535435526": [("OSS", "neutral", 0.5, "小盘不宜回购提及"), ("AVA", "neutral", 0.5, "同上")],
    "2009044396143182025": [("AXTI", "buy", 0.8, "'just getting started'，出口管制后单点失效垄断")],
    "2009045147980538325": [("AXTI", "buy", 0.7, "若AXTI无法出口美国，AI建设有更大问题")],
    "2009052378021150795": [("OSS", "buy", 0.65, "不想卖订阅，纯兴趣验证论点"), ("AXTI", "buy", 0.65, "同上")],
    "2009077684853485905": [("OSS", "buy", 0.7, "Bressner出售极正面，原部门拉低混合毛利率"), ("AIRO", "neutral", 0.5, "提及")],
    "2009169397168869831": [("AXTI", "buy", 0.7, "实为禁令非仅管制，军用终端用户相关")],
    "2009176232416669998": [("AXTI", "buy", 0.82, "InP有效垄断，NVDA/MSFT/META/AMZN单点失效")],
    "2009184670013907045": [("AXTI", "buy", 0.7, "日文帖，万亿hyperscaler被小公司瓶颈，垄断")],
    "2009187551974707515": [("AXTI", "buy", 0.72, "万亿hyperscaler首次被小公司瓶颈+垄断地位"), ("MSFT", "neutral", 0.5, "提及")],
    "2009198276235448369": [("AXTI", "buy", 0.7, "InP基板TAM从数亿小众商品非线性扩张"), ("NVDA", "neutral", 0.5, "提及"), ("LITE", "neutral", 0.5, "提及"), ("COHR", "neutral", 0.5, "提及"), ("MSFT", "neutral", 0.5, "提及"), ("GOOGL", "neutral", 0.5, "提及")],
    "2009200373496496218": [("AXTI", "buy", 0.7, "7n价格SMM暴涨，hyperscaler光学/光子学关键材料")],
    "2009275961003426050": [("AIRO", "buy", 0.7, "国防战争股+1.5T国防支出顺风+50%"), ("OSS", "buy", 0.7, "同上")],
    "2009277084875538708": [("AVAV", "buy", 0.65, "已持有AVAV/UMAC"), ("UMAC", "buy", 0.6, "持有")],
    "2009278429724614950": [("AIRO", "buy", 0.7, "远期P/S 3x vs同行30x+，仍持有")],
    "2009318848277909826": [("AVAV", "buy", 0.72, "8亿+合同+委内瑞拉自杀式无人机，10x潜力")],
    "2009321878071201826": [("AXTI", "buy", 0.72, "InP瓶颈实时上演，7n铟抛物线暴涨")],
    "2009330986522448103": [("AXTI", "buy", 0.7, "机构涌入+Northland 1亿融资后认识垄断地位")],
    "2009353462006399199": [("POET", "neutral", 0.55, "对2026-27 InP瓶颈几乎不存在，但是工程绕过方案"), ("AXTI", "buy", 0.7, "瓶颈核心")],
    "2009388507341754743": [("AXTI", "buy", 0.75, "盘后-29.54%，但瓶颈未变，2024合同递延一季非实质")],
    "2009394498200322144": [("COHR", "sell", 0.6, "瓶颈下游伤害COHR/LITE产能ramp"), ("LITE", "sell", 0.6, "同上"), ("GOOGL", "neutral", 0.5, "提及"), ("MSFT", "neutral", 0.5, "提及"), ("AXTI", "buy", 0.7, "垄断地位")],
    "2009398085680812084": [("AXTI", "buy", 0.7, "笑看AXTI因2024合同递延被抛售，前瞻更重要")],
    "2009399797271417276": [("AXTI", "buy", 0.7, "13天前点出瓶颈，SMM价格+未来定价上涨")],
    "2009407689349341557": [("AXTI", "buy", 0.72, "市场过度反应2024合同递延一季，无前瞻指引")],
    "2009411116724896223": [("AXTI", "buy", 0.7, "发布自己论点，杠杆押注AI建设光子学瓶颈")],
    "2009423554547487107": [("AXTI", "buy", 0.72, "Northland 1亿融资扩产，递延500万FCF非实质"), ("DOWA", "neutral", 0.5, "提及"), ("COHR", "neutral", 0.5, "提及")],
    "2009424935765295556": [("AXTI", "buy", 0.7, "笑看市场定价2024递延而非结构需求")],
    "2009429709860507753": [("MU", "neutral", 0.5, "HBM瓶颈非常规建模提及"), ("AXTI", "buy", 0.7, "双瓶颈中间"), ("NVDA", "neutral", 0.5, "提及"), ("MSFT", "neutral", 0.5, "提及"), ("GOOGL", "neutral", 0.5, "提及")],
    "2009436652184457529": [("AXTI", "buy", 0.78, "Q×P：AXTI同时控制AI建设光子学的量(垄断)与价")],
    "2009439229542322256": [("AXTI", "buy", 0.72, "澄清控制价格，量指InP供应链多数")],
    "2009446195933139114": [("AXTI", "buy", 0.8, "两大瓶颈中间：InP原料双寡头(AXTI+中国78-80%)"), ("DOWA", "neutral", 0.5, "提及"), ("GOOGL", "neutral", 0.5, "提及"), ("MSFT", "neutral", 0.5, "提及"), ("NVDA", "neutral", 0.5, "提及"), ("META", "neutral", 0.5, "提及"), ("MU", "neutral", 0.5, "提及"), ("SNDK", "neutral", 0.5, "提及")],
    "2009555729645211855": [("OSS", "neutral", 0.55, "小仓位，本应更大"), ("AXTI", "neutral", 0.55, "同上"), ("GLXY", "neutral", 0.5, "提及"), ("SOFI", "neutral", 0.5, "提及"), ("ASTS", "neutral", 0.5, "提及"), ("CRDO", "neutral", 0.5, "提及")],
    "2009561002958782514": [("LITE", "sell", 0.62, "卖空光子学持仓，Sumitomo被出口管制"), ("AAOI", "sell", 0.62, "同上"), ("COHR", "sell", 0.62, "同上")],
    "2009567495796265302": [("LITE", "sell", 0.6, "三阶效应血洗-10%+"), ("AAOI", "sell", 0.6, "同上"), ("COHR", "sell", 0.6, "同上"), ("GOOGL", "neutral", 0.5, "提及"), ("AXTI", "buy", 0.65, "垄断地位")],
    "2009575813793116456": [("AXTI", "buy", 0.72, "出口管制最大风险，但两大竞争对手被禁→AXTI+中国"), ("GOOGL", "neutral", 0.5, "提及")],
    "2009579146863931835": [("AXTI", "buy", 0.65, "推测未来几月极端瓶颈，多数人未察觉")],
    "2009583550304305224": [("COHR", "buy", 0.7, "10%回调加仓COHR，受影响小于LITE"), ("LITE", "sell", 0.6, "需购买基板受影响更大")],
    "2009616296388997534": [("AVGO", "buy", 0.65, "v8供应链即时利好")],
    "2009623958640078891": [("ONDS", "neutral", 0.55, "赞赏ONDS融资方式，但个人不持有")],
    "2009637599661510665": [("VLN", "buy", 0.78, "建仓VLN 1.55亿市值，自动驾驶/机器人AI半导体，市场误定价")],
    "2009640115157479743": [("VLN", "buy", 0.7, "分析师与算法误用多伦多VLN数据，定价错误")],
    "2009642945574760550": [("VLN", "buy", 0.65, "发布自己论点，新颖信息综合")],
    "2009644353543979313": [("VLN", "buy", 0.7, "8200万库存误读，核查差异发现现金消耗误算")],
    "2009665076006105291": [("VLN", "buy", 0.72, "本应7亿成长半导体股，被8200万capex错误人为压制")],
    "2009667279139881095": [("VLN", "buy", 0.72, "同上，本应7亿被错误数据压制")],
    "2009668088359514486": [("VLN", "buy", 0.7, "回到2.22亿仍被低估")],
    "2009672143999787356": [("VLN", "buy", 0.68, "市场无效完美例证，多伦多VLN数据混淆")],
    "2009676399905517886": [("VLN", "buy", 0.7, "7亿估值合理，但8200万capex错误被算入")],
    "2009679875880431737": [("VLN", "buy", 0.7, "7000万收入+9300万现金+MC极度不匹配")],
    "2009689623015108831": [("VLN", "buy", 0.72, "建模约7亿(6.5美元)，持有1年长线")],
    "2009693974181867825": [("VLN", "buy", 0.68, "160万股做空，做空方未理解估值脱节")],
    "2009702902420652084": [("VLN", "buy", 0.72, "算法做空交易将大错，仍按-8200万建模"), ("NVDA", "neutral", 0.5, "提及")],
    "2009708441573707876": [("VLN", "buy", 0.78, "发现VLN/VLN.TO混淆是十年级alpha")],
    "2009710665142018224": [("VLN", "buy", 0.7, "算法误用-8200万数据做空， amusing")],
    "2009713188192108557": [("VLN", "buy", 0.7, "做空份额接近耗尽")],
    "2009717659185885489": [("VLN", "buy", 0.65, "公司应重估，算法按错误数据做空")],
    "2009720858898772293": [("VLN", "buy", 0.72, "算法做空到接近无券可借")],
    "2009723451163242535": [("VLN", "buy", 0.75, "建模7.30美元(现2.5)，2027前瞻1.3亿+5x EV/Sales+9350万净现金")],
    "2009742235277930728": [("VLN", "buy", 0.7, "无债务+9350万现金+1100万库存，澄清负债vs债务")],
    "2009743779092410700": [("VLN", "buy", 0.72, "算法压制源于8200万typo，否则早已7美元")],
    "2009908150296826364": [("VLN", "buy", 0.7, "公允价值自行计算，重发指标无晶圆厂半导体"), ("NVDA", "neutral", 0.5, "提及")],
    "2009917560935104835": [("VLN", "buy", 0.68, "仅+58%，新闻有误，建模7美元")],
    "2009918872174883116": [("CRDO", "buy", 0.6, "线缆颜色纠正+VLN差异发现"), ("VLN", "buy", 0.68, "同上")],
    "2009989364462333990": [("VLN", "neutral", 0.55, "Fintel数据延迟，建议用Ortex看实时流量")],
    "2010000327123317051": [("VLN", "buy", 0.7, "源于极度缺乏理解，-8200万技术故障"), ("NVDA", "neutral", 0.5, "提及")],
    "2010002533088182642": [("VLN", "buy", 0.72, "NYSE与TSX的VLN ticker碰撞数据错误至昨日才被发现")],
    "2010016015330291787": [("VLN", "buy", 0.78, "2.5美元极端误定价，-8200万库存燃烧为数据错误"), ("LSCC", "neutral", 0.5, "提及"), ("MTSI", "neutral", 0.5, "提及"), ("NVDA", "neutral", 0.5, "提及")],
    "2010024809208643887": [("VLN", "buy", 0.75, "-8200万燃烧影响巨大，去年低毛利车规芯片转型")],
    "2010026534187512115": [("VLN", "buy", 0.72, "机器人供应链中发现，8000万前瞻收入+69%增长+NVDA毛利")],
    "2010047332235260390": [("NVDA", "neutral", 0.5, "对比提及"), ("VLN", "buy", 0.7, "8000万前瞻收入+NVDA毛利+2.4 EV/rev")],
    "2010049741460218026": [("VLN", "buy", 0.72, "自建Citadel级数据管道发现VLN，最大异常之一")],
    "2010073763308814496": [("VLN", "buy", 0.65, "享受发布VLN/CRDO信息综合"), ("CRDO", "neutral", 0.5, "提及")],
    "2010077751538266218": [("VLN", "buy", 0.72, "越看越喜欢，个人持有1年+")],
    "2010116701757874336": [("VLN", "neutral", 0.5, "Reddit互动帖，非信号")],
    "2010255341196628117": [("CRDO", "buy", 0.72, "+15.47%反弹，线缆颜色错误致百亿市值蒸发"), ("AMZN", "neutral", 0.5, "线缆颜色误报提及")],
    "2010260199605506440": [("CRDO", "buy", 0.68, "市场有时极蠢，CRDO线缆颜色+VLN现金/MC案例"), ("VLN", "buy", 0.68, "同上"), ("AXTI", "neutral", 0.5, "提及")],
    "2010298726221480119": [("VLN", "buy", 0.75, "0债务+9350万现金+1100万库存，算法/LLM用污染数据")],
    "2010300269654061457": [("VLN", "buy", 0.68, "Opus等用污染数据，需人工核查")],
    "2010301050214109600": [("VLN", "buy", 0.72, "-8200万重定价事件，三星/LG/奔驰为客户")],
    "2010399805848346667": [("CRDO", "neutral", 0.55, "不给预测但出现频繁(野村股权研究)")],
}


def _excerpt(text: str, limit: int = 480) -> str:
    t = (text or "").replace("\n", " ").strip()
    return t[:limit]


def main() -> None:
    signals = []
    ticker_post_dates = defaultdict(list)  # ticker -> [(date, rec)]
    missing = []
    for pid, judgements in JUDGEMENTS.items():
        p = BY_ID.get(pid)
        if not p:
            missing.append(pid)
            continue
        text = p.get("text", "")
        created = p["created_at"]
        for ticker, rec, conf, reasoning in judgements:
            signals.append({
                "post_id": pid,
                "ticker": ticker,
                "recommendation": rec,
                "confidence": conf,
                "reasoning": reasoning,
                "post_text_excerpt": _excerpt(text),
                "post_created_at": created,
                "post_score": int(p.get("score", 0) or 0),
            })
            ticker_post_dates[ticker].append((created[:10], rec))

    if missing:
        raise SystemExit(f"missing posts in BY_ID: {missing}")

    # consensus: 按账号全窗口重算（本批即全窗口，因为是首次）
    # 按 (date, ticker) 聚合 buy/sell/hold
    agg = defaultdict(lambda: {"buy": 0, "sell": 0, "hold": 0, "neutral": 0})
    for ticker, items in ticker_post_dates.items():
        for date, rec in items:
            agg[(date, ticker)][rec] += 1
    consensus = []
    for (date, ticker), counts in sorted(agg.items()):
        buy, sell, hold = counts["buy"], counts["sell"], counts["hold"]
        if buy >= sell * 1.5 and buy > 0:
            sig = "buy"
        elif sell >= buy * 1.5 and sell > 0:
            sig = "sell"
        elif hold > buy and hold > sell and hold > 0:
            sig = "neutral"
        else:
            sig = "neutral"
        consensus.append({
            "consensus_date": date,
            "ticker": ticker,
            "consensus_signal": sig,
            "buy_count": buy,
            "sell_count": sell,
            "hold_count": hold,
            "reasoning": f"{date} 该账号对 {ticker} 共 buy {buy}/sell {sell}/hold {hold}，依 1.5x 阈值判定 {sig}。仅供参考，非投资建议。",
        })

    # top_tickers: 按 mention_posts 排名（全窗口）
    mention = Counter()
    buy_sig = Counter()
    sell_sig = Counter()
    hold_sig = Counter()
    latest = {}
    for ticker, items in ticker_post_dates.items():
        mention[ticker] = len(items)
        for _, rec in items:
            if rec == "buy":
                buy_sig[ticker] += 1
            elif rec == "sell":
                sell_sig[ticker] += 1
            elif rec == "hold":
                hold_sig[ticker] += 1
        latest[ticker] = items[-1][1]
    top = []
    for rank, (ticker, mc) in enumerate(mention.most_common(50), 1):
        top.append({
            "rank_no": rank,
            "ticker": ticker,
            "mention_posts": mc,
            "buy_signals": buy_sig[ticker],
            "sell_signals": sell_sig[ticker],
            "hold_signals": hold_sig[ticker],
            "latest_signal": latest[ticker],
            "top_authors": ["aleabitoreddit"],
            "ai_summary": f"{ticker} 被提及 {mc} 次（buy {buy_sig[ticker]}/sell {sell_sig[ticker]}/hold {hold_sig[ticker]}）。仅供参考，非投资建议。",
        })

    now = datetime.now(timezone.utc)
    run_id = now.strftime("%Y%m%dT%H%M%SZ") + "_ai_aleabitoreddit"
    # checkpoint = 本批最后一条帖
    last_post = POSTS[-1]
    window_start = POSTS[0]["created_at"]
    window_end = last_post["created_at"]

    payload = {
        "run_id": run_id,
        "account": "aleabitoreddit",
        "window_start": window_start,
        "window_end": window_end,
        "post_count": len(POSTS),
        "signal_count": len(signals),
        "consensus_count": len(consensus),
        "top_ticker_count": len(top),
        "model": "glm-5.2",
        "prompt_version": "openclaw-v4",
        "status": "partial",
        "summary": (
            f"本批处理 {len(POSTS)} 帖（断点 NULL→{last_post['post_id']}），"
            f"生成 {len(signals)} 条 signals、{len(consensus)} 条 consensus、{len(top)} 条 top_tickers。"
            f"核心主题：Neocloud（NBIS/CRWV/IREN/WULF/CIFR，多次 Strong Buy/Buy 评级）、"
            f"InP 光子学瓶颈（AXTI 反复强调为 AI 建设单点失效垄断）、"
            f"VLN 多伦多/纽约 ticker 碰撞导致算法误定价、委内瑞拉政权更迭国家建设（GRZ/CVX/AVAV/ASHM）、"
            f"国防无人机（AIRO/OSS/AVAV）。NBIS 为最高信念多头，AXTI 为瓶颈核心多头。"
            f"仍有 {BATCH['remaining_estimate']} 帖未处理，下次从 checkpoint 继续。仅供参考，非投资建议。"
        ),
        "analyzed_at": now.strftime("%Y-%m-%d %H:%M:%S.%f"),
        "resume_from_post_id": RESUME_FROM_POST_ID,
        "resume_from_created_at": RESUME_FROM_CREATED_AT,
        "checkpoint_post_id": last_post["post_id"],
        "checkpoint_post_created_at": last_post["created_at"],
        "signals": signals,
        "consensus": consensus,
        "top_tickers": top,
    }
    json.dump(payload, open("/tmp/stock-ai/alea_run.json", "w"), ensure_ascii=False, indent=1)
    print(f"signals={len(signals)} consensus={len(consensus)} top={len(top)} status=partial checkpoint={last_post['post_id']}")


if __name__ == "__main__":
    main()
