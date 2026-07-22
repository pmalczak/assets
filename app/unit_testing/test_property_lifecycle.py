import unittest
from datetime import date

import pandas as pd

from analyse_assets.config_model import (
    AnalyseAssetsCatalog,
    AnalyseAssetsManual,
)
from importers.assets.data_model import OperationDomain, PropertyValuations
from importers.assets.property_lifecycle import (
    is_property_closed,
    latest_valuation_on_date,
    load_property_close_dates,
    property_ids_in_scope,
    property_valuation_history,
)


def _valuations_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                PropertyValuations.ID: "garaz",
                PropertyValuations.DATE: "2008-06-19",
                PropertyValuations.VALUE: 23000.0,
                PropertyValuations.CURRENCY: "PLN",
                PropertyValuations.SIZE: 18.9,
                PropertyValuations.OPERATION: OperationDomain.BUY,
                PropertyValuations.UNIT_PRICE: 1216.93,
            },
            {
                PropertyValuations.ID: "garaz",
                PropertyValuations.DATE: "2025-11-14",
                PropertyValuations.VALUE: 35000.0,
                PropertyValuations.CURRENCY: "PLN",
                PropertyValuations.SIZE: 18.9,
                PropertyValuations.OPERATION: OperationDomain.EVALUATION,
                PropertyValuations.UNIT_PRICE: 1851.85,
            },
            {
                PropertyValuations.ID: "rumiankowa",
                PropertyValuations.DATE: "2008-02-19",
                PropertyValuations.VALUE: 326601.45,
                PropertyValuations.CURRENCY: "PLN",
                PropertyValuations.SIZE: 54.0,
                PropertyValuations.OPERATION: OperationDomain.BUY,
                PropertyValuations.UNIT_PRICE: 6048.18,
            },
        ]
    )


def _manual_closing() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                AnalyseAssetsManual.ASSET_ID: "rumiankowa",
                AnalyseAssetsManual.STEP_ORDER: 0,
                AnalyseAssetsManual.DATE: "2015-06-01",
                AnalyseAssetsManual.AMOUNT: 400000.0,
                AnalyseAssetsManual.CATEGORY: "CLOSING",
                AnalyseAssetsManual.DESCRIPTION: "sprzedaz",
            }
        ]
    )


def _catalog() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                AnalyseAssetsCatalog.ASSET_ID: "garaz",
                AnalyseAssetsCatalog.OUTPUT_FILE: "mbank_garaz.xlsx",
                AnalyseAssetsCatalog.ORDER: 1,
                AnalyseAssetsCatalog.ENABLED: 1,
                AnalyseAssetsCatalog.PROPERTIES_ID: "garaz",
                AnalyseAssetsCatalog.POOL_ID: "mbank_pln",
            },
            {
                AnalyseAssetsCatalog.ASSET_ID: "rumiankowa",
                AnalyseAssetsCatalog.OUTPUT_FILE: "mbank_rumiankowa.xlsx",
                AnalyseAssetsCatalog.ORDER: 2,
                AnalyseAssetsCatalog.ENABLED: 1,
                AnalyseAssetsCatalog.PROPERTIES_ID: "rumiankowa",
                AnalyseAssetsCatalog.POOL_ID: "mbank_pln",
            },
        ]
    )


class PropertyLifecycleTests(unittest.TestCase):
    def test_latest_valuation_uses_last_row_on_or_before_date(self):
        valuations = _valuations_frame()
        close_dates = {}
        latest = latest_valuation_on_date(valuations, "garaz", date(2026, 1, 1), close_dates)
        self.assertIsNotNone(latest)
        value, evaluation_date = latest
        self.assertEqual(value, 35000.0)
        self.assertEqual(evaluation_date, date(2025, 11, 14))

    def test_closed_property_returns_none_after_close_date(self):
        valuations = _valuations_frame()
        close_dates = load_property_close_dates(_manual_closing(), _catalog())
        self.assertTrue(is_property_closed("rumiankowa", date(2016, 1, 1), close_dates))
        latest = latest_valuation_on_date(valuations, "rumiankowa", date(2016, 1, 1), close_dates)
        self.assertIsNone(latest)

    def test_history_adds_zero_on_close_date(self):
        valuations = _valuations_frame()
        close_dates = load_property_close_dates(_manual_closing(), _catalog())
        history = property_valuation_history(valuations, "rumiankowa", close_dates)
        close_row = history[history["date"] == pd.Timestamp("2015-06-01")]
        self.assertEqual(len(close_row), 1)
        self.assertEqual(float(close_row.iloc[0]["value"]), 0.0)

    def test_open_property_still_valued_before_close(self):
        valuations = _valuations_frame()
        close_dates = load_property_close_dates(_manual_closing(), _catalog())
        latest = latest_valuation_on_date(valuations, "rumiankowa", date(2010, 1, 1), close_dates)
        self.assertIsNotNone(latest)
        self.assertEqual(latest[0], 326601.45)

    def test_property_ids_in_scope_includes_close_dates_without_valuations(self):
        valuations = pd.DataFrame(columns=list(PropertyValuations.expected_columns()))
        close_dates = load_property_close_dates(_manual_closing(), _catalog())
        scope = property_ids_in_scope(valuations, close_dates)
        self.assertIn("rumiankowa", scope)


if __name__ == "__main__":
    unittest.main()
