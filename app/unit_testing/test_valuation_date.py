import unittest
from datetime import date
from pathlib import Path

import pandas as pd

from evaluators.valuation_date import (
    filter_excel_rows_on_or_before,
    filter_on_or_before,
    format_date_columns,
)
from fx.get_last_fx import get_fx_as_of
from importers.assets.data_model import AssetsDef
from importers.mbank.data_model import MBankFile
from nbp_fx_repo.nbp_fx_repository import NBP_API_EUR


class FilterOnOrBeforeTests(unittest.TestCase):
    def test_filter_on_or_before_keeps_rows_up_to_valuation_date(self):
        df = pd.DataFrame(
            {
                MBankFile.MBANK_TRANSACTION_DATE: ["2026-07-01", "2026-07-08", "2026-07-15"],
                "value": [1, 2, 3],
            }
        )
        result = filter_on_or_before(df, MBankFile.MBANK_TRANSACTION_DATE, date(2026, 7, 10))
        self.assertEqual(len(result), 2)
        self.assertEqual(result["value"].tolist(), [1, 2])

    def test_filter_excel_rows_on_or_before(self):
        df = pd.DataFrame({"Data": pd.to_datetime(["2026-01-01", "2026-06-01", "2026-12-01"])})
        result = filter_excel_rows_on_or_before(df, "Data", date(2026, 6, 30))
        self.assertEqual(len(result), 2)


class FormatDateColumnsTests(unittest.TestCase):
    def test_format_date_columns_normalizes_mixed_types_for_parquet(self):
        df = pd.DataFrame(
            {
                AssetsDef.EVALUATION_DATE: [
                    "2026-07-01",
                    pd.Timestamp("2026-07-05"),
                ],
                "value": [1, 2],
            }
        )
        result = format_date_columns(df, AssetsDef.EVALUATION_DATE)
        self.assertEqual(result[AssetsDef.EVALUATION_DATE].tolist(), ["2026-07-01", "2026-07-05"])
        result.to_parquet("test_mixed_dates.parquet")
        Path("test_mixed_dates.parquet").unlink()


class GetFxAsOfTests(unittest.TestCase):
    def test_get_fx_as_of_uses_last_rate_on_or_before_date(self):
        fx_rates = pd.DataFrame(
            {NBP_API_EUR: [4.0, 4.1, 4.2]},
            index=pd.to_datetime(["2026-07-01", "2026-07-05", "2026-07-10"]),
        )
        result = get_fx_as_of(fx_rates, date(2026, 7, 7))
        eur_row = result[result[AssetsDef.CURRENCY] == NBP_API_EUR].iloc[0]
        self.assertEqual(float(eur_row["fx"]), 4.1)
        self.assertEqual(eur_row[AssetsDef.VALUE_DATE], "2026-07-05")

    def test_get_fx_as_of_accepts_string_index(self):
        fx_rates = pd.DataFrame(
            {NBP_API_EUR: [4.0, 4.1, 4.2]},
            index=["2026-07-01", "2026-07-05", "2026-07-10"],
        )
        result = get_fx_as_of(fx_rates, date(2026, 7, 7))
        eur_row = result[result[AssetsDef.CURRENCY] == NBP_API_EUR].iloc[0]
        self.assertEqual(float(eur_row["fx"]), 4.1)


if __name__ == "__main__":
    unittest.main()
