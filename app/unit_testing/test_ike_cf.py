# -*- coding: utf-8 -*-
"""Testy CF / MTM IKE (fixtures — bez Dropbox)."""
from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import patch

import pandas as pd

from importers.assets.ike import IkeInventory, IkeKurs, ike_terminal_value
from portfolio_cf.adapters.ike import adapt_ike_ledger
from portfolio_cf.assemble import build_instrument_ledger
from portfolio_cf.coverage import CoverageStatus
from portfolio_cf.data_model import InstrumentCashFlow
from roi.categories import CAPEX, DIVESTMENT
from roi.data_model import CashFlowEvent
from roi.ike_roi import build_ike_cashflows, load_ike_events_by_asset

_PRODUCT = "IKE mAkcji Poslkich (kat. a)"


def _inv_frame(rows: list[tuple]) -> pd.DataFrame:
    """(date, units, value) → inventory frame."""
    data = [
        {
            IkeInventory.PRODUCT: _PRODUCT,
            IkeInventory.DATE: d,
            IkeInventory.UNITS: u,
            IkeInventory.VALUE: v,
            IkeInventory.CURRENCY: "PLN",
        }
        for d, u, v in rows
    ]
    return pd.DataFrame(data)


def _kurs_frame(rows: list[tuple]) -> pd.DataFrame:
    """(date, price) → kurs frame."""
    data = [
        {IkeKurs.PRODUCT: _PRODUCT, IkeKurs.DATE: d, IkeKurs.PRICE: p}
        for d, p in rows
    ]
    if not data:
        return pd.DataFrame(columns=[IkeKurs.PRODUCT, IkeKurs.DATE, IkeKurs.PRICE])
    return pd.DataFrame(data)


class IkeCashflowTests(unittest.TestCase):
    def test_purchase_is_negative_capex(self):
        inv = _inv_frame(
            [
                ("2020-01-01", 10.0, 1000.0),
                ("2020-06-01", 5.0, 600.0),
            ]
        )
        events = build_ike_cashflows(inv, "pm_ike")
        self.assertEqual(len(events), 2)
        self.assertTrue((events[CashFlowEvent.CATEGORY] == CAPEX).all())
        self.assertAlmostEqual(float(events[CashFlowEvent.AMOUNT].sum()), -1600.0)
        self.assertTrue((events[CashFlowEvent.AMOUNT] < 0).all())

    def test_negative_value_or_units_is_divestment(self):
        inv = _inv_frame(
            [
                ("2021-01-01", -2.0, -500.0),
            ]
        )
        events = build_ike_cashflows(inv, "gm_ike")
        self.assertEqual(len(events), 1)
        self.assertEqual(events.iloc[0][CashFlowEvent.CATEGORY], DIVESTMENT)
        self.assertAlmostEqual(float(events.iloc[0][CashFlowEvent.AMOUNT]), 500.0)

    def test_date_filter_in_load(self):
        inv = _inv_frame(
            [
                ("2020-01-01", 1.0, 100.0),
                ("2022-01-01", 1.0, 200.0),
            ]
        )
        events = load_ike_events_by_asset(
            date(2021, 6, 1),
            inventory_by_account={"pm": inv, "gm": _inv_frame([])},
        )
        self.assertEqual(len(events["pm_ike"]), 1)
        self.assertAlmostEqual(float(events["pm_ike"].iloc[0][CashFlowEvent.AMOUNT]), -100.0)
        self.assertTrue(events["gm_ike"].empty)


