import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

from roi.cache import ROI_CATALOG_RESOURCE, load_catalog_events
from roi.data_model import CashFlowEvent


class LoadCatalogEventsTests(unittest.TestCase):
    @patch("roi.cache.DATA_STEP")
    @patch("roi.cache._init_data_step")
    @patch("roi.cache.get_config_file")
    @patch("roi.cache.read_analyse_config")
    def test_load_catalog_events_uses_obtain_dependent(
        self,
        read_config_mock,
        get_config_file_mock,
        init_mock,
        data_step_mock,
    ):
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

        result = load_catalog_events(config, use_cache=True)

        data_step_mock.obtain_dependent.assert_called_once()
        args, kwargs = data_step_mock.obtain_dependent.call_args
        self.assertEqual(args[0], ROI_CATALOG_RESOURCE)
        self.assertEqual(args[2], Path("analyse_assets_config.xlsx"))
        self.assertIn("kiemliczow_1", result)
        self.assertEqual(len(result["kiemliczow_1"]), 1)

    @patch("roi.cache._build_allocation")
    @patch("roi.cache.read_analyse_config")
    def test_load_catalog_events_without_cache_skips_data_step(
        self,
        read_config_mock,
        build_allocation_mock,
    ):
        catalog = pd.DataFrame([{"asset_id": "kiemliczow_1", "enabled": True, "order": 1}])
        config = {"catalog": catalog, "rules": pd.DataFrame(), "manual": pd.DataFrame()}
        read_config_mock.return_value = config
        events = pd.DataFrame(columns=list(CashFlowEvent.COLUMN_ORDER))
        build_allocation_mock.return_value = ({"kiemliczow_1": events}, pd.DataFrame())

        result = load_catalog_events(config, use_cache=False)

        build_allocation_mock.assert_called_once_with(config)
        self.assertEqual(result, {"kiemliczow_1": events})


if __name__ == "__main__":
    unittest.main()
