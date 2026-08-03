import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

from analyse_assets.account_tx import AccountTx
from analyse_assets.config_model import AnalyseAssetsCatalog
from analyse_assets.data_model import AssetRw
from app_proc.export_product_excel import (
    export_roi_product_excels,
    unallocated_excel_filename,
)
from importers.mbank.data_model import MBankFile
from roi.data_model import CashFlowEvent
from roi.roi_products import (
    add_mbank_consolidated_ymd_columns,
    load_catalog_events,
    load_roi_summary,
    roi_catalog_resource,
    roi_summary_resource,
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
        get_config_file_mock.return_value = Path("a_config.xlsx")

        all_events = pd.DataFrame(
            [
                {
                    CashFlowEvent.ASSET_ID: "kiemliczow_1",
                    CashFlowEvent.DATE: "2026-01-01",
                    CashFlowEvent.AMOUNT: -100.0,
                    CashFlowEvent.CATEGORY: "CAPEX",
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
        self.assertEqual(args[2], Path("a_config.xlsx"))
        self.assertEqual(kwargs["assets_date"], assets_date)
        self.assertIn("kiemliczow_1", result)
        self.assertEqual(len(result["kiemliczow_1"]), 1)

    def test_roi_catalog_resource_includes_date(self):
        self.assertEqual(
            roi_catalog_resource(date(2026, 7, 16)),
            "10 roi/2026-07-16/_catalog.parquet",
        )


class LoadRoiSummaryTests(unittest.TestCase):
    @patch("roi.roi_products.DATA_STEP")
    @patch("roi.roi_products.get_config_file")
    @patch("roi.roi_products.read_analyse_config")
    def test_load_roi_summary_uses_obtain_dependent(
        self,
        read_config_mock,
        get_config_file_mock,
        data_step_mock,
    ):
        assets_date = date(2026, 7, 16)
        catalog = pd.DataFrame([{"asset_id": "kiemliczow_1", "enabled": True, "order": 1}])
        config = {"catalog": catalog, "rules": pd.DataFrame(), "manual": pd.DataFrame()}
        read_config_mock.return_value = config
        get_config_file_mock.return_value = Path("a_config.xlsx")

        summary = pd.DataFrame(
            [{"asset_id": "kiemliczow_1", "roi_nominal": 100, "xirr": 0.1, "is_sold": False}]
        )
        frame_mock = MagicMock()
        frame_mock.data_frame.return_value = summary
        data_step_mock.obtain_dependent.return_value = frame_mock

        result = load_roi_summary(assets_date, config)

        data_step_mock.obtain_dependent.assert_called_once()
        args, kwargs = data_step_mock.obtain_dependent.call_args
        self.assertEqual(args[0], roi_summary_resource(assets_date))
        self.assertEqual(kwargs["assets_date"], assets_date)
        self.assertEqual(len(result), 1)
        self.assertEqual(result.loc[0, "asset_id"], "kiemliczow_1")

    def test_roi_summary_resource_includes_date(self):
        self.assertEqual(
            roi_summary_resource(date(2026, 7, 16)),
            "10 roi/2026-07-16/_roi_summary.parquet",
        )


class BuildCatalogEventsExportTests(unittest.TestCase):
    @patch("roi.roi_products.export_roi_product_excels")
    @patch("roi.roi_products._build_allocation")
    @patch("roi.roi_products.read_analyse_config")
    def test_build_catalog_events_exports_excel_not_unallocated_parquet(
        self,
        read_config_mock,
        build_alloc_mock,
        export_mock,
    ):
        from roi.roi_products import _build_catalog_events

        assets_date = date(2026, 7, 16)
        catalog = pd.DataFrame(
            [
                {
                    AnalyseAssetsCatalog.ASSET_ID: "kiemliczow_1",
                    AnalyseAssetsCatalog.ENABLED: True,
                    AnalyseAssetsCatalog.ORDER: 1,
                }
            ]
        )
        read_config_mock.return_value = {
            "catalog": catalog,
            "rules": pd.DataFrame(),
            "manual": pd.DataFrame(),
        }
        events = pd.DataFrame(
            [
                {
                    CashFlowEvent.ASSET_ID: "kiemliczow_1",
                    CashFlowEvent.DATE: "2026-01-01",
                    CashFlowEvent.AMOUNT: -100.0,
                    CashFlowEvent.CATEGORY: "CAPEX",
                    CashFlowEvent.SOURCE: "mbank_pln",
                    CashFlowEvent.DESCRIPTION: "test",
                    CashFlowEvent.TITLE: "",
                    CashFlowEvent.COUNTERPARTY: "",
                    CashFlowEvent.ACCOUNT_NUMBER: "",
                }
            ]
        )
        unallocated = {
            "mbank_pln": pd.DataFrame([{AccountTx.POOL_ID: "mbank_pln", AccountTx.AMOUNT: 1.0}]),
            "mbank_eur": pd.DataFrame([{AccountTx.POOL_ID: "mbank_eur", AccountTx.AMOUNT: 2.0}]),
        }
        build_alloc_mock.return_value = ({"kiemliczow_1": events}, unallocated)

        with patch("roi.roi_products.DATA_STEP") as data_step_mock:
            result = _build_catalog_events(Path("cfg.xlsx"), assets_date=assets_date)

        data_step_mock.obtain.assert_not_called()
        export_mock.assert_called_once()
        args = export_mock.call_args[0]
        self.assertEqual(args[1], unallocated)
        self.assertEqual(args[3], assets_date)
        self.assertEqual(len(result), 1)


class ExportRoiProductExcelsTests(unittest.TestCase):
    def test_writes_separate_unallocated_xlsx_per_pool(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            catalog = pd.DataFrame(
                [
                    {
                        AnalyseAssetsCatalog.ASSET_ID: "asset_a",
                        AnalyseAssetsCatalog.ENABLED: True,
                        AnalyseAssetsCatalog.ORDER: 1,
                        AnalyseAssetsCatalog.OUTPUT_FILE: "mbank_asset_a.xlsx",
                    }
                ]
            )
            events = {
                "asset_a": pd.DataFrame(
                    [{CashFlowEvent.ASSET_ID: "asset_a", CashFlowEvent.AMOUNT: -10.0}]
                )
            }
            unallocated = {
                "mbank_pln": pd.DataFrame([{AccountTx.POOL_ID: "mbank_pln", AccountTx.AMOUNT: 1.0}]),
                "mbank_eur": pd.DataFrame([{AccountTx.POOL_ID: "mbank_eur", AccountTx.AMOUNT: 2.0}]),
            }

            with patch(
                "app_proc.export_product_excel.get_online_data_output",
                return_value=out,
            ):
                export_roi_product_excels(events, unallocated, catalog, date(2026, 7, 16))

            self.assertTrue((out / "mbank_asset_a.xlsx").is_file())
            self.assertTrue((out / unallocated_excel_filename("mbank_pln")).is_file())
            self.assertTrue((out / unallocated_excel_filename("mbank_eur")).is_file())
            self.assertFalse((out / "mbank_consolidated.xlsx").exists())


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
