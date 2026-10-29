# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest
from datetime import date

import pandas as pd

from portfolios.assignment import PORTFOLIO_DLUGOTERMINOWY, PORTFOLIO_GM
from portfolio_cf.instrument_portfolio import portfolio_for_instrument
from roi.broker_investment_cycles import (
    broker_base_instrument_id,
    closed_cycle_instrument_id,
    is_closed_cycle_instrument_id,
    partition_broker_cashflows,
)
from roi.broker_trading_roi import compute_ticker_roi, ticker_asset_id
from roi.categories import CAPEX, DIVESTMENT, REVENUES
from roi.data_model import CashFlowEvent


def _cf(
    asset_id: str,
    day: str,
    category: str,
    amount: float,
    quantity: float | None = None,
) -> dict:
    return {
        CashFlowEvent.ASSET_ID: asset_id,
        CashFlowEvent.DATE: day,
        CashFlowEvent.AMOUNT: amount,
        CashFlowEvent.QUANTITY: quantity,
        CashFlowEvent.UNIT_PRICE: None,
        CashFlowEvent.CATEGORY: category,
        CashFlowEvent.SOURCE: "p_degiro",
        CashFlowEvent.DESCRIPTION: category,
        CashFlowEvent.TITLE: asset_id,
        CashFlowEvent.COUNTERPARTY: "",
        CashFlowEvent.ACCOUNT_NUMBER: "",
    }


class BrokerInvestmentCycleIdTests(unittest.TestCase):
    def test_base_and_closed_helpers(self):
        bare = "p_degiro:IE00B4L5YX21"
        closed = closed_cycle_instrument_id(bare, date(2026, 8, 31))
        self.assertEqual(closed, "p_degiro:IE00B4L5YX21#2026-08-31")
        self.assertEqual(broker_base_instrument_id(closed), bare)
        self.assertTrue(is_closed_cycle_instrument_id(closed))
        self.assertFalse(is_closed_cycle_instrument_id(bare))
        self.assertEqual(
            closed_cycle_instrument_id(bare, date(2026, 8, 31), collision=2),
            "p_degiro:IE00B4L5YX21#2026-08-31.2",
        )

    def test_portfolio_override_uses_base_id(self):
        self.assertEqual(
            portfolio_for_instrument("p_degiro:LT0000128621#2026-01-15"),
            PORTFOLIO_DLUGOTERMINOWY,
        )
        self.assertEqual(
            portfolio_for_instrument("p_degiro:IE00B4L5YX21#2026-08-31"),
            PORTFOLIO_GM,
        )


