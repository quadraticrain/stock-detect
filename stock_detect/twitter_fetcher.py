"""Fetch public X/Twitter timelines via GraphQL guest API + syndication fallback."""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Iterator

import requests

from stock_detect.config import (
    DEFAULT_X_ACCOUNTS,
    MAX_FETCH_PAGES,
    MAX_FETCH_POSTS,
    REQUEST_DELAY_SEC,
    USER_AGENT,
)
from stock_detect.fetch_window import FetchStats, FetchWindow, default_fetch_window, filter_to_window
from stock_detect.models import SocialPost

_SYNDICATION = "https://syndication.twitter.com/srv/timeline-profile/screen-name/{screen_name}"
_FXTWITTER_USER = "https://api.fxtwitter.com/{screen_name}"
_MAIN_JS = "https://abs.twimg.com/responsive-web/client-web/main.08b2ceaa.js"
_GUEST_ACTIVATE = "https://api.x.com/1.1/guest/activate.json"
_GRAPHQL = "https://x.com/i/api/graphql/{query_id}/{operation}"
_GRAPHQL_STREAMS = (
    "UserTweets",
    "UserHighlightsTweets",
    "UserTweetsAndReplies",
)
_BEARER = (
    "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D"
    "1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)
_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)
_MAIN_JS_RE = re.compile(r"main\.([a-f0-9]+)\.js")


