from __future__ import annotations

import unittest
from datetime import datetime, timezone

from scripts.sync_xueqiu_cookie_secret import BrowserCookie, chrome_expires_at, format_cookie_header


class SyncXueqiuCookieSecretTests(unittest.TestCase):
    def test_chrome_expires_at_uses_chrome_epoch(self):
        self.assertEqual(chrome_expires_at(1_000_000), datetime(1601, 1, 1, 0, 0, 1, tzinfo=timezone.utc))

    def test_format_cookie_header_skips_empty_and_expired(self):
        cookies = [
            BrowserCookie("z", "", 0),
            BrowserCookie("old", "1", 1),
            BrowserCookie("xq_a_token", "token", 0),
            BrowserCookie("u", "6033220609", 0),
        ]

        self.assertEqual(format_cookie_header(cookies), "xq_a_token=token; u=6033220609")


if __name__ == "__main__":
    unittest.main()
