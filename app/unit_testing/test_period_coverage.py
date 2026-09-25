# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest
from datetime import date

from importers.period_coverage import assert_no_coverage_gaps, find_coverage_gaps, merge_coverage


class PeriodCoverageTests(unittest.TestCase):
    def test_finds_gap_between_february_and_mid_march(self):
        gaps = find_coverage_gaps(
            [(date(2020, 1, 1), date(2020, 2, 28)), (date(2020, 3, 15), date(2020, 6, 30))]
        )
        self.assertEqual(gaps, [(date(2020, 2, 29), date(2020, 3, 14))])

    def test_nested_period_does_not_create_gap(self):
        self.assertEqual(
            find_coverage_gaps(
                [
                    (date(2020, 1, 1), date(2020, 6, 30)),
                    (date(2020, 2, 1), date(2020, 2, 28)),
                    (date(2020, 7, 1), date(2020, 8, 31)),
                ]
            ),
            [],
        )

    def test_merge_overlaps_and_touching(self):
        self.assertEqual(
            merge_coverage(
                [
                    (date(2020, 1, 1), date(2020, 2, 28)),
                    (date(2020, 2, 15), date(2020, 3, 31)),
                    (date(2020, 4, 1), date(2020, 4, 30)),
                ]
            ),
            [(date(2020, 1, 1), date(2020, 4, 30))],
        )

    def test_assert_reports_file_boundaries(self):
        with self.assertRaises(ValueError) as ctx:
            assert_no_coverage_gaps(
                [(date(2025, 1, 1), date(2025, 1, 31)), (date(2025, 3, 1), date(2025, 3, 31))],
                asset_id="p_re_eur",
            )
        self.assertIn("2025-01-31 .. 2025-03-01", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
