import unittest
from datetime import date

import pandas as pd

from importers.assets.data_model import OperationDomain, PropertyValuations
from roi.categories import CLOSING, INVESTMENT, OUTFLOW
from roi.compute_roi import compute_roi
from roi.data_model import CashFlowEvent


def _kiemliczow_1_events() -> pd.DataFrame:
    rows = [
        ("kiemliczow_1", "1997-06-02", -48600.0, INVESTMENT, "manual", "zakup mieszkania"),
        ("kiemliczow_1", "2000-01-03", 156600.0, CLOSING, "manual", "sprzedaż"),
        ("kiemliczow_1", "2000-04-04", -3700.0, OUTFLOW, "manual", "opłata skarbowa"),
        ("kiemliczow_1", "2000-04-04", -695.5, OUTFLOW, "manual", "prowizja"),
        ("kiemliczow_1", "2001-08-20", -572.5, OUTFLOW, "manual", "hipoteka - opłata sądowa"),
        ("kiemliczow_1", "2001-10-05", -145.0, OUTFLOW, "manual", "hipoteka - opłata sądowa"),
    ]
    df = pd.DataFrame(rows, columns=list(CashFlowEvent.COLUMN_ORDER))
    CashFlowEvent.check_structure(df)
    return df


def _open_property_sheet(asset_id: str, value: float, valuation: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                PropertyValuations.ID: asset_id,
                PropertyValuations.DATE: valuation,
                PropertyValuations.VALUE: value,
                PropertyValuations.CURRENCY: "PLN",
                PropertyValuations.SIZE: 50,
                PropertyValuations.OPERATION: OperationDomain.EVALUATION,
                PropertyValuations.UNIT_PRICE: value / 50,
            }
        ]
    )


class ComputeRoiTests(unittest.TestCase):
    def test_sold_property_roi_is_sum_of_realized_cashflows(self):
        events = _kiemliczow_1_events()
        summary = compute_roi("kiemliczow_1", events, None, date(2026, 1, 1))

        self.assertTrue(summary.is_sold)
        self.assertEqual(summary.terminal_realized, 156600.0)
        self.assertEqual(summary.terminal_unrealized, 0.0)
        self.assertEqual(summary.roi_nominal, 102887.0)

    def test_open_property_adds_unrealized_terminal_from_properties(self):
        events = pd.DataFrame(
            [
                {
                    CashFlowEvent.ASSET_ID: "kiemliczow_3",
                    CashFlowEvent.DATE: "2012-05-28",
                    CashFlowEvent.AMOUNT: -7290.0,
                    CashFlowEvent.CATEGORY: OUTFLOW,
                    CashFlowEvent.SOURCE: "manual",
                    CashFlowEvent.DESCRIPTION: "notarial",
                }
            ]
        )
        props = _open_property_sheet("kiemliczow_3", 450000.0, "2024-06-01")
        summary = compute_roi("kiemliczow_3", events, props, date(2026, 1, 1))

        self.assertFalse(summary.is_sold)
        self.assertEqual(summary.terminal_unrealized, 450000.0)
        self.assertEqual(summary.roi_nominal, 442710.0)

    def test_valuation_date_filters_future_cashflows(self):
        events = _kiemliczow_1_events()
        summary = compute_roi("kiemliczow_1", events, None, date(1999, 12, 31))

        self.assertFalse(summary.is_sold)
        self.assertEqual(summary.capex, -48600.0)
        self.assertEqual(summary.terminal_realized, 0.0)
        self.assertEqual(summary.roi_nominal, -48600.0)


class ManualAllocationTests(unittest.TestCase):
    def test_manual_part_builds_valid_events(self):
        from analyse_assets.config_model import AnalyseAssetsManual, AnalyseAssetsRules
        from roi.allocate import allocate_asset_from_mbank_pool

        manual = pd.DataFrame(
            [
                {
                    AnalyseAssetsManual.ASSET_ID: "kiemliczow_1",
                    AnalyseAssetsManual.STEP_ORDER: 0,
                    AnalyseAssetsManual.DATE: "1997-06-02",
                    AnalyseAssetsManual.AMOUNT: -48600.0,
                    AnalyseAssetsManual.CATEGORY: "INVESTMENT",
                    AnalyseAssetsManual.DESCRIPTION: "zakup",
                }
            ]
        )
        rules = pd.DataFrame(columns=list(AnalyseAssetsRules.expected_columns()))
        _remaining, events = allocate_asset_from_mbank_pool(
            pd.DataFrame(),
            "kiemliczow_1",
            rules,
            manual,
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events.iloc[0][CashFlowEvent.CATEGORY], INVESTMENT)


class BuildSelectorTests(unittest.TestCase):
    def test_blank_rule_conditions_are_ignored(self):
        from analyse_assets.build_selector import build_step_selector
        from analyse_assets.config_model import AnalyseAssetsRules
        from analyse_assets.data_model import AssetRw

        df = AssetRw.create(
            [
                ("2020-01-01", -100.0, AssetRw.CAT_INVESTMENT, "test"),
            ]
        )
        df[AssetRw.MBANK_TITLE] = "UMOWA NR AQ/2014/252/180 LOKAL 180"
        step_rules = pd.DataFrame(
            [
                {
                    AnalyseAssetsRules.ASSET_ID: "aquamarina",
                    AnalyseAssetsRules.STEP_ID: "r0",
                    AnalyseAssetsRules.STEP_ORDER: 0,
                    AnalyseAssetsRules.MAPPING: "initial_investment",
                    AnalyseAssetsRules.CONDITION_GROUP: 1,
                    AnalyseAssetsRules.FIELD: float("nan"),
                    AnalyseAssetsRules.OPERATOR: float("nan"),
                    AnalyseAssetsRules.VALUE: float("nan"),
                },
                {
                    AnalyseAssetsRules.ASSET_ID: "aquamarina",
                    AnalyseAssetsRules.STEP_ID: "r0",
                    AnalyseAssetsRules.STEP_ORDER: 0,
                    AnalyseAssetsRules.MAPPING: "initial_investment",
                    AnalyseAssetsRules.CONDITION_GROUP: 2,
                    AnalyseAssetsRules.FIELD: "MBANK_TITLE",
                    AnalyseAssetsRules.OPERATOR: "contains",
                    AnalyseAssetsRules.VALUE: "UMOWA NR AQ/2014/252/180 LOKAL 180",
                },
            ]
        )

        selector = build_step_selector(df, step_rules)
        self.assertTrue(selector.iloc[0])

    def test_drop_incomplete_rules_removes_blank_rows(self):
        from analyse_assets.config_model import AnalyseAssetsRules
        from roi.config import _drop_incomplete_rules

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
                    AnalyseAssetsRules.VALUE: "test",
                },
                {
                    AnalyseAssetsRules.ASSET_ID: "aquamarina",
                    AnalyseAssetsRules.STEP_ID: "r0",
                    AnalyseAssetsRules.STEP_ORDER: 0,
                    AnalyseAssetsRules.MAPPING: "initial_investment",
                    AnalyseAssetsRules.CONDITION_GROUP: 1,
                    AnalyseAssetsRules.FIELD: float("nan"),
                    AnalyseAssetsRules.OPERATOR: float("nan"),
                    AnalyseAssetsRules.VALUE: float("nan"),
                },
            ]
        )

        filtered = _drop_incomplete_rules(rules)
        self.assertEqual(len(filtered), 1)
