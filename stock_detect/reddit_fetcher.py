"""Fetch posts from r/wallstreetbets via archive APIs (Arctic Shift / PullPush)."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import requests

from stock_detect.config import (
    MAX_FETCH_PAGES,
    MAX_FETCH_POSTS,
    REDDIT_PAGE_SIZE,
    REQUEST_DELAY_SEC,
    USER_AGENT,
)
from stock_detect.fetch_window import FetchStats, FetchWindow, default_fetch_window


@dataclass
class RedditPost:
    id: str
    title: str
    body: str
    flair: str | None
    created: datetime
    score: int
    num_comments: int
    permalink: str


class RedditFetcher:
    ARCTIC_SHIFT = "https://arctic-shift.photon-reddit.com/api/posts/search"
    PULLPUSH = "https://api.pullpush.io/reddit/search/submission/"

    def __init__(self, subreddit: str = "wallstreetbets", user_agent: str = USER_AGENT):
        self.subreddit = subreddit
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})
        self.last_stats = FetchStats()

    def fetch_posts(
        self,
        *,
        sort: str = "new",
        limit: int | None = None,
        time_filter: str = "week",
        after: datetime | None = None,
        before: datetime | None = None,
        max_pages: int = MAX_FETCH_PAGES,
        max_posts: int | None = None,
    ) -> list[RedditPost]:
        del time_filter  # fixed window replaces Reddit time_filter
        window = default_fetch_window(before=before)
        if after is not None:
            window = FetchWindow(
                after=after if after.tzinfo else after.replace(tzinfo=timezone.utc),
                before=window.before,
                window_days=window.window_days,
            )

        cap = min(limit or MAX_FETCH_POSTS, max_posts or MAX_FETCH_POSTS)
        stats = FetchStats()
        posts = self._fetch_arctic_shift(
            sort=sort,
            after=window.after,
            before=window.before,
            max_pages=max_pages,
            max_posts=cap,
            stats=stats,
        )
        if len(posts) < cap:
            posts.extend(
                self._fetch_pullpush(
                    sort=sort,
                    after=window.after,
                    before=window.before,
                    max_pages=max_pages,
                    max_posts=cap - len(posts),
                    stats=stats,
                )
            )

        posts = [p for p in posts if window.contains(p.created)]
        posts.sort(key=lambda p: p.created, reverse=True)
        stats.posts_fetched = len(posts)
        self.last_stats = stats
        return posts[:cap]

    @classmethod
    def from_json_file(cls, path: str | Path) -> list[RedditPost]:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        items = raw if isinstance(raw, list) else raw.get("data", raw.get("posts", []))
        return [_post_from_dict(item) for item in items]

    def _fetch_arctic_shift(
        self,
        *,
        sort: str,
        after: datetime,
        before: datetime,
        max_pages: int,
        max_posts: int,
        stats: FetchStats,
    ) -> list[RedditPost]:
        posts: list[RedditPost] = []
        before_ts: int | None = int(before.timestamp())
        order = "desc" if sort in {"new", "hot"} else "asc"

        for _ in range(max_pages):
            if len(posts) >= max_posts:
                break

            params: dict = {
                "subreddit": self.subreddit,
                "limit": min(REDDIT_PAGE_SIZE, max_posts - len(posts)),
                "sort": order,
                "after": int(after.timestamp()),
            }
            if before_ts is not None:
                params["before"] = before_ts

            try:
                resp = self.session.get(self.ARCTIC_SHIFT, params=params, timeout=45)
                if resp.status_code != 200:
                    stats.pages_skipped += 1
                    break
                payload = resp.json()
            except (requests.RequestException, json.JSONDecodeError):
                stats.pages_skipped += 1
                break

            stats.pages_fetched += 1
            data = payload.get("data", [])
            if not data:
                break

            oldest_on_page: datetime | None = None
            for item in data:
                post = _post_from_dict(item)
                posts.append(post)
                oldest_on_page = post.created if oldest_on_page is None or post.created < oldest_on_page else oldest_on_page

            if oldest_on_page and oldest_on_page < after:
                break

            before_ts = min(int(item.get("created_utc", 0)) for item in data)
            if len(data) < params["limit"]:
                break
            time.sleep(REQUEST_DELAY_SEC)

        return posts

    def _fetch_pullpush(
        self,
        *,
        sort: str,
        after: datetime,
        before: datetime,
        max_pages: int,
        max_posts: int,
        stats: FetchStats,
    ) -> list[RedditPost]:
        posts: list[RedditPost] = []
        before_ts: int | None = int(before.timestamp())

        for _ in range(max_pages):
            if len(posts) >= max_posts:
                break

            params: dict = {
                "subreddit": self.subreddit,
                "size": min(REDDIT_PAGE_SIZE, max_posts - len(posts)),
                "sort": "desc" if sort in {"new", "hot"} else "asc",
                "sort_type": "created_utc",
                "after": int(after.timestamp()),
            }
            if before_ts is not None:
                params["before"] = before_ts

            try:
                resp = self.session.get(self.PULLPUSH, params=params, timeout=45)
                if resp.status_code != 200:
                    stats.pages_skipped += 1
                    break
                data = resp.json().get("data", [])
            except (requests.RequestException, json.JSONDecodeError):
                stats.pages_skipped += 1
                break

            stats.pages_fetched += 1
            if not data:
                break

            oldest_on_page: datetime | None = None
            for item in data:
                post = _post_from_dict(item)
                posts.append(post)
                oldest_on_page = post.created if oldest_on_page is None or post.created < oldest_on_page else oldest_on_page

            if oldest_on_page and oldest_on_page < after:
                break

            before_ts = min(int(item.get("created_utc", 0)) for item in data)
            if len(data) < params["size"]:
                break
            time.sleep(REQUEST_DELAY_SEC)

        return posts

    def iter_posts(self, **kwargs) -> Iterator[RedditPost]:
        yield from self.fetch_posts(**kwargs)


def _post_from_dict(data: dict) -> RedditPost:
    created = datetime.fromtimestamp(int(data.get("created_utc", 0)), tz=timezone.utc)
    permalink = data.get("permalink") or data.get("full_link") or ""
    if permalink and not permalink.startswith("http"):
        permalink = f"https://www.reddit.com{permalink}"
    return RedditPost(
        id=data.get("id", ""),
        title=data.get("title", ""),
        body=data.get("selftext", "") or "",
        flair=data.get("link_flair_text"),
        created=created,
        score=int(data.get("score", 0)),
        num_comments=int(data.get("num_comments", 0)),
        permalink=permalink,
    )
