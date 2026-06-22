"""Tests for scheduled CI account configuration."""

from __future__ import annotations

import unittest

from stock_detect.config import CI_SCHEDULED_X_ACCOUNTS, CI_SCHEDULED_X_ACCOUNTS_CSV


class CiScheduledAccountsTests(unittest.TestCase):
    def test_scheduled_accounts(self):
        self.assertEqual(
            CI_SCHEDULED_X_ACCOUNTS,
            (
                "aleabitoreddit",
                "elonmusk",
                "BofA_News",
                "mingchikuo",
                "SEMIglobal",
                "Gartner_inc",
            ),
        )
        self.assertEqual(
            CI_SCHEDULED_X_ACCOUNTS_CSV,
            "aleabitoreddit,elonmusk,BofA_News,mingchikuo,SEMIglobal,Gartner_inc",
        )


if __name__ == "__main__":
    unittest.main()
