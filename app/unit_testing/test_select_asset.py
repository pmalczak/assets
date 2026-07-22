# -*- coding: utf-8 -*-
import unittest

import pandas as pd

from analyse_assets.config_model import AnalyseAssetsRules
from analyse_assets.data_model import AssetRw
from analyse_assets.select_asset import format_empty_selector_error, select_asset
from importers.mbank.data_model import MbankOperationType


class EmptySelectorDiagnosticsTests(unittest.TestCase):
    def test_format_includes_asset_id_field_value(self):
        step_rules = pd.DataFrame(
            [
                {
                    AnalyseAssetsRules.FIELD: "TITLE",
                    AnalyseAssetsRules.VALUE: "MENNICA",
                },
                {
                    AnalyseAssetsRules.FIELD: "AMOUNT",
                    AnalyseAssetsRules.VALUE: "-15000",
                },
            ]
        )
        msg = format_empty_selector_error(asset_id="zloto-monety", step_rules=step_rules)
        self.assertIn("Selektor nie zwrocil zadnych transakcji", msg)
        self.assertIn("asset_id='zloto-monety'", msg)
        self.assertIn("field='TITLE' value='MENNICA'", msg)
        self.assertIn("field='AMOUNT' value='-15000'", msg)

    def test_select_asset_raises_with_diagnostics(self):
        df = pd.DataFrame(
            [
                {
                    AssetRw.OPERATION_TYPE: MbankOperationType.PRZELEW_ZEWNETRZNY_WYCHODZACY,
                    AssetRw.AMOUNT: -100.0,
                    AssetRw.TITLE: "INNY",
                }
            ]
        )
        step_rules = pd.DataFrame(
            [
                {
                    AnalyseAssetsRules.FIELD: "TITLE",
                    AnalyseAssetsRules.VALUE: "MENNICA",
                }
            ]
        )
        selector = pd.Series([False], index=df.index)
        with self.assertRaises(ValueError) as ctx:
            select_asset(
                df,
                selector,
                AssetRw.initial_investment_mapping,
                asset_id="zloto-monety",
                step_rules=step_rules,
            )
        msg = str(ctx.exception)
        self.assertIn("asset_id='zloto-monety'", msg)
        self.assertIn("field='TITLE' value='MENNICA'", msg)


if __name__ == "__main__":
    unittest.main()
