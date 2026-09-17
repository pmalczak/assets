# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import patch

import pandas as pd

from app_streamlit.render_roi import (
    ROI_CALCULATION_DATE_LABEL,
    ROI_EVALUATION_DATE_LABEL,
    _format_roi_summary_display,
    _prepare_flow_display,
    _roi_calculation_date_input,
)
from importers.assets.data_model import AssetsDef
from roi.data_model import CashFlowEvent


class RoiFlowDisplayTests(unittest.TestCase):
    def test_flows_are_newest_first(self):
        events = pd.DataFrame(
            [
                {
                    CashFlowEvent.DATE: "2024-01-01",
                    CashFlowEvent.AMOUNT: 1,
                    CashFlowEvent.CATEGORY: "CAPEX",
                },
                {
                    CashFlowEvent.DATE: "2026-08-01",
                    CashFlowEvent.AMOUNT: 2,
                    CashFlowEvent.CATEGORY: "REVENUES",
                },
                {
                    CashFlowEvent.DATE: "2025-06-15",
                    CashFlowEvent.AMOUNT: 3,
                    CashFlowEvent.CATEGORY: "OPEX",
                },
            ]
        )
        display = _prepare_flow_display(events, date(2026, 8, 30))
        dates = pd.to_datetime(display["Data"]).dt.date.tolist()
        self.assertEqual(dates, [date(2026, 8, 1), date(2025, 6, 15), date(2024, 1, 1)])

    def test_flows_after_valuation_date_are_dropped(self):
        events = pd.DataFrame(
            [
                {CashFlowEvent.DATE: "2026-01-01", CashFlowEvent.AMOUNT: 1},
                {CashFlowEvent.DATE: "2026-12-31", CashFlowEvent.AMOUNT: 2},
            ]
        )
        display = _prepare_flow_display(events, date(2026, 6, 1))
        dates = pd.to_datetime(display["Data"]).dt.date.tolist()
        self.assertEqual(dates, [date(2026, 1, 1)])


class RoiCalculationDateInputTests(unittest.TestCase):
    @patch("app_streamlit.render_roi.st.date_input")
    def test_uses_shared_calculation_date_label_and_preserves_widget_key(
        self, date_input
    ):
        selected = date(2026, 9, 17)
        date_input.return_value = selected

        result = _roi_calculation_date_input(
            date(2026, 9, 16),
            key="roi_degiro_valuation_date",
        )

        self.assertEqual(result, selected)
        date_input.assert_called_once_with(
            ROI_CALCULATION_DATE_LABEL,
            value=date(2026, 9, 16),
            key="roi_degiro_valuation_date",
        )
        self.assertEqual(ROI_CALCULATION_DATE_LABEL, "Data obliczenia ROI")


class RoiSummaryDisplayTests(unittest.TestCase):
    def test_evaluation_date_follows_unrealized_terminal(self):
        summary = pd.DataFrame(
            [
                {
                    "asset_id": "p_xtb:A",
                    "capex": -10,
                    "opex": 0,
                    "revenue": 0,
                    "terminal_realized": 0,
                    "terminal_unrealized": 12,
                    AssetsDef.EVALUATION_DATE: "2026-08-20",
                    "roi_nominal": 2,
                    "xirr": None,
                    "is_sold": False,
                    "warnings": "",
                }
            ]
        )
        display = _format_roi_summary_display(summary)
        cols = list(display.columns)
        self.assertEqual(
            cols[cols.index("Wycena (nerealiz.)") : cols.index("ROI nominal") + 1],
            ["Wycena (nerealiz.)", ROI_EVALUATION_DATE_LABEL, "ROI nominal"],
        )
        self.assertEqual(display[ROI_EVALUATION_DATE_LABEL].iloc[0], "2026-08-20")

    def test_catalog_shows_evaluation_date_after_unrealized_terminal(self):
        summary = pd.DataFrame(
            [
                {
                    "asset_id": "cash",
                    "capex": -10,
                    "opex": 0,
                    "revenue": 0,
                    "terminal_realized": 0,
                    "terminal_unrealized": 10,
                    AssetsDef.EVALUATION_DATE: "2026-01-01",
                    "roi_nominal": 0,
                    "xirr": None,
                    "is_sold": False,
                    "warnings": "",
                }
            ]
        )
        display = _format_roi_summary_display(summary)
        cols = list(display.columns)
        self.assertEqual(
            cols[cols.index("Wycena (nerealiz.)") : cols.index("ROI nominal") + 1],
            ["Wycena (nerealiz.)", ROI_EVALUATION_DATE_LABEL, "ROI nominal"],
        )
        self.assertEqual(display[ROI_EVALUATION_DATE_LABEL].iloc[0], "2026-01-01")


if __name__ == "__main__":
    unittest.main()
