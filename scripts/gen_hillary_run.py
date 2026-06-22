#!/usr/bin/env python3
"""生成 HillaryClinton 账号本批 run JSON（AI 语义判断，openclaw-v4）。

HillaryClinton 为政治人物，推文 0 条显式 $TICKER，经扫描无任何可映射公司/ticker
语境（"profit"/"tax"/"dollar"等均为政治批评用语，"dow"为无人机名误匹配）。
按 prompt「非财经语境多数 neutral」，本批 0 signals，status=completed（已无剩余）。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

BATCH = json.load(open("/tmp/stock-ai/HillaryClinton.json"))
POSTS = BATCH["posts"]
RESUME_FROM_POST_ID = BATCH["resume_from_post_id"]
RESUME_FROM_CREATED_AT = BATCH["resume_from_created_at"]


def main() -> None:
    now = datetime.now(timezone.utc)
    run_id = now.strftime("%Y%m%dT%H%M%SZ") + "_ai_HillaryClinton"
    last_post = POSTS[-1]
    # status: remaining_estimate=0 → completed
    status = "completed" if BATCH["remaining_estimate"] == 0 else "partial"

    payload = {
        "run_id": run_id, "account": "HillaryClinton",
        "window_start": POSTS[0]["created_at"], "window_end": last_post["created_at"],
        "post_count": len(POSTS), "signal_count": 0,
        "consensus_count": 0, "top_ticker_count": 0,
        "model": "glm-5.2", "prompt_version": "openclaw-v4", "status": status,
        "summary": (
            f"本批处理 {len(POSTS)} 帖（断点 NULL→{last_post['post_id']}）。"
            f"HillaryClinton 推文 0 条显式 $TICKER，经扫描无任何可映射公司/ticker 语境："
            f"'profit'/'tax'/'dollar'均为对特朗普/普京的政治批评用语，'dow'为无人机名误匹配，"
            f"'invest'/'job'为泛用词。按 prompt「非财经语境多数 neutral」，本批 0 signals。"
            f"该账号推文以政治/节日/民主议题为主，不适合做股票舆情映射。"
            f"已追上最新数据，status=completed，checkpoint 落在最新帖，下次仅处理增量。仅供参考，非投资建议。"
        ),
        "analyzed_at": now.strftime("%Y-%m-%d %H:%M:%S.%f"),
        "resume_from_post_id": RESUME_FROM_POST_ID, "resume_from_created_at": RESUME_FROM_CREATED_AT,
        "checkpoint_post_id": last_post["post_id"], "checkpoint_post_created_at": last_post["created_at"],
        "signals": [], "consensus": [], "top_tickers": [],
    }
    json.dump(payload, open("/tmp/stock-ai/hillary_run.json", "w"), ensure_ascii=False, indent=1)
    print(f"signals=0 consensus=0 top=0 status={status} checkpoint={last_post['post_id']}")


if __name__ == "__main__":
    main()
