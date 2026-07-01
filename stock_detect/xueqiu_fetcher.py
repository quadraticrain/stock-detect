"""Fetch selected Xueqiu user posts into SocialPost objects."""

from __future__ import annotations

import re
import os
from datetime import datetime, timezone
from html import unescape

import requests

from stock_detect.fetch_window import FetchWindow, default_fetch_window
from stock_detect.models import SocialPost, sort_posts_chronological
from stock_detect.post_tickers import tickers_from_text

DUAN_YONGPING_USER_ID = "1247347556"
DAN_BIN_USER_ID = "1102105103"
XUEQIU_USER_AGENT = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"


class XueqiuFetcher:
    def __init__(self, *, user_agent: str = XUEQIU_USER_AGENT, cookie: str | None = None):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "application/json, text/plain, */*",
                "Referer": "https://xueqiu.com/",
            }
        )
        cookie = cookie if cookie is not None else os.environ.get("XUEQIU_COOKIE", "")
        if cookie:
            self.session.headers["Cookie"] = cookie

    def fetch_user_posts(
        self,
        user_id: str = DUAN_YONGPING_USER_ID,
        *,
        window: FetchWindow | None = None,
        max_pages: int = 10,
        max_posts: int = 200,
    ) -> list[SocialPost]:
        window = window or default_fetch_window()
        posts: list[SocialPost] = []
        for page in range(1, max_pages + 1):
            response = self.session.get(
                "https://xueqiu.com/statuses/user_timeline.json",
                params={"user_id": user_id, "page": page, "count": 20},
                timeout=20,
            )
            response.raise_for_status()
            statuses = response.json().get("statuses") or []
            if not statuses:
                break
            page_old = False
            for item in statuses:
                post = _status_to_post(item, user_id)
                if not post:
                    continue
                if post.created < window.after:
                    page_old = True
                    continue
                if window.contains(post.created):
                    posts.append(post)
                    if len(posts) >= max_posts:
                        return sort_posts_chronological(posts)
            if page_old:
                break
        return sort_posts_chronological(posts)


def _status_to_post(item: dict, fallback_author: str) -> SocialPost | None:
    if not _is_own_status(item, fallback_author):
        return None
    post_id = str(item.get("id") or "")
    created_at = item.get("created_at")
    raw_text = str(item.get("text") or item.get("description") or "")
    text = _clean_html(raw_text)
    if not post_id or not created_at or not text:
        return None
    created = datetime.fromtimestamp(int(created_at) / 1000, timezone.utc)
    user = item.get("user") or {}
    author = f"xueqiu:{user.get('id') or fallback_author}"
    return SocialPost(
        id=f"xueqiu:{post_id}",
        text=text,
        author=author.lower(),
        source="xueqiu",
        created=created,
        score=int(item.get("reply_count") or item.get("retweet_count") or 0),
        url=f"https://xueqiu.com/{user.get('id') or fallback_author}/{post_id}",
        tickers=_xueqiu_tickers(raw_text),
    )


def _clean_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def _is_own_status(item: dict, fallback_author: str) -> bool:
    user = item.get("user") or {}
    if str(user.get("id") or item.get("user_id") or fallback_author) != str(fallback_author):
        return False
    if any(item.get(key) for key in ("retweeted_status", "retweeted_status_id")):
        return False
    return fallback_author == DUAN_YONGPING_USER_ID or not item.get("in_reply_to_status_id")


def _xueqiu_tickers(text: str) -> list[str]:
    upper = unescape(text).upper()
    tickers = set(tickers_from_text(upper))
    tickers.update(match.group(1) for match in re.finditer(r"/S/((?:SH|SZ|HK)?\d{4,6}|[A-Z]{1,5})\b", upper))
    tickers.update(match.group(1) for match in re.finditer(r"\$[^$()]*\(((?:SH|SZ|HK)?\d{4,6}|[A-Z]{1,5})\)\$", upper))
    tickers.update(match.group(1) for match in re.finditer(r"\$((?:SH|SZ|HK)\d{4,6}|[A-Z]{1,5})\$", upper))
    return sorted(tickers)
