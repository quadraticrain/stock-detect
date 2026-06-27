"""Tests for new ticker detection and Bark formatting."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from stock_detect.models import SocialPost
from stock_detect.new_ticker_alert import (
    detect_new_ticker_hits,
    format_bark_body,
    format_bark_title,
    prior_tickers_by_author,
    push_bark_alert,
)


def _post(
    post_id: str,
    author: str,
    text: str,
    *,
    tickers: list[str] | None = None,
    hours_ago: float = 0,
) -> SocialPost:
    return SocialPost(
        id=post_id,
        text=text,
        author=author,
        source="x",
        created=datetime.now(timezone.utc) - timedelta(hours=hours_ago),
        score=1,
        url=f"https://x.com/{author}/status/{post_id}",
        tickers=tickers or [],
    )


class NewTickerAlertTests(unittest.TestCase):
    def test_prior_tickers_merges_db_and_text(self):
        posts = [
            _post("1", "demo", "hello", tickers=["TSM"]),
            _post("2", "demo", "buy $NVDA", tickers=[]),
        ]
        prior = prior_tickers_by_author(posts)
        self.assertEqual(prior["demo"], {"TSM", "NVDA"})

    def test_detect_new_ticker_only_for_first_recent_mention(self):
        historical = [
            _post("h1", "aleabitoreddit", "long $NVDA", tickers=["NVDA"]),
        ]
        recent = [
            _post("r1", "aleabitoreddit", "adding $TSM", tickers=["TSM"]),
            _post("r2", "aleabitoreddit", "still like $TSM", tickers=["TSM"]),
            _post("r3", "elonmusk", "Tesla", tickers=["TSLA"]),
        ]
        hits = detect_new_ticker_hits(recent, historical)
        self.assertEqual(len(hits), 2)
        self.assertEqual({(h.author, h.ticker) for h in hits}, {
            ("aleabitoreddit", "TSM"),
            ("elonmusk", "TSLA"),
        })

    def test_detect_skips_ticker_seen_before_window(self):
        historical = [_post("h1", "demo", "$AAPL", tickers=["AAPL"])]
        recent = [_post("r1", "demo", "$AAPL again", tickers=["AAPL"])]
        self.assertEqual(detect_new_ticker_hits(recent, historical), [])

    def test_bark_format_includes_author(self):
        hit = detect_new_ticker_hits(
            [_post("r1", "mingchikuo", "$AAPL", tickers=["AAPL"])],
            [],
        )[0]
        self.assertIn("mingchikuo", format_bark_title(hit))
        self.assertIn("mingchikuo", format_bark_body(hit))
        self.assertIn("$AAPL", format_bark_title(hit))

    @patch("stock_detect.new_ticker_alert.requests.post")
    def test_push_bark_alert_posts_json(self, mock_post):
        mock_post.return_value.status_code = 200
        hit = detect_new_ticker_hits(
            [_post("r1", "elonmusk", "$TSLA", tickers=["TSLA"])],
            [],
        )[0]
        push_bark_alert(hit, bark_url="https://api.day.app/testkey")
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], "https://api.day.app/testkey")
        self.assertIn("elonmusk", kwargs["json"]["title"])


if __name__ == "__main__":
    unittest.main()
