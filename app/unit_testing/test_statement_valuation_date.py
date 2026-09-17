# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest
from datetime import date

import pandas as pd

from importers.assets.data_model import AssetsDef
from roi.statement_valuation_date import (
    attach_evaluation_date,
    evaluation_date_from_file_dates,
    evaluation_date_from_frame,
)


class StatementValuationDateTests(unittest.TestCase):
    def test_uses_latest_file_date(self):
        self.assertEqual(
            evaluation_date_from_file_dates(
                ["2026-01-01", "2026-06-30"],
                date(2026, 9, 16),
            ),
            "2026-06-30",
        )

    def test_clamps_to_calculation_date(self):
        self.assertEqual(
            evaluation_date_from_file_dates(
                ["2026-06-30"],
                date(2026, 3, 1),
            ),
            "2026-03-01",
        )

    def test_missing_or_invalid_dates_are_none(self):
        self.assertIsNone(evaluation_date_from_file_dates([], date(2026, 9, 16)))
        self.assertIsNone(evaluation_date_from_file_dates(["x"], date(2026, 9, 16)))
        self.assertIsNone(
            evaluation_date_from_frame(
                pd.DataFrame({"other": [1]}),
                "ref_date",
                date(2026, 9, 16),
            )
        )

    def test_attach_empty_string_when_missing(self):
        row = attach_evaluation_date({"asset_id": "x"}, None)
        self.assertEqual(row[AssetsDef.EVALUATION_DATE], "")


if __name__ == "__main__":
    unittest.main()