class BrokerInvestmentCyclePartitionTests(unittest.TestCase):
    def test_eunn_close_then_reopen_splits_cycles(self):
        """Cykl 17–31.08 zamknięty; CAPEX 30.09/02.10 = osobny otwarty instrument."""
        base = ticker_asset_id("p_degiro", "IE00B4L5YX21")
        events = pd.DataFrame(
            [
                _cf(base, "2026-08-17", CAPEX, -4947.71, 68.0),
                _cf(base, "2026-08-31", DIVESTMENT, 4875.72, 68.0),
                _cf(base, "2026-09-30", CAPEX, -12680.3, 170.0),
                _cf(base, "2026-10-02", CAPEX, -2794.61, 37.0),
            ]
        )
        partitioned, warnings = partition_broker_cashflows({base: events})
        self.assertEqual(warnings, [])
        closed_id = "p_degiro:IE00B4L5YX21#2026-08-31"
        self.assertEqual(set(partitioned), {closed_id, base})

        closed = partitioned[closed_id]
        self.assertEqual(len(closed), 2)
        self.assertEqual(closed[CashFlowEvent.CATEGORY].tolist(), [CAPEX, DIVESTMENT])
        closed_roi = compute_ticker_roi(
            closed_id, closed, date(2026, 10, 29), open_qty=0.0, last_price=0.0
        )
        self.assertTrue(closed_roi.is_sold)
        self.assertAlmostEqual(closed_roi.roi_nominal, -4947.71 + 4875.72, places=2)
        self.assertAlmostEqual(closed_roi.terminal_unrealized, 0.0)

        opened = partitioned[base]
        self.assertEqual(len(opened), 2)
        self.assertEqual(opened[CashFlowEvent.DATE].tolist(), ["2026-09-30", "2026-10-02"])
        open_roi = compute_ticker_roi(
            base, opened, date(2026, 10, 29), open_qty=1.0, last_price=15099.22
        )
        self.assertFalse(open_roi.is_sold)
        self.assertAlmostEqual(open_roi.capex, -12680.3 - 2794.61, places=2)
        self.assertAlmostEqual(open_roi.terminal_unrealized, 15099.22)

    def test_mid_cycle_valuation_keeps_single_bare_id(self):
        base = ticker_asset_id("p_degiro", "IE00B4L5YX21")
        events = pd.DataFrame(
            [
                _cf(base, "2026-08-17", CAPEX, -4947.71, 68.0),
                _cf(base, "2026-08-31", DIVESTMENT, 4875.72, 68.0),
            ]
        )
        # Tylko CF ≤ 25.08 — pozycja jeszcze otwarta.
        mid = events.loc[events[CashFlowEvent.DATE] <= "2026-08-25"].copy()
        partitioned, warnings = partition_broker_cashflows({base: mid})
        self.assertEqual(warnings, [])
        self.assertEqual(set(partitioned), {base})
        self.assertFalse(is_closed_cycle_instrument_id(next(iter(partitioned))))

    def test_partial_sell_does_not_split(self):
        base = ticker_asset_id("p_degiro", "IE00B4L5YX21")
        events = pd.DataFrame(
            [
                _cf(base, "2026-08-17", CAPEX, -4947.71, 68.0),
                _cf(base, "2026-08-20", DIVESTMENT, 2400.0, 34.0),
                _cf(base, "2026-09-01", CAPEX, -1000.0, 10.0),
            ]
        )
        partitioned, warnings = partition_broker_cashflows({base: events})
        self.assertEqual(warnings, [])
        self.assertEqual(set(partitioned), {base})
        self.assertEqual(len(partitioned[base]), 3)

    def test_missing_quantity_skips_partition(self):
        base = ticker_asset_id("p_xtb", "SOME.PL")
        events = pd.DataFrame(
            [
                _cf(base, "2026-01-01", CAPEX, -100.0, None),
                _cf(base, "2026-02-01", DIVESTMENT, 90.0, None),
                _cf(base, "2026-03-01", CAPEX, -50.0, 5.0),
            ]
        )
        partitioned, warnings = partition_broker_cashflows({base: events})
        self.assertEqual(len(warnings), 1)
        self.assertEqual(set(partitioned), {base})
        self.assertEqual(len(partitioned[base]), 3)

    def test_dividend_attaches_to_open_cycle(self):
        base = ticker_asset_id("p_re_robo", "PRAR")
        events = pd.DataFrame(
            [
                _cf(base, "2026-01-01", CAPEX, -1000.0, 10.0),
                _cf(base, "2026-02-01", REVENUES, 5.0, None),
                _cf(base, "2026-03-01", DIVESTMENT, 900.0, 10.0),
                _cf(base, "2026-04-01", CAPEX, -500.0, 5.0),
            ]
        )
        partitioned, warnings = partition_broker_cashflows({base: events})
        self.assertEqual(warnings, [])
        closed_id = "p_re_robo:PRAR#2026-03-01"
        self.assertEqual(set(partitioned), {closed_id, base})
        self.assertEqual(
            partitioned[closed_id][CashFlowEvent.CATEGORY].tolist(),
            [CAPEX, REVENUES, DIVESTMENT],
        )
        self.assertEqual(
            partitioned[base][CashFlowEvent.CATEGORY].tolist(),
            [CAPEX],
        )


if __name__ == "__main__":
    unittest.main()
