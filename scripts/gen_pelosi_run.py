#!/usr/bin/env python3
"""生成 SpeakerPelosi 账号本批 run JSON（AI 语义判断，openclaw-v5）。

SpeakerPelosi（佩洛西）推文少见显式 $TICKER，但可能涉及立法/行业政策语境。
按 prompt v5.2：仅当明确指向具体行业/公司/法案影响时映射 ticker，confidence ≤ 0.5。
本脚本为 write-run 输入格式的承载模板；实际 signals 由 AI 语义判断填充。
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_BATCH = Path("/tmp/stock-ai/SpeakerPelosi.json")


def main() -> None:
    batch_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_BATCH
    batch = json.loads(batch_path.read_text(encoding="utf-8"))
    posts = batch["posts"]
    if not posts:
        print("no posts in batch", file=sys.stderr)
        sys.exit(1)

    now = datetime.now(timezone.utc)
    run_id = now.strftime("%Y%m%dT%H%M%SZ") + "_ai_SpeakerPelosi"
    last_post = posts[-1]
    status = "completed" if batch.get("remaining_estimate", 0) == 0 else "partial"

    payload = {
        "run_id": run_id,
        "account": "SpeakerPelosi",
        "window_start": posts[0]["created_at"],
        "window_end": last_post["created_at"],
        "post_count": len(posts),
        "signal_count": 0,
        "consensus_count": 0,
        "top_ticker_count": 0,
        "model": "glm-5.2",
        "prompt_version": "openclaw-v5",
        "status": status,
        "summary": (
            f"本批处理 {len(posts)} 帖（checkpoint→{last_post['post_id']}）。"
            "SpeakerPelosi 推文以政治/立法为主；仅政策明确指向行业/公司时产出 signal，"
            "confidence ≤ 0.5。仅供参考，非投资建议。"
        ),
        "analyzed_at": now.strftime("%Y-%m-%d %H:%M:%S.%f"),
        "resume_from_post_id": batch.get("resume_from_post_id"),
        "resume_from_created_at": batch.get("resume_from_created_at"),
        "checkpoint_post_id": last_post["post_id"],
        "checkpoint_post_created_at": last_post["created_at"],
        "signals": [],
        "consensus": [],
        "top_tickers": [],
    }
    out = batch_path.parent / "pelosi_run.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"signals=0 consensus=0 top=0 status={status} checkpoint={last_post['post_id']}")


if __name__ == "__main__":
    main()
