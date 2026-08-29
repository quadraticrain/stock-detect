"""
中国重要财经要闻 · Bark 推送入口
================================
供 Cursor Automation（AI 定时任务）调用：Agent 自行研判重要性后，
把正文经 stdin 交给本脚本推送；无达标要闻时传 --skip，不推送。

用法:
  printf '%s' "$BODY" | python stock_push/china.py
  python stock_push/china.py --skip
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from bark import push_china


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--skip":
        print("[china] skip: no important Reuters/Bloomberg China finance today")
        return 0

    body = sys.stdin.read().strip()
    if not body:
        print("[china] empty stdin; use --skip if nothing to push", file=sys.stderr)
        return 1

    result = push_china(body)
    print(f"[china] push result: {result}")
    return 0 if result.get("code") == 200 else 1


if __name__ == "__main__":
    raise SystemExit(main())
