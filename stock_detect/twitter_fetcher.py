"""Fetch X/Twitter timelines via official API (OAuth) with guest API fallback."""

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
    FULL_FETCH_MAX_PAGES,
    INCREMENTAL_MAX_PAGES,
    MAX_FETCH_PAGES,
    MAX_FETCH_POSTS,
    REQUEST_DELAY_SEC,
    USER_AGENT,
    X_API_TIMELINE_EXCLUDES,
)
from stock_detect.fetch_budget import extended_fetch_budget, incremental_api_pages
from stock_detect.fetch_window import (
    FetchStats,
    FetchWindow,
    default_fetch_window,
    filter_to_window,
    gap_window_before,
    guest_backfill_window,
)
from stock_detect.models import SocialPost, sort_posts_chronological
from stock_detect.tweet_cache import TweetCache
from stock_detect.x_api_client import XApiClient

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
        self.x_api = XApiClient()

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
        cache = TweetCache()
        normalized = [account.lstrip("@").lower() for account in accounts]
        use_combined = (
            cache.available
            and self.x_api.is_configured()
            and len(normalized) > 1
        )

        if use_combined:
            combined = self._fetch_accounts_cached_combined(
                normalized,
                window=window,
                max_pages=max_pages,
                max_posts=max_posts,
                stats=stats,
                cache=cache,
            )
            for post in combined:
                posts_by_id.setdefault(post.id, post)
        else:
            for account in normalized:
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
        cache = TweetCache()
        if cache.available:
            try:
                return self._fetch_account_cached(
                    screen_name,
                    window=window,
                    max_pages=max_pages,
                    max_posts=max_posts,
                    stats=stats,
                    cache=cache,
                )
            except Exception:
                pass

        return self._fetch_account_direct(
            screen_name,
            window=window,
            max_pages=max_pages,
            max_posts=max_posts,
            stats=stats,
        )

    @staticmethod
    def _advance_fetch_state(
        cache: TweetCache,
        account: str,
        *,
        user_id: str | None,
        posts: list[SocialPost],
        last_tweet_id: str | None,
    ) -> str | None:
        newest = TweetCache.newest_tweet_id(posts)
        if not newest:
            return last_tweet_id
        if last_tweet_id and int(newest) <= int(last_tweet_id):
            return last_tweet_id
        cache.save_state(account, user_id=user_id, last_tweet_id=newest)
        return newest

    def _fetch_and_persist_api_pages(
        self,
        screen_name: str,
        *,
        window: FetchWindow,
        max_pages: int,
        max_posts: int,
        stats: FetchStats,
        cache: TweetCache,
        user_id: str | None,
        since_id: str | None = None,
        advance_state: bool = False,
        stop_when_all_duplicates: bool = False,
    ) -> int:
        """Fetch one API page at a time, dedupe-check MySQL, and insert immediately."""
        total_inserted = 0
        posts_seen = 0
        last_tweet_id = since_id
        chronological = since_id is None
        buffer: list[SocialPost] = []

        for exclude in X_API_TIMELINE_EXCLUDES or (None,):
            for page in self.x_api.iter_timeline_pages(
                screen_name,
                window=window,
                max_pages=max_pages,
                max_posts=max(max_posts - posts_seen, 0),
                stats=stats,
                since_id=since_id,
                user_id=user_id,
                exclude=exclude,
            ):
                if not page:
                    continue
                if posts_seen + len(page) > max_posts:
                    page = page[: max_posts - posts_seen]

                if chronological:
                    buffer.extend(page)
                else:
                    inserted, skipped = cache.insert_posts_batch(
                        sort_posts_chronological(page),
                        skip_existing=True,
                    )
                    total_inserted += inserted
                    if advance_state:
                        last_tweet_id = self._advance_fetch_state(
                            cache,
                            screen_name,
                            user_id=user_id,
                            posts=page,
                            last_tweet_id=last_tweet_id,
                        )
                    if stop_when_all_duplicates and inserted == 0 and skipped == len(page):
                        return total_inserted

                posts_seen += len(page)
                if posts_seen >= max_posts:
                    break

        if chronological and buffer:
            buffer = sort_posts_chronological(buffer)
            inserted, _ = cache.insert_posts_batch(buffer, skip_existing=True)
            total_inserted += inserted
            if advance_state:
                self._advance_fetch_state(
                    cache,
                    screen_name,
                    user_id=user_id,
                    posts=buffer,
                    last_tweet_id=last_tweet_id,
                )

        return total_inserted

    def _guest_backfill_pre_api(
        self,
        screen_name: str,
        *,
        window: FetchWindow,
        max_pages: int,
        max_posts: int,
        max_passes: int,
        stats: FetchStats,
        cache: TweetCache,
        user_id: str | None,
        since_id: str | None,
    ) -> int:
        """Guest-fetch tweets older than the X API floor; multi-pass until gap closes."""
        total_inserted = 0
        passes = max(1, max_passes)

        for _ in range(passes):
            cached = cache.list_posts(screen_name, window)
            oldest = min((p.created for p in cached), default=None)
            guest_window = guest_backfill_window(window, oldest)
            if guest_window is None:
                break

            guest_posts, guest_stats = self.fetch_guest_history(
                screen_name,
                before=guest_window.before,
                after=guest_window.after,
                max_pages=max_pages,
                max_posts=max_posts,
            )
            stats.pages_fetched += guest_stats.pages_fetched
            stats.pages_skipped += guest_stats.pages_skipped
            for stream in guest_stats.streams_used:
                if stream not in stats.streams_used:
                    stats.streams_used.append(stream)

            if not guest_posts:
                break

            inserted, skipped = cache.insert_posts_batch(guest_posts, skip_existing=True)
            total_inserted += inserted
            self._advance_fetch_state(
                cache,
                screen_name,
                user_id=user_id,
                posts=guest_posts,
                last_tweet_id=since_id,
            )
            if inserted == 0 and skipped == len(guest_posts):
                break

        return total_inserted

    def _fetch_accounts_cached_combined(
        self,
        accounts: list[str],
        *,
        window: FetchWindow,
        max_pages: int,
        max_posts: int,
        stats: FetchStats,
        cache: TweetCache,
    ) -> list[SocialPost]:
        """Fetch multiple accounts: per-account backfill, then one combined incremental search."""
        cache.ensure_schema()
        stats.streams_used.append("MySQLCache")

        budget = extended_fetch_budget(window.window_days, max_posts, max_pages)
        incremental_targets: list[tuple[str, str, str | None]] = []
        total_api_inserted = 0

        missing_user_ids = []
        for account in accounts:
            state = cache.get_state(account)
            if not state or not state.user_id:
                missing_user_ids.append(account)
        if missing_user_ids and self.x_api.is_configured():
            stats.x_auth_mode = self.x_api.credentials.auth_mode()
            for account, user_id in self.x_api.resolve_user_ids(
                missing_user_ids,
                stats,
            ).items():
                cache.save_state(account, user_id=user_id)

        for account in accounts:
            posts = self._fetch_account_cached(
                account,
                window=window,
                max_pages=max_pages,
                max_posts=max_posts,
                stats=stats,
                cache=cache,
                skip_incremental=True,
                skip_ci_scan=True,
            )
            total_api_inserted += stats.api_posts_new or 0

            state = cache.get_state(account)
            cached = cache.list_posts(account, window)
            since_id = (state.last_tweet_id if state else None) or (
                TweetCache.newest_tweet_id(cached) if cached else None
            )
            user_id = state.user_id if state else None
            if cached and since_id:
                incremental_targets.append((account, since_id, user_id))

        if incremental_targets and self.x_api.is_configured():
            combined_inserted = self._fetch_combined_incremental(
                incremental_targets,
                window=window,
                max_pages=incremental_api_pages(budget),
                max_posts=budget.api_posts,
                stats=stats,
                cache=cache,
            )
            total_api_inserted += combined_inserted
            if combined_inserted > 0 and "XApiV2" not in stats.streams_used:
                stats.streams_used.append("XApiV2")

        stats.api_posts_new = total_api_inserted
        all_posts: list[SocialPost] = []
        for account in accounts:
            all_posts.extend(cache.list_posts(account, window))
            cache.record_ci_scan(
                account,
                api_posts_new=total_api_inserted,
                window_days=window.window_days,
            )
        return all_posts[:max_posts]

    def _fetch_combined_incremental(
        self,
        targets: list[tuple[str, str, str | None]],
        *,
        window: FetchWindow,
        max_pages: int,
        max_posts: int,
        stats: FetchStats,
        cache: TweetCache,
    ) -> int:
        """One search/recent request can return up to 100 tweets across all targets."""
        accounts = [account for account, _since_id, _user_id in targets]
        since_ids = [since_id for _account, since_id, _user_id in targets]
        since_id = min(since_ids, key=int)
        user_ids = {
            account: user_id
            for account, _since_id, user_id in targets
            if user_id
        }

        total_inserted = 0
        search_window = FetchWindow(
            after=window.after,
            before=window.before,
            window_days=window.window_days,
            api_start_time=False,
        )
        for page in self.x_api.iter_search_recent_pages(
            accounts,
            window=search_window,
            max_pages=max_pages,
            max_posts=max_posts,
            stats=stats,
            since_id=since_id,
        ):
            if not page:
                continue

            posts_by_account: dict[str, list[SocialPost]] = {}
            for post in page:
                posts_by_account.setdefault(post.author, []).append(post)

            page_inserted = 0
            page_skipped = 0
            for account, _since_id, user_id in targets:
                account_posts = posts_by_account.get(account, [])
                if not account_posts:
                    continue
                inserted, skipped = cache.insert_posts_batch(
                    sort_posts_chronological(account_posts),
                    skip_existing=True,
                )
                page_inserted += inserted
                page_skipped += skipped
                if inserted:
                    self._advance_fetch_state(
                        cache,
                        account,
                        user_id=user_ids.get(account),
                        posts=account_posts,
                        last_tweet_id=_since_id,
                    )

            total_inserted += page_inserted
            if page_inserted == 0 and page_skipped > 0:
                break

        return total_inserted

    def _fetch_account_cached(
        self,
        screen_name: str,
        *,
        window: FetchWindow,
        max_pages: int,
        max_posts: int,
        stats: FetchStats,
        cache: TweetCache,
        skip_incremental: bool = False,
        skip_ci_scan: bool = False,
    ) -> list[SocialPost]:
        cache.ensure_schema()
        cached = cache.list_posts(screen_name, window)
        stats.cache_posts = len(cached)
        stats.streams_used.append("MySQLCache")

        state = cache.get_state(screen_name)
        user_id = state.user_id if state else None
        oldest_cached = min((p.created for p in cached), default=None)
        since_id = (state.last_tweet_id if state else None) or (
            TweetCache.newest_tweet_id(cached) if cached else None
        )

        budget = extended_fetch_budget(window.window_days, max_posts, max_pages)
        api_inserted = 0

        if budget.guest_pages > 0:
            guest_inserted = self._guest_backfill_pre_api(
                screen_name,
                window=window,
                max_pages=budget.guest_pages,
                max_posts=budget.guest_posts,
                max_passes=budget.guest_passes,
                stats=stats,
                cache=cache,
                user_id=user_id,
                since_id=since_id,
            )
            api_inserted += guest_inserted
            cached = cache.list_posts(screen_name, window)
            oldest_cached = min((p.created for p in cached), default=None)
            stats.cache_posts = len(cached)

        if self.x_api.is_configured():
            stats.x_auth_mode = self.x_api.credentials.auth_mode()
            if not user_id:
                user_id = self.x_api.resolve_user_id(screen_name, stats)
                if user_id:
                    cache.save_state(screen_name, user_id=user_id)

            gap = gap_window_before(window, oldest_cached) if oldest_cached else None

            if gap is not None:
                api_inserted += self._fetch_and_persist_api_pages(
                    screen_name,
                    window=gap,
                    max_pages=min(budget.api_pages, FULL_FETCH_MAX_PAGES),
                    max_posts=budget.api_posts,
                    stats=stats,
                    cache=cache,
                    user_id=user_id,
                    since_id=None,
                    advance_state=False,
                )
            elif not cached:
                api_inserted += self._fetch_and_persist_api_pages(
                    screen_name,
                    window=window,
                    max_pages=min(budget.api_pages, FULL_FETCH_MAX_PAGES),
                    max_posts=budget.api_posts,
                    stats=stats,
                    cache=cache,
                    user_id=user_id,
                    since_id=None,
                    advance_state=True,
                )

            if cached and since_id and not skip_incremental:
                api_inserted += self._fetch_and_persist_api_pages(
                    screen_name,
                    window=window,
                    max_pages=incremental_api_pages(budget),
                    max_posts=budget.api_posts,
                    stats=stats,
                    cache=cache,
                    user_id=user_id,
                    since_id=since_id,
                    advance_state=True,
                    stop_when_all_duplicates=True,
                )

            stats.api_posts_new = api_inserted
            stats.streams_used.append("XApiV2")
        else:
            stats.api_posts_new = api_inserted

        posts = cache.list_posts(screen_name, window)
        stats.cache_posts = len(posts)
        if not skip_ci_scan:
            cache.record_ci_scan(
                screen_name,
                api_posts_new=api_inserted,
                window_days=window.window_days,
            )
        return posts[:max_posts]

    def _fetch_account_direct(
        self,
        screen_name: str,
        *,
        window: FetchWindow,
        max_pages: int,
        max_posts: int,
        stats: FetchStats,
    ) -> list[SocialPost]:
        posts_by_id: dict[str, SocialPost] = {}

        if self.x_api.is_configured():
            stats.x_auth_mode = self.x_api.credentials.auth_mode()
            api_posts = self.x_api.fetch_user_timeline(
                screen_name,
                window=window,
                max_pages=max_pages,
                max_posts=max_posts,
                stats=stats,
            )
            if api_posts or stats.pages_fetched > 0:
                stats.streams_used.append("XApiV2")
                for post in api_posts:
                    posts_by_id.setdefault(post.id, post)
                return list(posts_by_id.values())[:max_posts]

        for post in self._fetch_guest_sources(
            screen_name,
            window=window,
            max_pages=max_pages,
            max_posts=max_posts,
            stats=stats,
        ):
            posts_by_id.setdefault(post.id, post)

        return list(posts_by_id.values())[:max_posts]

    def fetch_guest_history(
        self,
        screen_name: str,
        *,
        before: datetime,
        after: datetime | None = None,
        max_pages: int = MAX_FETCH_PAGES,
        max_posts: int = MAX_FETCH_POSTS,
    ) -> tuple[list[SocialPost], FetchStats]:
        """Fetch older posts via guest/syndication APIs (no OAuth, no X API billing).

        Typical use: backfill tweets **older than** the 63-day CI window — set
        ``before`` to ``default_fetch_window().after``.
        """
        if before.tzinfo is None:
            before = before.replace(tzinfo=timezone.utc)
        start = after or datetime(2006, 3, 21, tzinfo=timezone.utc)
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        window = FetchWindow(after=start, before=before, window_days=0)
        stats = FetchStats()
        posts = self._fetch_guest_sources(
            screen_name.lstrip("@").lower(),
            window=window,
            max_pages=max_pages,
            max_posts=max_posts,
            stats=stats,
        )
        posts = [p for p in posts if window.contains(p.created)]
        posts.sort(key=lambda p: p.created, reverse=True)
        self.last_stats = stats
        return posts, stats

    def _fetch_guest_sources(
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
            page_posts, next_cursor, _oldest = self._parse_graphql_timeline(payload)
            known_ids = {post.id for post in posts}
            for post in page_posts:
                if post.id in known_ids:
                    continue
                if post.created >= window.before:
                    continue
                if post.created < window.after:
                    continue
                posts.append(post)
                known_ids.add(post.id)

            in_window = len(posts)
            if in_window >= max_posts:
                break
            if not next_cursor:
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
