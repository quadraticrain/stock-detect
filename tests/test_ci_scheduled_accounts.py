"""Tests for scheduled CI account configuration."""

from __future__ import annotations

import unittest

from stock_detect.config import (
    CI_SCHEDULED_X_ACCOUNTS,
    CI_SCHEDULED_X_ACCOUNTS_CSV,
    active_scheduled_x_accounts,
)


class CiScheduledAccountsTests(unittest.TestCase):
    def test_scheduled_accounts(self):
        self.assertEqual(
            CI_SCHEDULED_X_ACCOUNTS,
            (
                "aleabitoreddit",
                "elonmusk",
                "mingchikuo",
                "justinsuntron",
            ),
        )
        self.assertEqual(
            CI_SCHEDULED_X_ACCOUNTS_CSV,
            "aleabitoreddit,elonmusk,mingchikuo,justinsuntron",
        )

    def test_active_scheduled_accounts_excludes_disabled(self):
        self.assertEqual(
            active_scheduled_x_accounts(),
            ("aleabitoreddit", "elonmusk", "mingchikuo"),
        )


if __name__ == "__main__":
    unittest.main()
