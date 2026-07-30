# -*- coding: utf-8 -*-
import unittest

import pandas as pd

from importers.deduplicate_records import deduplicate_records


class DeduplicateRecordsTests(unittest.TestCase):
    def test_mixed_iso8601_with_and_without_fractional_seconds(self):
        """Revolut trading miesza ...Z i ...123456Z — dedupe nie może padać na format."""
        cols = ["Date", "Ticker", "qty"]
        df1 = pd.DataFrame(
            [
                {"Date": "2026-03-18T10:01:03.123456Z", "Ticker": "AAA", "qty": 1},
                {"Date": "2026-03-18T10:01:03Z", "Ticker": "BBB", "qty": 2},
            ],
            columns=cols,
        )
        df2 = pd.DataFrame(
            [
                {"Date": "2026-03-18T10:01:03Z", "Ticker": "BBB", "qty": 2},
                {"Date": "2026-03-19T09:00:00.000000Z", "Ticker": "CCC", "qty": 3},
            ],
            columns=cols,
        )
        merged = deduplicate_records(df1, df2, "Date", cols)
        self.assertEqual(len(merged), 3)
        self.assertEqual(set(merged["Ticker"]), {"AAA", "BBB", "CCC"})

    def test_nan_in_key_columns_does_not_break_join(self):
        """CASH TOP-UP / fee: Ticker i Quantity bywają NaN."""
        cols = ["Date", "Ticker", "Type", "Quantity"]
        df1 = pd.DataFrame(
            [
                {
                    "Date": "2026-03-18T10:01:03Z",
                    "Ticker": float("nan"),
                    "Type": "ROBO MANAGEMENT FEE",
                    "Quantity": float("nan"),
                },
                {
                    "Date": "2026-03-18T11:00:00Z",
                    "Ticker": "AAA",
                    "Type": "BUY - MARKET",
                    "Quantity": 1.0,
                },
            ],
            columns=cols,
        )
        df2 = pd.DataFrame(
            [
                {
                    "Date": "2026-03-18T10:01:03Z",
                    "Ticker": float("nan"),
                    "Type": "ROBO MANAGEMENT FEE",
                    "Quantity": float("nan"),
                },
                {
                    "Date": "2026-03-19T09:00:00Z",
                    "Ticker": "BBB",
                    "Type": "BUY - MARKET",
                    "Quantity": 2.0,
                },
            ],
            columns=cols,
        )
        merged = deduplicate_records(df1, df2, "Date", cols)
        self.assertEqual(len(merged), 3)


if __name__ == "__main__":
    unittest.main()
