"""
Bark Push Utility - 推送消息到iOS Bark App + MySQL日志
"""
import requests
import json
import sys
import os

BARK_URL = os.environ.get("BARK_URL", "https://api.day.app/CXFgAnMVdZXTPvsKRgWKFo/")
BARK_SOUND = os.environ.get("BARK_SOUND", "healthnotification")

# MySQL配置
DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "rm-wz91qxav0rb3uxf17ro.mysql.cn-shenzhen.rds.aliyuncs.com"),
    "port": int(os.environ.get("DB_PORT", 3306)),
    "user": os.environ.get("DB_USER", "cache_data_write"),
    "password": os.environ.get("DB_PASSWORD", "7+ML%wbA%gg3fB+"),
    "database": os.environ.get("DB_NAME", "cache_data"),
    "connect_timeout": 10,
    "autocommit": True,
}


def _log_to_db(task_id: str, task_name: str, push_url: str,
               request_body: dict, http_status: int, response_body: str,
               success: bool, error_message: str = None):
    """推送日志写入MySQL push_response_log表"""
    try:
        import pymysql
        conn = pymysql.connect(**DB_CONFIG)
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO push_response_log
                   (task_id, task_name, push_url, request_body, http_status,
                    response_body, success, error_message, retry_count)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (int(task_id), task_name, push_url,
                 json.dumps(request_body, ensure_ascii=False)[:4000],
                 http_status, response_body[:2000] if response_body else "",
                 1 if success else 0, error_message, 0)
            )
        conn.close()
        print(f"[DB] 日志已写入: task={task_name} success={success}")
    except Exception as e:
        # 数据库写入失败不影响主流程
        print(f"[DB] 日志写入失败（不影响推送）: {e}")


# ponytail: self-hosted Bark nginx returns 413 around ~30 公司 / ~3k chars; split instead of truncate
MAX_BODY_CHARS = 2500


def _chunk_body(body: str, max_chars: int = MAX_BODY_CHARS) -> list:
    """按行拆成多条，避免单条请求被 nginx 413。"""
    if len(body) <= max_chars:
        return [body]
    chunks, cur, cur_len = [], [], 0
    for line in body.split("\n"):
        add = len(line) + (1 if cur else 0)
        if cur and cur_len + add > max_chars:
            chunks.append("\n".join(cur))
            cur, cur_len = [line], len(line)
        else:
            cur.append(line)
            cur_len += add
    if cur:
        chunks.append("\n".join(cur))
    return chunks


def _push_once(title: str, body: str, group: str, url: str,
               task_id: str, task_name: str) -> dict:
    """单条推送 + 写日志。"""
    payload = {
        "title": title,
        "body": body,
        "badge": 1,
        "sound": BARK_SOUND,
        "group": group,
    }
    if url:
        payload["url"] = url

    try:
        r = requests.post(BARK_URL, json=payload, timeout=15)
        try:
            result = r.json()
        except ValueError:
            result = {"code": -1, "message": f"非JSON响应: {r.text[:200]}"}
        http_status = r.status_code
        success = result.get("code") == 200

        if success:
            print(f"[Bark] 推送成功: {title[:40]}")
        else:
            print(f"[Bark] 推送失败: {result}")

        _log_to_db(
            task_id=task_id,
            task_name=task_name,
            push_url=BARK_URL,
            request_body=payload,
            http_status=http_status,
            response_body=json.dumps(result, ensure_ascii=False),
            success=success,
        )
        return result
    except Exception as e:
        print(f"[Bark] 推送异常: {e}")
        _log_to_db(
            task_id=task_id,
            task_name=task_name,
            push_url=BARK_URL,
            request_body=payload,
            http_status=0,
            response_body="",
            success=False,
            error_message=str(e),
        )
        return {"code": -1, "message": str(e)}


def push(title: str, body: str, group: str = "default", url: str = None,
         task_id: str = "0", task_name: str = "unknown") -> dict:
    """
    推送消息到Bark + 写入日志。正文过长时自动拆成多条。
    :return: 响应dict（多条时取最后一条；任一条失败则 code != 200）
    """
    chunks = _chunk_body(body)
    if len(chunks) > 1:
        print(f"[Bark] 正文 {len(body)} 字符，拆成 {len(chunks)} 条推送")

    last = {"code": -1, "message": "empty body"}
    failed = False
    for i, chunk in enumerate(chunks):
        t = title if len(chunks) == 1 else f"{title} ({i + 1}/{len(chunks)})"
        last = _push_once(t, chunk, group, url, task_id, task_name)
        if last.get("code") != 200:
            failed = True
    if failed:
        return {"code": -1, "message": last.get("message", "部分分片推送失败")}
    return last


def push_ipo(body: str) -> dict:
    """推送IPO打新消息"""
    return push("📊 打新日历（近3天）·腾讯龙虾", body, group="ipo",
                task_id="49214", task_name="A股港股打新提醒·腾讯龙虾")


def push_earnings(body: str) -> dict:
    """推送财报消息（旧：富文本直推 Bark；保留给本地调试）"""
    return push("📊 美股财报日历·腾讯龙虾", body, group="earnings",
                task_id="49406", task_name="美股财报提醒·腾讯龙虾")


# Go 后端财报分发接口（按用户订阅过滤后推 Bark）
EARNINGS_PUSH_API = os.environ.get("EARNINGS_PUSH_API") or (
    "https://quadraticequation.top/api/earnings/bark-forward"
)


def push_earnings_json(payload: dict) -> dict:
    """
    把财报 JSON 交给 GolangCalculateServer 分发推送。
    成功条件：HTTP 200 且响应 code==200（允许 sent=0，例如无人订阅命中）。
    """
    try:
        r = requests.post(EARNINGS_PUSH_API, json=payload, timeout=60)
        try:
            result = r.json()
        except ValueError:
            result = {"code": -1, "message": f"非JSON响应: {r.text[:200]}"}
        success = r.status_code == 200 and result.get("code") == 200
        if success:
            print(f"[EarningsAPI] 分发成功: {result.get('data')}")
        else:
            print(f"[EarningsAPI] 分发失败 status={r.status_code}: {result}")
        _log_to_db(
            task_id="49406",
            task_name="美股财报提醒·腾讯龙虾",
            push_url=EARNINGS_PUSH_API,
            request_body=payload,
            http_status=r.status_code,
            response_body=json.dumps(result, ensure_ascii=False),
            success=success,
        )
        if success:
            return result if isinstance(result, dict) else {"code": 200, "data": result}
        return {"code": -1, "message": result.get("message", f"http {r.status_code}")}
    except Exception as e:
        print(f"[EarningsAPI] 分发异常: {e}")
        _log_to_db(
            task_id="49406",
            task_name="美股财报提醒·腾讯龙虾",
            push_url=EARNINGS_PUSH_API,
            request_body=payload,
            http_status=0,
            response_body="",
            success=False,
            error_message=str(e),
        )
        return {"code": -1, "message": str(e)}




def push_china(body: str) -> dict:
    """推送中国财经要闻（路透/彭博精筛）"""
    return push("🇨🇳 中国财经要闻·腾讯龙虾", body, group="china",
                task_id="china01", task_name="中国财经要闻·腾讯龙虾")


if __name__ == "__main__":
    # 测试推送
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        push("🔔 测试推送", "这是来自stock-push的测试消息\n时间: " +
             __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M"),
             task_id="test", task_name="测试")
    elif len(sys.argv) > 2:
        push(sys.argv[1], sys.argv[2])
    else:
        print("Usage: python bark.py test | python bark.py <title> <body>")
