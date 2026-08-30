# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest
from datetime import date

import pandas as pd

from app_streamlit.render_roi import _prepare_flow_display
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


if __name__ == "__main__":
    unittest.main()
