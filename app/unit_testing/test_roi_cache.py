import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

from analyse_assets.data_model import AssetRw
from importers.mbank.data_model import MBankFile
from roi.data_model import CashFlowEvent
from roi.roi_products import (
    add_mbank_consolidated_ymd_columns,
    load_catalog_events,
    roi_catalog_resource,
)


class LoadCatalogEventsTests(unittest.TestCase):
    @patch("roi.roi_products.DATA_STEP")
    @patch("roi.roi_products.get_config_file")
    @patch("roi.roi_products.read_analyse_config")
    def test_load_catalog_events_uses_obtain_dependent(
        self,
        read_config_mock,
        get_config_file_mock,
        data_step_mock,
    ):
        assets_date = date(2026, 7, 16)
        catalog = pd.DataFrame([{"asset_id": "kiemliczow_1", "enabled": True, "order": 1}])
        config = {"catalog": catalog, "rules": pd.DataFrame(), "manual": pd.DataFrame()}
        read_config_mock.return_value = config
        get_config_file_mock.return_value = Path("analyse_assets_config.xlsx")

        all_events = pd.DataFrame(
            [
                {
                    CashFlowEvent.ASSET_ID: "kiemliczow_1",
                    CashFlowEvent.DATE: "2026-01-01",
                    CashFlowEvent.AMOUNT: -100.0,
                    CashFlowEvent.CATEGORY: "INVESTMENT",
                    CashFlowEvent.SOURCE: "manual",
                    CashFlowEvent.DESCRIPTION: "test",
                    CashFlowEvent.TITLE: "",
                    CashFlowEvent.COUNTERPARTY: "",
                    CashFlowEvent.ACCOUNT_NUMBER: "",
                }
            ]
        )
        frame_mock = MagicMock()
        frame_mock.data_frame.return_value = all_events
        data_step_mock.obtain_dependent.return_value = frame_mock

        result = load_catalog_events(assets_date, config)

        data_step_mock.obtain_dependent.assert_called_once()
        data_step_mock.init_steps.assert_not_called()
        args, kwargs = data_step_mock.obtain_dependent.call_args
        self.assertEqual(args[0], roi_catalog_resource(assets_date))
        self.assertEqual(args[2], Path("analyse_assets_config.xlsx"))
        self.assertEqual(kwargs["assets_date"], assets_date)
        self.assertIn("kiemliczow_1", result)
        self.assertEqual(len(result["kiemliczow_1"]), 1)

    def test_roi_catalog_resource_includes_date(self):
        self.assertEqual(
            roi_catalog_resource(date(2026, 7, 16)),
            "10 roi/2026-07-16/_catalog.parquet",
        )


class MbankConsolidatedYmdTests(unittest.TestCase):
    def test_add_mbank_consolidated_ymd_columns(self):
        df = pd.DataFrame(
            {
                MBankFile.MBANK_TRANSACTION_DATE: ["2024-03-15", "2025-11-01"],
                MBankFile.MBANK_AMOUNT: [-100.0, 200.0],
            }
        )
        result = add_mbank_consolidated_ymd_columns(df)

        self.assertEqual(result.loc[0, AssetRw.YEAR], "2024")
        self.assertEqual(result.loc[0, AssetRw.MONTH], "3")
        self.assertEqual(result.loc[0, AssetRw.DAY], "15")
        self.assertEqual(result.loc[1, AssetRw.YEAR], "2025")
        self.assertEqual(result.loc[1, AssetRw.MONTH], "11")
        self.assertEqual(result.loc[1, AssetRw.DAY], "1")
        self.assertNotIn("MIESIĄC", result.columns)
        self.assertNotIn("DZIEŃ", result.columns)

    def test_add_mbank_consolidated_ymd_columns_is_idempotent(self):
        df = add_mbank_consolidated_ymd_columns(
            pd.DataFrame({MBankFile.MBANK_TRANSACTION_DATE: ["2024-01-02"]})
        )
        again = add_mbank_consolidated_ymd_columns(df)
        pd.testing.assert_frame_equal(df, again)

    def test_replaces_legacy_diacritic_columns(self):
        df = pd.DataFrame(
            {
                MBankFile.MBANK_TRANSACTION_DATE: ["2024-03-15"],
                "ROK": [2024],
                "MIESIĄC": [3],
                "DZIEŃ": [15],
            }
        )
        result = add_mbank_consolidated_ymd_columns(df)
        self.assertEqual(result.loc[0, AssetRw.YEAR], "2024")
        self.assertEqual(result.loc[0, AssetRw.MONTH], "3")
        self.assertEqual(result.loc[0, AssetRw.DAY], "15")
        self.assertNotIn("MIESIĄC", result.columns)
        self.assertNotIn("DZIEŃ", result.columns)


if __name__ == "__main__":
    unittest.main()
