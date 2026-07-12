import unittest
from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd

from app_proc.calculate_assets import (
    _finalize_assets_snapshot,
    calculate_assets, ASSETS_SNAPSHOT_STEP, PORTFOLIO_VALUATION_DATE, assets_snapshot_resource,
)
from app_proc.data_steps_root import get_data_steps_root
from importers.assets.data_model import AssetsDef, AssetsFile


class AssetsSnapshotResourceTests(unittest.TestCase):
    def test_assets_snapshot_resource_format(self):
        self.assertEqual(
            assets_snapshot_resource(date(2026, 7, 7)),
            f"{ASSETS_SNAPSHOT_STEP}/2026-07-07.parquet",
        )


class FinalizeAssetsSnapshotTests(unittest.TestCase):
    def test_finalize_adds_portfolio_valuation_date(self):
        assets = pd.DataFrame(
            [
                {
                    AssetsFile.ID: "a1",
                    AssetsFile.GROUP: "1 test",
                    AssetsFile.TYPE: "cash",
                    AssetsFile.DESCR: "x",
                    AssetsFile.KIND: "assets.cash",
                    AssetsFile.CURRENCY: "PLN",
                    AssetsFile.NOTES: "",
                    AssetsDef.EVALUATION_DATE: "2026-07-01",
                    AssetsDef.VALUE: 100.0,
                    AssetsDef.VALUE_PLN: 100,
                    AssetsDef.VALUE_DATE: "2026-07-07",
                    AssetsDef.DAYS_AFTER_VALUATION: 6,
                    AssetsDef.IBAN: "",
                    "fx": 1.0,
                }
            ]
        )
        result = _finalize_assets_snapshot(assets, date(2026, 7, 7))
        self.assertEqual(result[PORTFOLIO_VALUATION_DATE].iloc[0], "2026-07-07")
        self.assertNotIn("fx", result.columns)
        self.assertNotIn(AssetsFile.NOTES, result.columns)


class CalculateAssetsObtainTests(unittest.TestCase):
    @patch("app_proc.calculate_assets.DATA_STEP")
    def test_calculate_assets_calls_obtain_with_dated_product(self, data_step_mock):
        valuation_date = date(2026, 7, 7)
        expected_df = pd.DataFrame([{AssetsFile.ID: "a1", PORTFOLIO_VALUATION_DATE: "2026-07-07"}])
        frame_mock = MagicMock()
        frame_mock.data_frame.return_value = expected_df
        data_step_mock.obtain.return_value = frame_mock

        result = calculate_assets(valuation_date=valuation_date)

        data_step_mock.init_steps.assert_called_once()
        data_step_mock.obtain.assert_called_once()
        args, kwargs = data_step_mock.obtain.call_args
        self.assertEqual(args[0], assets_snapshot_resource(valuation_date))
        self.assertEqual(kwargs["valuation_date"], valuation_date)
        pd.testing.assert_frame_equal(result, expected_df)

    @patch("app_proc.calculate_assets.DATA_STEP")
    def test_calculate_assets_defaults_valuation_date_to_today(self, data_step_mock):
        frame_mock = MagicMock()
        frame_mock.data_frame.return_value = pd.DataFrame()
        data_step_mock.obtain.return_value = frame_mock

        calculate_assets()

        product = data_step_mock.obtain.call_args.args[0]
        self.assertEqual(product, assets_snapshot_resource(date.today()))


class AssetsSnapshotParquetFileTests(unittest.TestCase):
    def test_existing_snapshot_parquet_readable(self):
        snapshot_path = get_data_steps_root() / assets_snapshot_resource(date.today())
        if not snapshot_path.is_file():
            self.skipTest(f"Brak lokalnego snapshotu: {snapshot_path}")
        df = pd.read_parquet(snapshot_path)
        self.assertFalse(df.empty)
        self.assertIn(PORTFOLIO_VALUATION_DATE, df.columns)


if __name__ == "__main__":
    unittest.main()
