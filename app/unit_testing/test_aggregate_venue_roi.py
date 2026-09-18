# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest
from datetime import date

import pandas as pd

from importers.assets.data_model import AssetsDef
from roi.aggregate_venue_roi import VENUE_TOTAL_ASSET_ID, aggregate_venue_roi
from roi.categories import CAPEX, DIVESTMENT
from roi.data_model import CashFlowEvent
from roi.xirr import compute_xirr


def _cf(asset_id: str, day: str, amount: float, category: str = CAPEX) -> dict:
    return {
        CashFlowEvent.ASSET_ID: asset_id,
        CashFlowEvent.DATE: day,
        CashFlowEvent.AMOUNT: amount,
        CashFlowEvent.CATEGORY: category,
        CashFlowEvent.SOURCE: "",
        CashFlowEvent.DESCRIPTION: "",
        CashFlowEvent.TITLE: "",
        CashFlowEvent.COUNTERPARTY: "",
        CashFlowEvent.ACCOUNT_NUMBER: "",
    }


def _summary_row(
    asset_id: str,
    *,
    capex: float,
    terminal_unrealized: float,
    roi_nominal: float,
    xirr: float | None,
    is_sold: bool,
    evaluation_date: str,
    opex: float = 0.0,
    revenue: float = 0.0,
    terminal_realized: float = 0.0,
) -> dict:
    return {
        "asset_id": asset_id,
        "capex": capex,
        "opex": opex,
        "revenue": revenue,
        "terminal_realized": terminal_realized,
        "terminal_unrealized": terminal_unrealized,
        AssetsDef.EVALUATION_DATE: evaluation_date,
        "roi_nominal": roi_nominal,
        "xirr": xirr,
        "is_sold": is_sold,
        "warnings": "",
    }


class AggregateVenueRoiTests(unittest.TestCase):
    def test_sums_money_and_xirr_is_not_average_of_rows(self):
        # Różne CAPEX przy tej samej dacie: średnia XIRR ≠ XIRR zagregowanego CF.
        # A: -100 → 110 (~10%); B: -1000 → 1010 (~1%); średnia ~5.5%, portfel ~1.9%.
        valuation = date(2025, 1, 1)
        summary = pd.DataFrame(
            [
                _summary_row(
                    "a",
                    capex=-100,
                    terminal_unrealized=110,
                    roi_nominal=10,
                    xirr=0.10,
                    is_sold=False,
                    evaluation_date="2025-01-01",
                ),
                _summary_row(
                    "b",
                    capex=-1000,
                    terminal_unrealized=1010,
                    roi_nominal=10,
                    xirr=0.01,
                    is_sold=False,
                    evaluation_date="2025-01-01",
                ),
            ]
        )
        events = {
            "a": pd.DataFrame([_cf("a", "2024-01-01", -100)]),
            "b": pd.DataFrame([_cf("b", "2024-01-01", -1000)]),
        }

        total = aggregate_venue_roi(summary, events, valuation)
        self.assertEqual(len(total), 1)
        self.assertEqual(total["asset_id"].iloc[0], VENUE_TOTAL_ASSET_ID)
        self.assertEqual(int(total["capex"].iloc[0]), -1100)
        self.assertEqual(int(total["terminal_unrealized"].iloc[0]), 1120)
        self.assertEqual(int(total["roi_nominal"].iloc[0]), 20)

        row_avg = (0.10 + 0.01) / 2
        venue_xirr = total["xirr"].iloc[0]
        self.assertIsNotNone(venue_xirr)
        self.assertNotAlmostEqual(float(venue_xirr), row_avg, places=2)

        expected = compute_xirr(
            [date(2024, 1, 1), date(2025, 1, 1)],
            [-1100.0, 1120.0],
        )
        self.assertAlmostEqual(float(venue_xirr), float(expected), places=5)

    def test_only_visible_asset_ids_enter_aggregate(self):
        valuation = date(2025, 1, 1)
        summary = pd.DataFrame(
            [
                _summary_row(
                    "a",
                    capex=-100,
                    terminal_unrealized=110,
                    roi_nominal=10,
                    xirr=0.10,
                    is_sold=False,
                    evaluation_date="2025-01-01",
                ),
            ]
        )
        events = {
            "a": pd.DataFrame([_cf("a", "2024-01-01", -100)]),
            "hidden": pd.DataFrame([_cf("hidden", "2024-01-01", -1000)]),
        }
        total = aggregate_venue_roi(summary, events, valuation)
        self.assertEqual(int(total["capex"].iloc[0]), -100)
        self.assertEqual(int(total["terminal_unrealized"].iloc[0]), 110)

    def test_is_sold_true_only_when_all_rows_sold(self):
        valuation = date(2025, 6, 1)
        summary = pd.DataFrame(
            [
                _summary_row(
                    "a",
                    capex=-100,
                    terminal_unrealized=0,
                    terminal_realized=105,
                    roi_nominal=5,
                    xirr=0.05,
                    is_sold=True,
                    evaluation_date="2025-01-01",
                ),
                _summary_row(
                    "b",
                    capex=-50,
                    terminal_unrealized=0,
                    terminal_realized=55,
                    roi_nominal=5,
                    xirr=0.05,
                    is_sold=True,
                    evaluation_date="2025-02-01",
                ),
            ]
        )
        events = {
            "a": pd.DataFrame(
                [
                    _cf("a", "2024-01-01", -100),
                    _cf("a", "2025-01-01", 105, DIVESTMENT),
                ]
            ),
            "b": pd.DataFrame(
                [
                    _cf("b", "2024-01-01", -50),
                    _cf("b", "2025-02-01", 55, DIVESTMENT),
                ]
            ),
        }
        total = aggregate_venue_roi(summary, events, valuation)
        self.assertTrue(bool(total["is_sold"].iloc[0]))

        summary.loc[1, "is_sold"] = False
        mixed = aggregate_venue_roi(summary, events, valuation)
        self.assertFalse(bool(mixed["is_sold"].iloc[0]))

    def test_evaluation_date_is_min_of_rows(self):
        valuation = date(2026, 9, 1)
        summary = pd.DataFrame(
            [
                _summary_row(
                    "a",
                    capex=-10,
                    terminal_unrealized=11,
                    roi_nominal=1,
                    xirr=None,
                    is_sold=False,
                    evaluation_date="2026-08-20",
                ),
                _summary_row(
                    "b",
                    capex=-10,
                    terminal_unrealized=12,
                    roi_nominal=2,
                    xirr=None,
                    is_sold=False,
                    evaluation_date="2026-07-01",
                ),
                _summary_row(
                    "c",
                    capex=-10,
                    terminal_unrealized=13,
                    roi_nominal=3,
                    xirr=None,
                    is_sold=False,
                    evaluation_date="",
                ),
            ]
        )
        events = {
            "a": pd.DataFrame([_cf("a", "2025-01-01", -10)]),
            "b": pd.DataFrame([_cf("b", "2025-01-01", -10)]),
            "c": pd.DataFrame([_cf("c", "2025-01-01", -10)]),
        }
        total = aggregate_venue_roi(summary, events, valuation)
        self.assertEqual(total[AssetsDef.EVALUATION_DATE].iloc[0], "2026-07-01")

    def test_empty_summary_returns_empty(self):
        total = aggregate_venue_roi(pd.DataFrame(), {}, date(2026, 1, 1))
        self.assertTrue(total.empty)


if __name__ == "__main__":
    unittest.main()
