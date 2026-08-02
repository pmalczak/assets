import tempfile
import unittest
from pathlib import Path

import pandas as pd

from analyse_assets.config_model import (
    CATALOG_SHEET,
    DEFAULT_POOL_ID,
    MANUAL_SHEET,
    RULES_SHEET,
    AnalyseAssetsCatalog,
    AnalyseAssetsManual,
    AnalyseAssetsRules,
)
from roi.config import read_analyse_config


class AnalyseConfigPoolIdTests(unittest.TestCase):
    def _write_config(self, catalog: pd.DataFrame, rules: pd.DataFrame, manual: pd.DataFrame) -> Path:
        path = Path(tempfile.mkdtemp()) / "a_config.xlsx"
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            catalog.to_excel(writer, sheet_name=CATALOG_SHEET, index=False)
            rules.to_excel(writer, sheet_name=RULES_SHEET, index=False)
            manual.to_excel(writer, sheet_name=MANUAL_SHEET, index=False)
        return path

    def test_blank_catalog_pool_id_filled_with_default(self):
        catalog = pd.DataFrame(
            [
                {
                    AnalyseAssetsCatalog.ASSET_ID: "aquamarina",
                    AnalyseAssetsCatalog.OUTPUT_FILE: "mbank_aquamarina.xlsx",
                    AnalyseAssetsCatalog.ORDER: 1,
                    AnalyseAssetsCatalog.ENABLED: 1,
                    AnalyseAssetsCatalog.POOL_ID: "",
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
                    AnalyseAssetsRules.FIELD: "TITLE",
                    AnalyseAssetsRules.OPERATOR: "contains",
                    AnalyseAssetsRules.VALUE: "X",
                    AnalyseAssetsRules.UWAGI: "",
                    AnalyseAssetsRules.POOL_ID: "",
                }
            ]
        )
        manual = pd.DataFrame(columns=list(AnalyseAssetsManual.expected_columns()))
        path = self._write_config(catalog, rules, manual)

        config = read_analyse_config(path)
        self.assertEqual(
            config["catalog"].iloc[0][AnalyseAssetsCatalog.POOL_ID],
            DEFAULT_POOL_ID,
        )
        self.assertEqual(config["rules"].iloc[0][AnalyseAssetsRules.POOL_ID], "")

    def test_blank_rule_pool_id_stays_blank_for_inherit(self):
        catalog = pd.DataFrame(
            [
                {
                    AnalyseAssetsCatalog.ASSET_ID: "aquamarina",
                    AnalyseAssetsCatalog.OUTPUT_FILE: "mbank_aquamarina.xlsx",
                    AnalyseAssetsCatalog.ORDER: 1,
                    AnalyseAssetsCatalog.ENABLED: 1,
                    AnalyseAssetsCatalog.POOL_ID: DEFAULT_POOL_ID,
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
                    AnalyseAssetsRules.FIELD: "TITLE",
                    AnalyseAssetsRules.OPERATOR: "contains",
                    AnalyseAssetsRules.VALUE: "X",
                    AnalyseAssetsRules.UWAGI: "",
                    AnalyseAssetsRules.POOL_ID: None,
                }
            ]
        )
        manual = pd.DataFrame(columns=list(AnalyseAssetsManual.expected_columns()))
        path = self._write_config(catalog, rules, manual)

        config = read_analyse_config(path)
        self.assertEqual(config["rules"].iloc[0][AnalyseAssetsRules.POOL_ID], "")

    def test_legacy_source_column_is_rejected(self):
        catalog = pd.DataFrame(
            [
                {
                    "asset_id": "aquamarina",
                    "output_file": "mbank_aquamarina.xlsx",
                    "order": 1,
                    "enabled": 1,
                    "source": DEFAULT_POOL_ID,
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
                    "field": "TITLE",
                    "operator": "contains",
                    "value": "X",
                    "Uwagi": "",
                    "source": "",
                }
            ]
        )
        manual = pd.DataFrame(columns=list(AnalyseAssetsManual.expected_columns()))
        path = self._write_config(catalog, rules, manual)

        with self.assertRaises(Exception):
            read_analyse_config(path)


if __name__ == "__main__":
    unittest.main()
