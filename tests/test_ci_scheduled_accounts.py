"""Tests for scheduled CI account configuration."""

from __future__ import annotations

import unittest

from stock_detect.config import (
    CI_SCHEDULED_X_ACCOUNTS,
    CI_SCHEDULED_X_ACCOUNTS_CSV,
    CI_SCHEDULED_XUEQIU_ACCOUNTS,
    CI_SCHEDULED_XUEQIU_USERS,
    active_scheduled_social_accounts,
    active_scheduled_x_accounts,
)


class CiScheduledAccountsTests(unittest.TestCase):
    def test_scheduled_accounts(self):
        self.assertEqual(
            CI_SCHEDULED_X_ACCOUNTS,
            (
                "aleabitoreddit",
                "mingchikuo",
                "justinsuntron",
            ),
        )
        self.assertEqual(
            CI_SCHEDULED_X_ACCOUNTS_CSV,
            "aleabitoreddit,mingchikuo,justinsuntron",
        )

    def test_active_scheduled_accounts_excludes_disabled(self):
        self.assertEqual(
            active_scheduled_x_accounts(),
            ("aleabitoreddit", "mingchikuo"),
        )

    def test_active_scheduled_social_accounts_includes_xueqiu(self):
        self.assertEqual(CI_SCHEDULED_XUEQIU_USERS, ("1247347556", "1102105103"))
        self.assertEqual(CI_SCHEDULED_XUEQIU_ACCOUNTS, ("xueqiu:1247347556", "xueqiu:1102105103"))
        self.assertEqual(
            active_scheduled_social_accounts(),
            ("aleabitoreddit", "mingchikuo", "xueqiu:1247347556", "xueqiu:1102105103"),
        )


if __name__ == "__main__":
    unittest.main()