class TwitterFetcher:
    def __init__(self, user_agent: str = USER_AGENT):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml,application/json",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )
        self.last_stats = FetchStats()
        self._graphql_ops: dict[str, tuple[str, dict, dict]] | None = None
        self._guest_token: str | None = None

    def fetch_accounts(
        self,
        accounts: list[str] | None = None,
        *,
        window: FetchWindow | None = None,
        after: datetime | None = None,
        before: datetime | None = None,
        max_pages: int = MAX_FETCH_PAGES,
        max_posts: int = MAX_FETCH_POSTS,
    ) -> list[SocialPost]:
        accounts = accounts or DEFAULT_X_ACCOUNTS
        if window is None:
            window = default_fetch_window(before=before)
            if after is not None:
                window = FetchWindow(
                    after=after if after.tzinfo else after.replace(tzinfo=timezone.utc),
                    before=window.before,
                    window_days=window.window_days,
                )

        stats = FetchStats()
        posts_by_id: dict[str, SocialPost] = {}

        for account in accounts:
            account = account.lstrip("@").lower()
            if len(posts_by_id) >= max_posts:
                break
            remaining = max_posts - len(posts_by_id)
            batch = self._fetch_account(
                account,
                window=window,
                max_pages=max_pages,
                max_posts=remaining,
                stats=stats,
            )
            for post in batch:
                posts_by_id.setdefault(post.id, post)
            time.sleep(REQUEST_DELAY_SEC)

        raw_posts = list(posts_by_id.values())
        stats.posts_raw = len(raw_posts)
        posts = filter_to_window(raw_posts, window, created_at=lambda p: p.created)
        posts.sort(key=lambda p: p.created, reverse=True)
        stats.posts_fetched = len(posts)
        self.last_stats = stats
        return posts[:max_posts]

    def fetch_user(
        self,
        screen_name: str,
        *,
        window: FetchWindow | None = None,
        max_pages: int = MAX_FETCH_PAGES,
        max_posts: int = MAX_FETCH_POSTS,
    ) -> list[SocialPost]:
        window = window or default_fetch_window()
        stats = FetchStats()
        posts = self._fetch_account(
            screen_name.lstrip("@").lower(),
            window=window,
            max_pages=max_pages,
            max_posts=max_posts,
            stats=stats,
        )
        posts = filter_to_window(posts, window, created_at=lambda p: p.created)
        stats.posts_fetched = len(posts)
        self.last_stats = stats
        return posts[:max_posts]

    def _fetch_account(
        self,
        screen_name: str,
        *,
        window: FetchWindow,
        max_pages: int,
        max_posts: int,
        stats: FetchStats,
    ) -> list[SocialPost]:
        posts_by_id: dict[str, SocialPost] = {}
        user_id = self._resolve_user_id(screen_name)
        if user_id:
            pages_per_stream = max(3, max_pages // len(_GRAPHQL_STREAMS))
            for operation in _GRAPHQL_STREAMS:
                if len(posts_by_id) >= max_posts:
                    break
                batch = self._fetch_graphql_stream(
                    user_id,
                    operation=operation,
                    window=window,
                    max_pages=pages_per_stream,
                    max_posts=max_posts - len(posts_by_id),
                    stats=stats,
                )
                if batch:
                    stats.streams_used.append(operation)
                for post in batch:
                    posts_by_id.setdefault(post.id, post)

        if len(posts_by_id) < max_posts:
            for post in self._fetch_syndication_page(screen_name, stats=stats):
                posts_by_id.setdefault(post.id, post)

        return list(posts_by_id.values())[:max_posts]

    def _resolve_user_id(self, screen_name: str) -> str | None:
        url = _FXTWITTER_USER.format(screen_name=screen_name)
        try:
            resp = self.session.get(url, timeout=30)
            if resp.status_code != 200:
                return None
            payload = resp.json()
            user = payload.get("user") or {}
            return str(user.get("id") or "")
        except (requests.RequestException, json.JSONDecodeError, KeyError, TypeError):
            return None

    def _guest_headers(self) -> dict[str, str]:
        if self._guest_token is None:
            resp = self.session.post(
                _GUEST_ACTIVATE,
                headers={"Authorization": _BEARER},
                timeout=30,
            )
            resp.raise_for_status()
            self._guest_token = resp.json()["guest_token"]
        return {
            "Authorization": _BEARER,
            "x-guest-token": self._guest_token,
            "x-twitter-active-user": "yes",
            "x-twitter-client-language": "en",
        }

    def _load_graphql_ops(self) -> dict[str, tuple[str, dict, dict]]:
        if self._graphql_ops is not None:
            return self._graphql_ops

        ops: dict[str, tuple[str, dict, dict]] = {}
        try:
            resp = self.session.get(_MAIN_JS, timeout=45)
            if resp.status_code != 200:
                index = self.session.get(
                    "https://x.com",
                    headers={"User-Agent": self.session.headers["User-Agent"]},
                    timeout=30,
                )
                match = _MAIN_JS_RE.search(index.text)
                if match:
                    js_url = f"https://abs.twimg.com/responsive-web/client-web/main.{match.group(1)}.js"
                    resp = self.session.get(js_url, timeout=45)
            if resp.status_code != 200:
                self._graphql_ops = ops
                return ops

            js = resp.text
            for operation in _GRAPHQL_STREAMS:
                query_match = re.search(
                    rf'queryId:"([^"]+)",operationName:"{operation}"',
                    js,
                )
                meta_match = re.search(
                    rf'operationName:"{operation}",operationType:"query",metadata:\{{'
                    rf'featureSwitches:\[(.*?)\],fieldToggles:\[(.*?)\]',
                    js,
                )
                if not query_match or not meta_match:
                    continue
                switches = re.findall(r'"([^"]+)"', meta_match.group(1))
                toggles = re.findall(r'"([^"]+)"', meta_match.group(2))
                features = {name: ("enabled" in name) for name in switches}
                field_toggles = {name: False for name in toggles}
                ops[operation] = (query_match.group(1), features, field_toggles)
        except (requests.RequestException, json.JSONDecodeError, KeyError):
            pass

        self._graphql_ops = ops
        return ops

    def _fetch_graphql_stream(
        self,
        user_id: str,
        *,
        operation: str,
        window: FetchWindow,
        max_pages: int,
        max_posts: int,
        stats: FetchStats,
    ) -> list[SocialPost]:
        ops = self._load_graphql_ops()
        meta = ops.get(operation)
        if not meta:
            stats.streams_unavailable.append(operation)
            return []

        query_id, features, field_toggles = meta
        posts: list[SocialPost] = []
        cursor: str | None = None
        stream_available = False

        for _ in range(max_pages):
            if len(posts) >= max_posts:
                break

            variables = {
                "userId": user_id,
                "count": 40,
                "includePromotedContent": True,
                "withQuickPromoteEligibilityTweetFields": True,
                "withVoice": True,
            }
            if cursor:
                variables["cursor"] = cursor

            params = {
                "variables": json.dumps(variables),
                "features": json.dumps(features),
                "fieldToggles": json.dumps(field_toggles),
            }
            try:
                resp = self.session.get(
                    _GRAPHQL.format(query_id=query_id, operation=operation),
                    params=params,
                    headers=self._guest_headers(),
                    timeout=45,
                )
                if resp.status_code == 404:
                    stats.streams_unavailable.append(operation)
                    return posts
                if resp.status_code != 200:
                    stats.pages_skipped += 1
                    break
                payload = resp.json()
            except (requests.RequestException, json.JSONDecodeError, KeyError):
                stats.pages_skipped += 1
                break

            stream_available = True
            stats.pages_fetched += 1
            page_posts, next_cursor, oldest = self._parse_graphql_timeline(payload)
            known_ids = {post.id for post in posts}
            for post in page_posts:
                if post.id not in known_ids:
                    posts.append(post)
                    known_ids.add(post.id)

            if oldest and oldest < window.after:
                break
            if not next_cursor or not page_posts:
                break

            cursor = next_cursor
            time.sleep(REQUEST_DELAY_SEC)

        if not stream_available and operation not in stats.streams_unavailable:
            stats.streams_unavailable.append(operation)
        return posts[:max_posts]

    def _parse_graphql_timeline(
        self,
        payload: dict,
    ) -> tuple[list[SocialPost], str | None, datetime | None]:
        posts: list[SocialPost] = []
        next_cursor: str | None = None
        oldest: datetime | None = None

        timeline = (
            payload.get("data", {})
            .get("user", {})
            .get("result", {})
            .get("timeline", {})
            .get("timeline", {})
        )
        entries: list[dict] = []
        for instruction in timeline.get("instructions", []):
            if instruction.get("type") == "TimelineAddEntries":
                entries = instruction.get("entries", [])

        for entry in entries:
            content = entry.get("content", {})
            entry_type = content.get("entryType")
            if entry_type == "TimelineTimelineCursor" and content.get("cursorType") == "Bottom":
                next_cursor = content.get("value")
                continue

            tweet_results = list(self._iter_graphql_tweet_results(content))
            for tweet_result in tweet_results:
                post = self._graphql_tweet_to_post(tweet_result)
                if post is None:
                    continue
                posts.append(post)
                oldest = post.created if oldest is None or post.created < oldest else oldest

        return posts, next_cursor, oldest

    def _iter_graphql_tweet_results(self, content: dict) -> Iterator[dict]:
        entry_type = content.get("entryType")
        if entry_type == "TimelineTimelineItem":
            result = content.get("itemContent", {}).get("tweet_results", {}).get("result")
            if result:
                yield self._unwrap_graphql_tweet(result)
            return

        if entry_type == "TimelineTimelineModule":
            for module_item in content.get("items", []):
                result = (
                    module_item.get("item", {})
                    .get("itemContent", {})
                    .get("tweet_results", {})
                    .get("result")
                )
                if result:
                    yield self._unwrap_graphql_tweet(result)

    @staticmethod
    def _unwrap_graphql_tweet(result: dict) -> dict:
        if result.get("__typename") == "TweetWithVisibilityResults":
            return result.get("tweet") or result
        return result

    @staticmethod
    def _graphql_tweet_to_post(tweet_result: dict) -> SocialPost | None:
        legacy = tweet_result.get("legacy") or {}
        user_result = tweet_result.get("core", {}).get("user_results", {}).get("result", {})
        screen_name = (
            user_result.get("legacy", {}).get("screen_name")
            or user_result.get("core", {}).get("screen_name")
        )
        if not legacy or not screen_name:
            return None
        return _tweet_to_post(
            {
                "id_str": tweet_result.get("rest_id") or legacy.get("id_str"),
                "created_at": legacy.get("created_at"),
                "full_text": legacy.get("full_text", ""),
                "favorite_count": legacy.get("favorite_count", 0),
                "permalink": legacy.get("permalink") or f"/{screen_name}/status/{legacy.get('id_str')}",
                "entities": legacy.get("entities", {}),
            },
            screen_name.lower(),
        )

    def _fetch_syndication_page(
        self,
        screen_name: str,
        *,
        stats: FetchStats,
    ) -> list[SocialPost]:
        url = _SYNDICATION.format(screen_name=screen_name)
        try:
            resp = self.session.get(url, timeout=45)
            if resp.status_code != 200:
                stats.pages_skipped += 1
                return []
            match = _NEXT_DATA.search(resp.text)
            if not match:
                stats.pages_skipped += 1
                return []
            payload = json.loads(match.group(1))
            entries = payload.get("props", {}).get("pageProps", {}).get("timeline", {}).get("entries", [])
        except (requests.RequestException, json.JSONDecodeError, RuntimeError):
            stats.pages_skipped += 1
            return []

        stats.pages_fetched += 1
        posts: list[SocialPost] = []
        for entry in entries:
            if entry.get("type") != "tweet":
                continue
            tweet = entry.get("content", {}).get("tweet")
            if tweet:
                posts.append(_tweet_to_post(tweet, screen_name))
        return posts

    @classmethod
    def from_json_file(cls, path: str | Path) -> list[SocialPost]:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        items = raw if isinstance(raw, list) else raw.get("data", raw.get("posts", []))
        posts: list[SocialPost] = []
        for item in items:
            text = item.get("text") or item.get("full_text") or ""
            created_raw = item.get("created") or item.get("created_at")
            if isinstance(created_raw, str) and " +" in created_raw:
                created = parsedate_to_datetime(created_raw)
            elif isinstance(created_raw, (int, float)):
                created = datetime.fromtimestamp(created_raw, tz=timezone.utc)
            else:
                created = datetime.now(timezone.utc)
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            author = item.get("author") or item.get("screen_name") or "unknown"
            posts.append(
                SocialPost(
                    id=str(item.get("id") or item.get("id_str") or ""),
                    text=text,
                    author=author.lstrip("@"),
                    source="x",
                    created=created,
                    score=int(item.get("score") or item.get("favorite_count") or 0),
                    url=item.get("url") or item.get("permalink") or "",
                    tickers=_symbols_from_item(item),
                )
            )
        return posts

    def iter_posts(self, **kwargs) -> Iterator[SocialPost]:
        yield from self.fetch_accounts(**kwargs)


def _tweet_to_post(tweet: dict, screen_name: str) -> SocialPost:
    created = parsedate_to_datetime(tweet["created_at"])
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    text = tweet.get("full_text") or ""
    tweet_id = str(tweet.get("id_str") or "")
    permalink = tweet.get("permalink") or f"/{screen_name}/status/{tweet_id}"
    if not permalink.startswith("http"):
        permalink = f"https://x.com{permalink}"
    return SocialPost(
        id=tweet_id,
        text=text,
        author=screen_name,
        source="x",
        created=created,
        score=int(tweet.get("favorite_count") or 0),
        url=permalink,
        tickers=_symbols_from_tweet(tweet),
    )


def _symbols_from_tweet(tweet: dict) -> list[str]:
    symbols = []
    for sym in tweet.get("entities", {}).get("symbols", []):
        text = sym.get("text", "").upper()
        if text:
            symbols.append(text)
    if symbols:
        return sorted(set(symbols))
    return sorted(set(re.findall(r"\$([A-Z]{1,5})\b", tweet.get("full_text", "").upper())))


def _symbols_from_item(item: dict) -> list[str]:
    if item.get("tickers"):
        return [t.upper() for t in item["tickers"]]
    entities = item.get("entities", {})
    symbols = [s.get("text", "").upper() for s in entities.get("symbols", []) if s.get("text")]
    if symbols:
        return sorted(set(symbols))
    text = item.get("text") or item.get("full_text") or ""
    return sorted(set(re.findall(r"\$([A-Z]{1,5})\b", text.upper())))
