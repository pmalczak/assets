import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from evaluators.valuation_date import (
    as_iso_date,
    filter_excel_rows_on_or_before,
    filter_on_or_before,
    format_date_columns,
    normalize_iso_date_columns,
    to_iso_date,
    to_iso_date_series,
)
from fx.get_last_fx import get_fx_as_of
from importers.assets.data_model import AssetsDef
from importers.mbank.data_model import MBankFile
from nbp_fx_repo.nbp_fx_repository import NBP_API_EUR


class ToIsoDateTests(unittest.TestCase):
    def test_round_trip_common_inputs(self):
        self.assertEqual(to_iso_date(date(2024, 1, 5)), "2024-01-05")
        self.assertEqual(to_iso_date(pd.Timestamp("2024-01-05")), "2024-01-05")
        self.assertEqual(to_iso_date("2024-1-5"), "2024-01-05")
        self.assertEqual(to_iso_date("2024-01-05 14:30"), "2024-01-05")
        self.assertEqual(to_iso_date("2024-01-05T14:30:00Z"), "2024-01-05")

    def test_tz_aware_uses_utc_calendar_day(self):
        # 2024-01-06 01:00+02 → still 2024-01-05 in UTC
        aware = datetime(2024, 1, 6, 1, 0, tzinfo=timezone(timedelta(hours=2)))
        self.assertEqual(to_iso_date(aware), "2024-01-05")

    def test_invalid_returns_none(self):
        self.assertIsNone(to_iso_date(None))
        self.assertIsNone(to_iso_date(""))
        self.assertIsNone(to_iso_date("not-a-date"))
        self.assertIsNone(to_iso_date(float("nan")))

    def test_as_iso_date_rejects_invalid(self):
        self.assertEqual(as_iso_date(date(2026, 7, 10)), "2026-07-10")
        with self.assertRaises(ValueError):
            as_iso_date("bogus")


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

    def test_filter_timestamp_and_iso_string_columns_agree(self):
        values = ["2026-07-01", "2026-07-08", "2026-07-15"]
        as_iso = pd.DataFrame({"d": values, "id": [1, 2, 3]})
        as_ts = pd.DataFrame({"d": pd.to_datetime(values), "id": [1, 2, 3]})
        cutoff = date(2026, 7, 10)
        left = filter_on_or_before(as_iso, "d", cutoff)["id"].tolist()
        right = filter_on_or_before(as_ts, "d", cutoff)["id"].tolist()
        self.assertEqual(left, right)
        self.assertEqual(left, [1, 2])

    def test_filter_drops_null_and_garbage(self):
        df = pd.DataFrame(
            {
                "d": ["2026-07-01", None, "bogus", "2026-07-20"],
                "id": [1, 2, 3, 4],
            }
        )
        result = filter_on_or_before(df, "d", date(2026, 7, 10))
        self.assertEqual(result["id"].tolist(), [1])

    def test_filter_excel_alias_matches_filter_on_or_before(self):
        df = pd.DataFrame({"Data": ["2026-01-01", "2026-06-01", "2026-12-01"]})
        a = filter_on_or_before(df, "Data", date(2026, 6, 30))
        b = filter_excel_rows_on_or_before(df, "Data", date(2026, 6, 30))
        self.assertEqual(a["Data"].tolist(), b["Data"].tolist())


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

    def test_normalize_iso_date_columns_and_series(self):
        df = pd.DataFrame({"d": ["2024-1-5", pd.Timestamp("2024-01-06")], "x": [1, 2]})
        out = normalize_iso_date_columns(df, "d")
        self.assertEqual(out["d"].tolist(), ["2024-01-05", "2024-01-06"])
        series = to_iso_date_series(pd.Series(["2024-01-05 12:00", "nope"]))
        self.assertEqual(series.tolist()[0], "2024-01-05")
        self.assertTrue(pd.isna(series.tolist()[1]) or series.tolist()[1] is None)


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