class IkeTerminalTests(unittest.TestCase):
    def test_qty_times_last_kurs(self):
        inv = _inv_frame(
            [
                ("2020-01-01", 10.0, 1000.0),
                ("2020-06-01", 5.0, 600.0),
            ]
        )
        kurs = _kurs_frame(
            [
                ("2020-01-01", 100.0),
                ("2020-12-01", 200.0),
            ]
        )
        terminal = ike_terminal_value(inv, kurs, date(2021, 1, 1))
        self.assertIsNotNone(terminal)
        value, eval_date = terminal
        self.assertAlmostEqual(value, 15.0 * 200.0)
        self.assertEqual(eval_date, date(2020, 12, 1))

    def test_nav_sums_per_product_times_own_kurs(self):
        inv = pd.DataFrame(
            [
                {
                    IkeInventory.PRODUCT: "A",
                    IkeInventory.DATE: "2020-01-01",
                    IkeInventory.UNITS: 10.0,
                    IkeInventory.VALUE: 100.0,
                    IkeInventory.CURRENCY: "PLN",
                },
                {
                    IkeInventory.PRODUCT: "A",
                    IkeInventory.DATE: "2020-02-01",
                    IkeInventory.UNITS: 5.0,
                    IkeInventory.VALUE: 50.0,
                    IkeInventory.CURRENCY: "PLN",
                },
                {
                    IkeInventory.PRODUCT: "B",
                    IkeInventory.DATE: "2020-01-15",
                    IkeInventory.UNITS: 2.0,
                    IkeInventory.VALUE: 80.0,
                    IkeInventory.CURRENCY: "PLN",
                },
            ]
        )
        kurs = pd.DataFrame(
            [
                {IkeKurs.PRODUCT: "A", IkeKurs.DATE: "2020-06-01", IkeKurs.PRICE: 10.0},
                {IkeKurs.PRODUCT: "B", IkeKurs.DATE: "2020-07-01", IkeKurs.PRICE: 40.0},
            ]
        )
        terminal = ike_terminal_value(inv, kurs, date(2021, 1, 1))
        self.assertIsNotNone(terminal)
        value, eval_date = terminal
        self.assertAlmostEqual(value, 15.0 * 10.0 + 2.0 * 40.0)
        self.assertEqual(eval_date, date(2020, 7, 1))

    def test_missing_kurs_with_qty_raises(self):
        inv = _inv_frame([("2020-01-01", 10.0, 1000.0)])
        with self.assertRaises(ValueError):
            ike_terminal_value(inv, _kurs_frame([]), date(2020, 6, 1))

    def test_empty_inventory_returns_none(self):
        self.assertIsNone(
            ike_terminal_value(_inv_frame([]), _kurs_frame([("2020-01-01", 1.0)]), date(2020, 6, 1))
        )


class IkeAdapterTests(unittest.TestCase):
    def test_adapt_marks_covered_and_builds_ledger(self):
        events = {
            "pm_ike": build_ike_cashflows(
                _inv_frame([("2020-01-01", 2.0, 400.0)]), "pm_ike"
            ),
            "gm_ike": build_ike_cashflows(
                _inv_frame([("2020-02-01", 1.0, 200.0)]), "gm_ike"
            ),
        }
        ledger, coverage, warnings = adapt_ike_ledger(
            date(2021, 1, 1), events_by_asset=events
        )
        self.assertEqual(warnings, [])
        statuses = {c.instrument_id: c.status for c in coverage}
        self.assertEqual(statuses["pm_ike"], CoverageStatus.COVERED)
        self.assertEqual(statuses["gm_ike"], CoverageStatus.COVERED)
        self.assertEqual(len(ledger), 2)
        self.assertAlmostEqual(
            float(ledger[InstrumentCashFlow.AMOUNT].sum()), -600.0
        )

    def test_assemble_does_not_uncover_ike_when_adapter_covers(self):
        events = {
            "pm_ike": build_ike_cashflows(
                _inv_frame([("2020-01-01", 1.0, 100.0)]), "pm_ike"
            ),
            "gm_ike": build_ike_cashflows(
                _inv_frame([("2020-01-01", 1.0, 100.0)]), "gm_ike"
            ),
        }
        snapshot = pd.DataFrame(
            {
                "id": ["pm_ike", "gm_ike", "rocky-iv"],
                "typ": ["investment.udziały", "investment.udziały", "investment.udziały"],
            }
        )

        def _fake_catalog(vd, **kwargs):
            from portfolio_cf.adapters.base import empty_ledger
            from portfolio_cf.coverage import InstrumentCoverage

            return (
                empty_ledger(),
                [
                    InstrumentCoverage(
                        "rocky-iv", CoverageStatus.COVERED, venue="catalog"
                    )
                ],
                [],
            )

        with (
            patch("portfolio_cf.assemble.adapt_catalog_ledger", side_effect=_fake_catalog),
            patch("portfolio_cf.assemble.adapt_robo_ledger", side_effect=_empty_adapter),
            patch("portfolio_cf.assemble.adapt_degiro_ledger", side_effect=_empty_adapter),
            patch("portfolio_cf.assemble.adapt_xtb_ledger", side_effect=_empty_adapter),
            patch("portfolio_cf.assemble.adapt_bonds_ledger", side_effect=_empty_adapter),
            patch("portfolio_cf.assemble.adapt_deposits_ledger", side_effect=_empty_adapter),
            patch(
                "portfolio_cf.assemble.adapt_ike_ledger",
                side_effect=lambda vd, **kw: adapt_ike_ledger(
                    vd, events_by_asset=events
                ),
            ),
            patch(
                "portfolio_cf.sold_status.build_instrument_sold_map",
                return_value={},
            ),
        ):
            asm = build_instrument_ledger(date(2021, 1, 1), snapshot=snapshot)

        uncovered_ids = {u.instrument_id for u in asm.uncovered()}
        self.assertNotIn("pm_ike", uncovered_ids)
        self.assertNotIn("gm_ike", uncovered_ids)


def _empty_adapter(vd, **kwargs):
    from portfolio_cf.adapters.base import empty_ledger

    return empty_ledger(), [], []


if __name__ == "__main__":
    unittest.main()
