import tempfile
import unittest
from pathlib import Path

import pandas as pd

from analyse_assets.config_model import (
    CATALOG_SHEET,
    DEFAULT_TRANSACTION_SOURCE,
    MANUAL_SHEET,
    RULES_SHEET,
    AnalyseAssetsCatalog,
    AnalyseAssetsManual,
    AnalyseAssetsRules,
)
from roi.config import read_analyse_config


class AnalyseConfigSourceTests(unittest.TestCase):
    def _write_config(self, catalog: pd.DataFrame, rules: pd.DataFrame, manual: pd.DataFrame) -> Path:
        path = Path(tempfile.mkdtemp()) / "analyse_assets_config.xlsx"
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            catalog.to_excel(writer, sheet_name=CATALOG_SHEET, index=False)
            rules.to_excel(writer, sheet_name=RULES_SHEET, index=False)
            manual.to_excel(writer, sheet_name=MANUAL_SHEET, index=False)
        return path

    def test_missing_catalog_source_filled_with_default(self):
        catalog = pd.DataFrame(
            [
                {
                    AnalyseAssetsCatalog.ASSET_ID: "aquamarina",
                    AnalyseAssetsCatalog.OUTPUT_FILE: "mbank_aquamarina.xlsx",
                    AnalyseAssetsCatalog.ORDER: 1,
                    AnalyseAssetsCatalog.ENABLED: 1,
                    AnalyseAssetsCatalog.PROPERTIES_ID: "aquamarina",
                }
            ]
        )
        rules = pd.DataFrame(
            [
                {
                    AnalyseAssetsRules.ASSET_ID: "aquamarina",
                    AnalyseAssetsRules.STEP_ID: "r0",
                    AnalyseAssetsRules.STEP_ORDER: 0,
                    AnalyseAssetsRules.MAPPING: "initial_investment",
                    AnalyseAssetsRules.CONDITION_GROUP: 1,
                    AnalyseAssetsRules.FIELD: "MBANK_TITLE",
                    AnalyseAssetsRules.OPERATOR: "contains",
                    AnalyseAssetsRules.VALUE: "X",
                    AnalyseAssetsRules.UWAGI: "",
                }
            ]
        )
        manual = pd.DataFrame(columns=list(AnalyseAssetsManual.expected_columns()))
        path = self._write_config(catalog, rules, manual)

        config = read_analyse_config(path)
        self.assertEqual(
            config["catalog"].iloc[0][AnalyseAssetsCatalog.SOURCE],
            DEFAULT_TRANSACTION_SOURCE,
        )
        self.assertEqual(config["rules"].iloc[0][AnalyseAssetsRules.SOURCE], "")

    def test_blank_rule_source_stays_blank_for_inherit(self):
        catalog = pd.DataFrame(
            [
                {
                    AnalyseAssetsCatalog.ASSET_ID: "aquamarina",
                    AnalyseAssetsCatalog.OUTPUT_FILE: "mbank_aquamarina.xlsx",
                    AnalyseAssetsCatalog.ORDER: 1,
                    AnalyseAssetsCatalog.ENABLED: 1,
                    AnalyseAssetsCatalog.PROPERTIES_ID: "aquamarina",
                    AnalyseAssetsCatalog.SOURCE: DEFAULT_TRANSACTION_SOURCE,
                }
            ]
        )
        rules = pd.DataFrame(
            [
                {
                    AnalyseAssetsRules.ASSET_ID: "aquamarina",
                    AnalyseAssetsRules.STEP_ID: "r0",
                    AnalyseAssetsRules.STEP_ORDER: 0,
                    AnalyseAssetsRules.MAPPING: "initial_investment",
                    AnalyseAssetsRules.CONDITION_GROUP: 1,
                    AnalyseAssetsRules.FIELD: "MBANK_TITLE",
                    AnalyseAssetsRules.OPERATOR: "contains",
                    AnalyseAssetsRules.VALUE: "X",
                    AnalyseAssetsRules.UWAGI: "",
                    AnalyseAssetsRules.SOURCE: None,
                }
            ]
        )
        manual = pd.DataFrame(columns=list(AnalyseAssetsManual.expected_columns()))
        path = self._write_config(catalog, rules, manual)

        config = read_analyse_config(path)
        self.assertEqual(config["rules"].iloc[0][AnalyseAssetsRules.SOURCE], "")

    def test_legacy_source_column_renamed_to_pool_id(self):
        catalog = pd.DataFrame(
            [
                {
                    "asset_id": "aquamarina",
                    "output_file": "mbank_aquamarina.xlsx",
                    "order": 1,
                    "enabled": 1,
                    "properties_id": "aquamarina",
                    "source": DEFAULT_TRANSACTION_SOURCE,
                }
            ]
        )
        rules = pd.DataFrame(
            [
                {
                    "asset_id": "aquamarina",
                    "step_id": "r0",
                    "step_order": 0,
                    "mapping": "initial_investment",
                    "condition_group": 1,
                    "field": "MBANK_TITLE",
                    "operator": "contains",
                    "value": "X",
                    "Uwagi": "",
                    "source": "",
                }
            ]
        )
        manual = pd.DataFrame(columns=list(AnalyseAssetsManual.expected_columns()))
        path = self._write_config(catalog, rules, manual)

        config = read_analyse_config(path)
        self.assertIn(AnalyseAssetsCatalog.POOL_ID, config["catalog"].columns)
        self.assertNotIn("source", config["catalog"].columns)
        self.assertEqual(
            config["catalog"].iloc[0][AnalyseAssetsCatalog.POOL_ID],
            DEFAULT_TRANSACTION_SOURCE,
        )
        self.assertIn(AnalyseAssetsRules.POOL_ID, config["rules"].columns)


if __name__ == "__main__":
    unittest.main()

