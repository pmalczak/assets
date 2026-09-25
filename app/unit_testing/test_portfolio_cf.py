# -*- coding: utf-8 -*-
"""Testy warstwy portfolio_cf (ledger → alokacja → XIRR)."""
from __future__ import annotations

import unittest
from datetime import date

import pandas as pd

from portfolio_cf.adapters.base import (
    build_ledger_row,
    cash_leg_category_and_amount,
    legacy_events_to_ledger,
)
from portfolio_cf.allocate import allocate_ledger_to_portfolio
from portfolio_cf.assemble import AssemblyResult
from portfolio_cf.coverage import CoverageStatus, InstrumentCoverage
from portfolio_cf.data_model import InstrumentCashFlow, cash_instrument_id
from portfolio_cf.fx import to_pln
from portfolio_cf.instrument_portfolio import portfolio_for_instrument
from portfolio_cf.xirr import compute_named_portfolio_xirr
from portfolios.assignment import (
    PORTFOLIO_GM,
    PORTFOLIO_NIERUCHOMOSCI,
    PORTFOLIO_PLYNNY,
    PORTFOLIO_REVOLUT_ROBO,
)
from roi.categories import CAPEX, DIVESTMENT, OPEX, REVENUES
from roi.data_model import CashFlowEvent


class PortfolioCfFxTests(unittest.TestCase):
    def test_pln_passthrough(self):
        result = to_pln(100.0, "PLN", date(2024, 6, 1), fx_rates=_fx_frame())
        self.assertEqual(result.amount_pln, 100.0)
        self.assertEqual(result.fx_rate, 1.0)

    def test_eur_uses_rate_on_or_before(self):
        result = to_pln(10.0, "EUR", date(2024, 6, 2), fx_rates=_fx_frame())
        self.assertAlmostEqual(result.amount_pln, 42.0)
        self.assertEqual(result.fx_date, "2024-06-01")


class PortfolioCfMappingTests(unittest.TestCase):
    def test_broker_prefixes(self):
        self.assertEqual(portfolio_for_instrument("p_re_robo:PRAR"), PORTFOLIO_REVOLUT_ROBO)
        self.assertEqual(portfolio_for_instrument("p_re_robo:CASH"), PORTFOLIO_REVOLUT_ROBO)
        self.assertEqual(portfolio_for_instrument("p_degiro:IE00BKM4GZ66"), PORTFOLIO_GM)
        self.assertEqual(portfolio_for_instrument("p_xtb:ETFPZUW20M40.PL"), PORTFOLIO_GM)
        self.assertEqual(portfolio_for_instrument("p_xtb:CASH"), PORTFOLIO_GM)

    def test_property_and_default(self):
        self.assertEqual(portfolio_for_instrument("aquamarina"), PORTFOLIO_NIERUCHOMOSCI)
        self.assertEqual(portfolio_for_instrument("horbaczewskiego"), PORTFOLIO_NIERUCHOMOSCI)
        self.assertEqual(portfolio_for_instrument("zloto-monety"), PORTFOLIO_PLYNNY)
        self.assertEqual(portfolio_for_instrument("obligacjeskarbowe:EDO1029"), PORTFOLIO_PLYNNY)


class PortfolioCfCashLegTests(unittest.TestCase):
    def test_buy_sell_mirror(self):
        cat, amt = cash_leg_category_and_amount(CAPEX, -1000.0)
        self.assertEqual(cat, DIVESTMENT)
        self.assertEqual(amt, 1000.0)
        cat, amt = cash_leg_category_and_amount(DIVESTMENT, 1000.0)
        self.assertEqual(cat, CAPEX)
        self.assertEqual(amt, -1000.0)

    def test_opex_has_no_mirror(self):
        with self.assertRaises(ValueError):
            cash_leg_category_and_amount(OPEX, -50.0)


