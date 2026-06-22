"""Tests for extended fetch budget splitting."""

from __future__ import annotations

import unittest

from stock_detect.config import EXTENDED_MAX_FETCH_PAGES
from stock_detect.fetch_budget import extended_fetch_budget


class FetchBudgetTests(unittest.TestCase):
    def test_standard_window_uses_single_api_budget(self):
        budget = extended_fetch_budget(63, max_posts=4000, max_pages=40)
        self.assertEqual(budget.api_posts, 4000)
        self.assertEqual(budget.api_pages, 40)
        self.assertEqual(budget.guest_posts, 0)
        self.assertEqual(budget.guest_pages, 0)
        self.assertEqual(budget.guest_passes, 0)

    def test_extended_window_splits_guest_and_api(self):
        budget = extended_fetch_budget(180, max_posts=4000, max_pages=40)
        self.assertGreater(budget.guest_pages, budget.api_pages)
        self.assertGreater(budget.guest_posts, budget.api_posts)
        self.assertGreaterEqual(budget.guest_passes, 2)
        self.assertEqual(budget.guest_pages, EXTENDED_MAX_FETCH_PAGES)


if __name__ == "__main__":
    unittest.main()
