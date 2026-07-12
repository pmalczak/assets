import unittest
from datetime import date

import pandas as pd

from importers.assets.data_model import OperationDomain, Properties
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
                Properties.ID: asset_id,
                Properties.DATE: valuation,
                Properties.VALUE: value,
                Properties.CURRENCY: "PLN",
                Properties.SIZE: 50,
                Properties.OPERATION: OperationDomain.EVALUATION,
                Properties.UNIT_PRICE: value / 50,
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