class PortfolioCfLedgerTests(unittest.TestCase):
    def test_legacy_events_to_ledger_adds_pln(self):
        events = {
            "p_degiro:AAA": pd.DataFrame(
                [
                    {
                        CashFlowEvent.ASSET_ID: "p_degiro:AAA",
                        CashFlowEvent.DATE: "2024-06-01",
                        CashFlowEvent.AMOUNT: -100.0,
                        CashFlowEvent.CATEGORY: CAPEX,
                        CashFlowEvent.SOURCE: "p_degiro",
                        CashFlowEvent.DESCRIPTION: "BUY",
                        CashFlowEvent.TITLE: "AAA",
                        CashFlowEvent.COUNTERPARTY: "",
                        CashFlowEvent.ACCOUNT_NUMBER: "",
                    }
                ]
            )
        }
        ledger, coverage = legacy_events_to_ledger(
            events,
            venue="degiro",
            currency="EUR",
            valuation_date=date(2024, 12, 31),
            fx_rates=_fx_frame(),
        )
        self.assertEqual(len(ledger), 1)
        self.assertAlmostEqual(float(ledger.iloc[0][InstrumentCashFlow.AMOUNT_PLN]), -420.0)
        self.assertEqual(coverage[0].status, CoverageStatus.COVERED)

    def test_same_day_rebalance_nets_in_portfolio_pln(self):
        """SELL ETF1 + BUY ETF2 tego samego dnia → netto 0 w amount_pln."""
        rows = [
            build_ledger_row(
                instrument_id="p_xtb:A",
                event_date="2024-01-01",
                category=CAPEX,
                amount=-10000.0,
                currency="PLN",
                venue="xtb",
                fx_rates=_fx_frame(),
            ),
            build_ledger_row(
                instrument_id="p_xtb:A",
                event_date="2024-07-01",
                category=DIVESTMENT,
                amount=10500.0,
                currency="PLN",
                venue="xtb",
                fx_rates=_fx_frame(),
            ),
            build_ledger_row(
                instrument_id="p_xtb:B",
                event_date="2024-07-01",
                category=CAPEX,
                amount=-10500.0,
                currency="PLN",
                venue="xtb",
                fx_rates=_fx_frame(),
            ),
            build_ledger_row(
                instrument_id="p_xtb:B",
                event_date="2025-01-01",
                category=DIVESTMENT,
                amount=11000.0,
                currency="PLN",
                venue="xtb",
                fx_rates=_fx_frame(),
            ),
        ]
        ledger = pd.DataFrame(rows)
        subset = allocate_ledger_to_portfolio(ledger, PORTFOLIO_GM)
        by_day = subset.groupby(InstrumentCashFlow.DATE)[InstrumentCashFlow.AMOUNT_PLN].sum()
        self.assertAlmostEqual(float(by_day.loc["2024-07-01"]), 0.0)


class PortfolioCfXirrTests(unittest.TestCase):
    def test_xirr_not_average_of_instruments(self):
        """Przykład skali: concat ≈ 1.99%, nie średnia 50.5%."""
        rows = [
            build_ledger_row(
                instrument_id="p_xtb:A",
                event_date="2024-01-01",
                category=CAPEX,
                amount=-1000.0,
                currency="PLN",
                venue="xtb",
                fx_rates=_fx_frame(),
            ),
            build_ledger_row(
                instrument_id="p_xtb:B",
                event_date="2024-01-01",
                category=CAPEX,
                amount=-99000.0,
                currency="PLN",
                venue="xtb",
                fx_rates=_fx_frame(),
            ),
        ]
        ledger = pd.DataFrame(rows)
        coverage = [
            InstrumentCoverage("p_xtb:A", CoverageStatus.COVERED, venue="xtb"),
            InstrumentCoverage("p_xtb:B", CoverageStatus.COVERED, venue="xtb"),
        ]
        assembly = AssemblyResult(ledger=ledger, coverage=coverage)
        result = compute_named_portfolio_xirr(
            PORTFOLIO_GM,
            date(2025, 1, 1),
            assembly=assembly,
            terminal_pln=101990.0,
        )
        self.assertIsNotNone(result.xirr)
        self.assertAlmostEqual(result.xirr, 0.0199, places=3)
        average_wrong = (1.0 + 0.01) / 2
        self.assertNotAlmostEqual(result.xirr, average_wrong, places=2)

    def test_uncovered_with_nav_marks_incomplete(self):
        assembly = AssemblyResult(
            ledger=pd.DataFrame(columns=list(InstrumentCashFlow.COLUMN_ORDER)),
            coverage=[
                InstrumentCoverage(
                    "gm_ike",
                    CoverageStatus.UNCOVERED,
                    reason="brak CF",
                    venue="long_term",
                )
            ],
        )
        result = compute_named_portfolio_xirr(
            "3 DŁUGOTERMINOWY",
            date(2025, 1, 1),
            assembly=assembly,
            terminal_pln=1000.0,
        )
        self.assertTrue(result.incomplete)
        self.assertTrue(any("niekompletne" in w.lower() for w in result.warnings))

    def test_cash_instrument_id(self):
        self.assertEqual(cash_instrument_id("p_degiro"), "p_degiro:CASH")


class PortfolioCfExportTests(unittest.TestCase):
    def test_portfolio_excel_has_cf_coverage_meta(self):
        from io import BytesIO

        from portfolio_cf.export_excel import (
            portfolio_cf_excel_filename,
            portfolio_cf_to_excel_bytes,
        )

        rows = [
            build_ledger_row(
                instrument_id="p_xtb:A",
                event_date="2024-01-01",
                category=CAPEX,
                amount=-1000.0,
                currency="PLN",
                venue="xtb",
                fx_rates=_fx_frame(),
            ),
            build_ledger_row(
                instrument_id="p_xtb:CLOSED",
                event_date="2024-01-01",
                category=CAPEX,
                amount=-500.0,
                currency="PLN",
                venue="xtb",
                fx_rates=_fx_frame(),
            ),
        ]
        assembly = AssemblyResult(
            ledger=pd.DataFrame(rows),
            coverage=[
                InstrumentCoverage("p_xtb:A", CoverageStatus.COVERED, venue="xtb"),
                InstrumentCoverage("p_xtb:CLOSED", CoverageStatus.COVERED, venue="xtb"),
                InstrumentCoverage(
                    "gm_ike", CoverageStatus.UNCOVERED, reason="brak CF", venue="long_term"
                ),
            ],
            is_sold_by_instrument={"p_xtb:A": False, "p_xtb:CLOSED": True},
        )
        payload = portfolio_cf_to_excel_bytes(
            assembly, PORTFOLIO_GM, date(2025, 1, 1), sold_filter="Niesprzedane"
        )
        self.assertTrue(payload.startswith(b"PK"))
        book = pd.ExcelFile(BytesIO(payload))
        self.assertEqual(set(book.sheet_names), {"cf", "coverage", "meta"})
        cf = pd.read_excel(book, sheet_name="cf")
        self.assertIn("portfel", cf.columns)
        self.assertEqual(set(cf["instrument_id"].astype(str)), {"p_xtb:A"})
        self.assertEqual(
            portfolio_cf_excel_filename(PORTFOLIO_GM, date(2025, 1, 1)),
            "portfolio_cf_2_g_momentum_2025-01-01.xlsx",
        )


class PortfolioCfSoldFilterTests(unittest.TestCase):
    def test_filter_hides_sold_instruments(self):
        from app_proc.ui_prefs import SOLD_FILTER_ACTIVE, SOLD_FILTER_SOLD
        from portfolio_cf.sold_status import filter_ledger_by_sold

        rows = [
            build_ledger_row(
                instrument_id="dep:open",
                event_date="2024-01-01",
                category=CAPEX,
                amount=-100.0,
                currency="PLN",
                venue="deposits",
                fx_rates=_fx_frame(),
            ),
            build_ledger_row(
                instrument_id="dep:closed",
                event_date="2024-01-01",
                category=CAPEX,
                amount=-100.0,
                currency="PLN",
                venue="deposits",
                fx_rates=_fx_frame(),
            ),
        ]
        ledger = pd.DataFrame(rows)
        sold = {"dep:open": False, "dep:closed": True}
        open_only = filter_ledger_by_sold(ledger, sold, sold_filter=SOLD_FILTER_ACTIVE)
        self.assertEqual(
            set(open_only[InstrumentCashFlow.INSTRUMENT_ID].astype(str)),
            {"dep:open"},
        )
        sold_only = filter_ledger_by_sold(ledger, sold, sold_filter=SOLD_FILTER_SOLD)
        self.assertEqual(
            set(sold_only[InstrumentCashFlow.INSTRUMENT_ID].astype(str)),
            {"dep:closed"},
        )


def _fx_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {"EUR": [4.0, 4.2]},
        index=pd.to_datetime(["2024-05-31", "2024-06-01"]),
    )


if __name__ == "__main__":
    unittest.main()
