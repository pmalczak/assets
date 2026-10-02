# -*- coding: utf-8 -*-
"""Testy warstwy portfolio_cf (ledger → alokacja → XIRR)."""
from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import patch

import pandas as pd

from portfolio_cf.adapters.base import (
    build_ledger_row,
    cash_leg_category_and_amount,
    legacy_events_to_ledger,
)
from portfolio_cf.allocate import allocate_ledger_to_portfolio
from portfolio_cf.assemble import AssemblyResult, build_instrument_ledger
from portfolio_cf.coverage import CoverageStatus, InstrumentCoverage
from portfolio_cf.data_model import InstrumentCashFlow, cash_instrument_id
from portfolio_cf.fx import to_pln
from portfolio_cf.instrument_portfolio import portfolio_for_instrument
from portfolio_cf.xirr import compute_named_portfolio_xirr
from portfolios.assignment import (
    PORTFOLIO_DLUGOTERMINOWY,
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

    def test_inter_rao_override_to_dlugoterminowy(self):
        self.assertEqual(
            portfolio_for_instrument("p_degiro:LT0000128621"),
            PORTFOLIO_DLUGOTERMINOWY,
        )

    def test_property_and_default(self):
        self.assertEqual(portfolio_for_instrument("aquamarina"), PORTFOLIO_NIERUCHOMOSCI)
        self.assertEqual(portfolio_for_instrument("horbaczewskiego"), PORTFOLIO_NIERUCHOMOSCI)
        self.assertEqual(portfolio_for_instrument("zloto-monety"), PORTFOLIO_DLUGOTERMINOWY)
        self.assertEqual(
            portfolio_for_instrument("obligacjeskarbowe:EDO1029"),
            PORTFOLIO_DLUGOTERMINOWY,
        )


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


class PortfolioCfAdapterNoCashTests(unittest.TestCase):
    def test_adapt_robo_ledger_has_no_cash_instrument(self):
        from importers.revolut.trading_data_model import RevolutTradingFile
        from portfolio_cf.adapters.robo import adapt_robo_ledger

        trading = pd.DataFrame(
            [
                {
                    RevolutTradingFile.DATE: "2024-06-01T12:00:00.000Z",
                    RevolutTradingFile.TICKER: "PRAR",
                    RevolutTradingFile.TYPE: RevolutTradingFile.TYPE_BUY,
                    RevolutTradingFile.QUANTITY: 10,
                    RevolutTradingFile.PRICE_PER_SHARE: "10",
                    RevolutTradingFile.TOTAL_AMOUNT: "-100",
                    RevolutTradingFile.CURRENCY: "EUR",
                    RevolutTradingFile.FX_RATE: "1",
                    RevolutTradingFile.FILE_DATE: "2024-06-01",
                    RevolutTradingFile.PERIOD_START: "2024-01-01",
                    RevolutTradingFile.PERIOD_END: "2024-06-01",
                },
                {
                    RevolutTradingFile.DATE: "2024-06-01T12:00:00.000Z",
                    RevolutTradingFile.TICKER: "",
                    RevolutTradingFile.TYPE: RevolutTradingFile.TYPE_CASH_TOP_UP,
                    RevolutTradingFile.QUANTITY: "",
                    RevolutTradingFile.PRICE_PER_SHARE: "",
                    RevolutTradingFile.TOTAL_AMOUNT: "500",
                    RevolutTradingFile.CURRENCY: "EUR",
                    RevolutTradingFile.FX_RATE: "1",
                    RevolutTradingFile.FILE_DATE: "2024-06-01",
                    RevolutTradingFile.PERIOD_START: "2024-01-01",
                    RevolutTradingFile.PERIOD_END: "2024-06-01",
                },
            ]
        )
        ledger, coverage, _warnings = adapt_robo_ledger(
            date(2025, 1, 1),
            trading_df=trading,
            fx_rates=_fx_frame(),
        )
        ids = (
            set(ledger[InstrumentCashFlow.INSTRUMENT_ID].astype(str))
            if not ledger.empty
            else set()
        )
        cov_ids = {item.instrument_id for item in coverage}
        self.assertTrue(all(not iid.endswith(":CASH") for iid in ids | cov_ids))
        self.assertIn("p_re_robo:PRAR", ids)
        buy = ledger.loc[ledger[InstrumentCashFlow.INSTRUMENT_ID] == "p_re_robo:PRAR"].iloc[0]
        self.assertAlmostEqual(float(buy[InstrumentCashFlow.QUANTITY]), 10.0)
        self.assertAlmostEqual(float(buy[InstrumentCashFlow.UNIT_PRICE]), 10.0)


class PortfolioCfUnitPriceTests(unittest.TestCase):
    def test_degiro_transaction_carries_unit_price(self):
        from importers.degiro.data_model import DegiroTransactionsFile
        from roi.degiro_roi import build_degiro_cashflows

        transactions = pd.DataFrame(
            [
                {
                    DegiroTransactionsFile.DATE: "01-06-2024",
                    DegiroTransactionsFile.TIME: "10:00",
                    DegiroTransactionsFile.PRODUCT: "AAA ETF",
                    DegiroTransactionsFile.ISIN: "IE00BKM4GZ66",
                    DegiroTransactionsFile.REFERENCE_EXCHANGE: "",
                    DegiroTransactionsFile.EXECUTION_VENUE: "",
                    DegiroTransactionsFile.QUANTITY: 5,
                    DegiroTransactionsFile.PRICE: 20.0,
                    DegiroTransactionsFile.PRICE_CURRENCY: "EUR",
                    DegiroTransactionsFile.LOCAL_VALUE: -100.0,
                    DegiroTransactionsFile.LOCAL_VALUE_CURRENCY: "EUR",
                    DegiroTransactionsFile.VALUE_EUR: -100.0,
                    DegiroTransactionsFile.FX_RATE: 1.0,
                    DegiroTransactionsFile.AUTOFX_FEE: "",
                    DegiroTransactionsFile.DEGIRO_FEE: "",
                    DegiroTransactionsFile.TOTAL_EUR: -100.0,
                    DegiroTransactionsFile.ORDER_ID: "ord-1",
                    DegiroTransactionsFile.FILE_DATE: "2024-06-01",
                    DegiroTransactionsFile.PERIOD_START: "2024-06-01",
                    DegiroTransactionsFile.PERIOD_END: "2024-06-01",
                }
            ]
        )
        events = build_degiro_cashflows(transactions, pd.DataFrame(), "p_degiro")
        df = events["p_degiro:IE00BKM4GZ66"]
        self.assertAlmostEqual(float(df.iloc[0][CashFlowEvent.QUANTITY]), 5.0)
        self.assertAlmostEqual(float(df.iloc[0][CashFlowEvent.UNIT_PRICE]), 20.0)

        ledger, _coverage = legacy_events_to_ledger(
            events,
            venue="degiro",
            currency="EUR",
            valuation_date=date(2025, 1, 1),
            fx_rates=_fx_frame(),
        )
        self.assertAlmostEqual(float(ledger.iloc[0][InstrumentCashFlow.QUANTITY]), 5.0)
        self.assertAlmostEqual(float(ledger.iloc[0][InstrumentCashFlow.UNIT_PRICE]), 20.0)

    def test_ledger_row_without_price_stays_empty(self):
        row = build_ledger_row(
            instrument_id="p_xtb:A",
            event_date="2024-01-01",
            category=CAPEX,
            amount=-1000.0,
            currency="PLN",
            venue="xtb",
        )
        self.assertIsNone(row[InstrumentCashFlow.QUANTITY])
        self.assertIsNone(row[InstrumentCashFlow.UNIT_PRICE])


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
                        CashFlowEvent.COUNTERPARTY: "MENNICA KAPITALOWA",
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
        self.assertEqual(
            ledger.iloc[0][InstrumentCashFlow.COUNTERPARTY], "MENNICA KAPITALOWA"
        )
        self.assertEqual(coverage[0].status, CoverageStatus.COVERED)

    def test_catalog_rocky_iv_capex_eur_to_pln(self):
        """rocky-iv: CAPEX w EUR → amount_pln; nie traktować kwot EUR jako PLN."""
        from portfolio_cf.adapters.catalog import adapt_catalog_ledger

        events = {
            "rocky-iv": pd.DataFrame(
                [
                    {
                        CashFlowEvent.ASSET_ID: "rocky-iv",
                        CashFlowEvent.DATE: "2024-06-01",
                        CashFlowEvent.AMOUNT: -1000.0,
                        CashFlowEvent.CATEGORY: CAPEX,
                        CashFlowEvent.SOURCE: "manual",
                        CashFlowEvent.DESCRIPTION: "buy",
                        CashFlowEvent.TITLE: "",
                        CashFlowEvent.COUNTERPARTY: "",
                        CashFlowEvent.ACCOUNT_NUMBER: "",
                    }
                ]
            )
        }
        with patch(
            "portfolio_cf.adapters.catalog._catalog_currencies_from_assets",
            return_value={"rocky-iv": "EUR"},
        ):
            ledger, coverage, _warnings = adapt_catalog_ledger(
                date(2025, 1, 1),
                events_by_asset=events,
                fx_rates=_fx_frame(),
            )
        self.assertEqual(len(coverage), 1)
        self.assertEqual(str(ledger.iloc[0][InstrumentCashFlow.CURRENCY]), "EUR")
        self.assertAlmostEqual(float(ledger.iloc[0][InstrumentCashFlow.AMOUNT]), -1000.0)
        self.assertAlmostEqual(float(ledger.iloc[0][InstrumentCashFlow.AMOUNT_PLN]), -4200.0)

    def test_catalog_fallback_eur_for_rocky_without_assets_map(self):
        from portfolio_cf.adapters.catalog import adapt_catalog_ledger

        events = {
            "rocky-iv": pd.DataFrame(
                [
                    {
                        CashFlowEvent.ASSET_ID: "rocky-iv",
                        CashFlowEvent.DATE: "2024-06-01",
                        CashFlowEvent.AMOUNT: -10.0,
                        CashFlowEvent.CATEGORY: CAPEX,
                        CashFlowEvent.SOURCE: "manual",
                        CashFlowEvent.DESCRIPTION: "",
                        CashFlowEvent.TITLE: "",
                        CashFlowEvent.COUNTERPARTY: "",
                        CashFlowEvent.ACCOUNT_NUMBER: "",
                    }
                ]
            )
        }
        with patch(
            "portfolio_cf.adapters.catalog._catalog_currencies_from_assets",
            return_value={},
        ):
            ledger, _coverage, _warnings = adapt_catalog_ledger(
                date(2025, 1, 1),
                events_by_asset=events,
                fx_rates=_fx_frame(),
            )
        self.assertEqual(str(ledger.iloc[0][InstrumentCashFlow.CURRENCY]), "EUR")
        self.assertAlmostEqual(float(ledger.iloc[0][InstrumentCashFlow.AMOUNT_PLN]), -42.0)

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
        self.assertAlmostEqual(result.xirr_pln, 0.0199, places=3)
        self.assertEqual(result.roi_fx_pln, 0.0)
        self.assertEqual(result.fx_share, 0.0)
        average_wrong = (1.0 + 0.01) / 2
        self.assertNotAlmostEqual(result.xirr, average_wrong, places=2)

    def test_pln_portfolio_fx_share_zero(self):
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
        ]
        assembly = AssemblyResult(
            ledger=pd.DataFrame(rows),
            coverage=[InstrumentCoverage("p_xtb:A", CoverageStatus.COVERED, venue="xtb")],
        )
        result = compute_named_portfolio_xirr(
            PORTFOLIO_GM,
            date(2025, 1, 1),
            assembly=assembly,
            terminal_pln=1100.0,
            fx_rates=_fx_frame(),
        )
        self.assertEqual(result.roi_fx_pln, 0.0)
        self.assertEqual(result.fx_share, 0.0)
        self.assertAlmostEqual(result.xirr, result.xirr_pln, places=6)

    def test_broker_cash_legs_excluded_from_portfolio_xirr(self):
        """Legacy *:CASH w ledgerze (gdyby powstały) nie wchodzą do XIRR portfela."""
        rows = [
            build_ledger_row(
                instrument_id="p_degiro:AAA",
                event_date="2024-05-31",
                category=CAPEX,
                amount=-1000.0,
                currency="EUR",
                venue="degiro",
                fx_rates=_fx_frame(),
            ),
            build_ledger_row(
                instrument_id="p_degiro:CASH",
                event_date="2024-05-31",
                category=DIVESTMENT,
                amount=1000.0,
                currency="EUR",
                venue="degiro",
                description="cash-leg:BUY",
                fx_rates=_fx_frame(),
            ),
            build_ledger_row(
                instrument_id="p_degiro:CASH",
                event_date="2024-06-01",
                category=DIVESTMENT,
                amount=5000.0,
                currency="EUR",
                venue="degiro",
                description="cash-leg:BUY",
                fx_rates=_fx_frame(),
            ),
        ]
        assembly = AssemblyResult(
            ledger=pd.DataFrame(rows),
            coverage=[
                InstrumentCoverage("p_degiro:AAA", CoverageStatus.COVERED, venue="degiro"),
                InstrumentCoverage("p_degiro:CASH", CoverageStatus.COVERED, venue="degiro"),
            ],
        )
        result = compute_named_portfolio_xirr(
            PORTFOLIO_GM,
            date(2025, 1, 1),
            assembly=assembly,
            terminal_pln=4500.0,
            fx_rates=_fx_frame(),
        )
        self.assertIsNotNone(result.xirr)
        self.assertIsNotNone(result.xirr_pln)

    def test_eur_fx_share_above_100_percent(self):
        """Strata lokalna skompensowana wzrostem kursu → udział FX > 100%."""
        from portfolio_cf.fx_attribution import roi_fx_components

        rows = [
            build_ledger_row(
                instrument_id="p_degiro:AAA",
                event_date="2024-05-31",
                category=CAPEX,
                amount=-100.0,
                currency="EUR",
                venue="degiro",
                fx_rates=_fx_frame(),
            ),
        ]
        ledger = pd.DataFrame(rows)
        # FX_t=4.0, FX_T(2024-06-01)=4.2; terminal 96 EUR × 4.2
        components = roi_fx_components(
            ledger, 96.0 * 4.2, date(2024, 6, 1), fx_rates=_fx_frame()
        )
        self.assertGreater(components.roi_pln, 0.0)
        self.assertLess(components.roi_local, 0.0)
        self.assertIsNotNone(components.fx_share)
        self.assertGreater(components.fx_share, 1.0)

    def test_eur_fx_share_negative(self):
        """FX zjadł część zysku lokalnego → udział FX < 0%."""
        from portfolio_cf.fx_attribution import roi_fx_components

        rows = [
            build_ledger_row(
                instrument_id="p_degiro:AAA",
                event_date="2024-06-01",
                category=CAPEX,
                amount=-100.0,
                currency="EUR",
                venue="degiro",
                fx_rates=_fx_frame(),
            ),
        ]
        ledger = pd.DataFrame(rows)
        # FX_t=4.2, FX_T(2024-05-31)=4.0; terminal 110 EUR × 4.0
        components = roi_fx_components(
            ledger, 110.0 * 4.0, date(2024, 5, 31), fx_rates=_fx_frame()
        )
        self.assertGreater(components.roi_pln, 0.0)
        self.assertGreater(components.roi_local, components.roi_pln)
        self.assertIsNotNone(components.fx_share)
        self.assertLess(components.fx_share, 0.0)

    def test_portfolio_roi_fx_sums_instruments(self):
        from portfolio_cf.fx_attribution import roi_fx_components

        rows = [
            build_ledger_row(
                instrument_id="p_degiro:A",
                event_date="2024-05-31",
                category=CAPEX,
                amount=-50.0,
                currency="EUR",
                venue="degiro",
                fx_rates=_fx_frame(),
            ),
            build_ledger_row(
                instrument_id="p_xtb:B",
                event_date="2024-05-31",
                category=CAPEX,
                amount=-1000.0,
                currency="PLN",
                venue="xtb",
                fx_rates=_fx_frame(),
            ),
        ]
        ledger = pd.DataFrame(rows)
        terminal = 50.0 * 4.2 + 1100.0
        total = roi_fx_components(
            ledger, terminal, date(2024, 6, 1), fx_rates=_fx_frame()
        )
        part_a = roi_fx_components(
            ledger.loc[ledger[InstrumentCashFlow.INSTRUMENT_ID] == "p_degiro:A"],
            50.0 * 4.2,
            date(2024, 6, 1),
            fx_rates=_fx_frame(),
        )
        part_b = roi_fx_components(
            ledger.loc[ledger[InstrumentCashFlow.INSTRUMENT_ID] == "p_xtb:B"],
            1100.0,
            date(2024, 6, 1),
            fx_rates=_fx_frame(),
        )
        self.assertAlmostEqual(total.roi_fx, part_a.roi_fx + part_b.roi_fx, places=6)
        self.assertAlmostEqual(total.roi_pln, part_a.roi_pln + part_b.roi_pln, places=6)
        self.assertAlmostEqual(total.roi_local, part_a.roi_local + part_b.roi_local, places=6)

    def test_xirr_map_excludes_cash_pool(self):
        from importers.assets.data_model import AssetsDef
        from portfolio_cf.xirr import compute_named_portfolio_xirr_map
        from portfolios.assignment import PORTFOLIO_CASH_POOL

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
        ]
        assembly = AssemblyResult(
            ledger=pd.DataFrame(rows),
            coverage=[InstrumentCoverage("p_xtb:A", CoverageStatus.COVERED, venue="xtb")],
        )
        snapshot = pd.DataFrame(
            [
                {
                    AssetsDef.ID: "p_xtb",
                    AssetsDef.TYPE: "investment.udziały",
                    AssetsDef.VALUE_PLN: 1100.0,
                }
            ]
        )
        mapping = compute_named_portfolio_xirr_map(
            date(2025, 1, 1),
            assembly=assembly,
            snapshot=snapshot,
            sold_filter="Wszystkie",
            holdings_by_id={},
        )
        self.assertIsNone(mapping[PORTFOLIO_CASH_POOL])
        self.assertIn(PORTFOLIO_GM, mapping)
        self.assertIsNotNone(mapping[PORTFOLIO_GM])
        self.assertAlmostEqual(float(mapping[PORTFOLIO_GM]), 0.10, places=2)

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

    def test_razem_matches_header_when_instrument_terminals_differ(self):
        """Σ terminali tickerów ≠ NAV portfela (np. bez CASH) → Razem z wyniku portfela."""
        from portfolio_cf.xirr import build_portfolio_razem_row
        from roi.aggregate_venue_roi import VENUE_TOTAL_ASSET_ID

        rows = [
            build_ledger_row(
                instrument_id="p_re_robo:PRAR",
                event_date="2024-06-01",
                category=CAPEX,
                amount=-1000.0,
                currency="EUR",
                venue="robo",
                fx_rates=_fx_frame(),
            ),
        ]
        ledger = pd.DataFrame(rows)
        assembly = AssemblyResult(
            ledger=ledger,
            coverage=[
                InstrumentCoverage("p_re_robo:PRAR", CoverageStatus.COVERED, venue="robo")
            ],
            is_sold_by_instrument={"p_re_robo:PRAR": False},
        )
        snapshot_nav = 5000.0
        instrument_mtm = 4200.0
        header = compute_named_portfolio_xirr(
            PORTFOLIO_REVOLUT_ROBO,
            date(2025, 1, 1),
            assembly=assembly,
            terminal_pln=snapshot_nav,
            fx_rates=_fx_frame(),
            sold_filter="Wszystkie",
        )
        summary = pd.DataFrame(
            [
                {
                    "asset_id": "p_re_robo:PRAR",
                    "capex": -4200.0,
                    "opex": 0.0,
                    "revenue": 0.0,
                    "terminal_realized": 0.0,
                    "terminal_unrealized": instrument_mtm,
                    "roi_nominal": instrument_mtm - 4200.0,
                    "roi_local": instrument_mtm - 4200.0,
                    "roi_fx": 0.0,
                    "fx_share": 0.0,
                    "xirr": 0.01,
                    "xirr_pln": 0.01,
                    "is_sold": False,
                }
            ]
        )
        self.assertNotEqual(instrument_mtm, snapshot_nav)
        razem = build_portfolio_razem_row(summary, header)
        self.assertEqual(razem.iloc[0]["asset_id"], VENUE_TOTAL_ASSET_ID)
        self.assertEqual(float(razem.iloc[0]["terminal_unrealized"]), round(snapshot_nav))
        self.assertEqual(razem.iloc[0]["xirr"], header.xirr)
        self.assertEqual(razem.iloc[0]["xirr_pln"], header.xirr_pln)
        self.assertEqual(float(razem.iloc[0]["roi_nominal"]), round(header.roi_nominal_pln))
        self.assertEqual(float(razem.iloc[0]["capex"]), -4200.0)

    def test_portfolio_xirr_terminal_excludes_broker_cash(self):
        """Terminal XIRR = NAV pozycji (bez gotówki roboczej brokera)."""
        from evaluators.broker_snapshot import BrokerHoldings
        from importers.assets.data_model import AssetsDef

        rows = [
            build_ledger_row(
                instrument_id="p_degiro:AAA",
                event_date="2024-05-31",
                category=CAPEX,
                amount=-1000.0,
                currency="EUR",
                venue="degiro",
                fx_rates=_fx_frame(),
            ),
        ]
        assembly = AssemblyResult(
            ledger=pd.DataFrame(rows),
            coverage=[
                InstrumentCoverage("p_degiro:AAA", CoverageStatus.COVERED, venue="degiro"),
            ],
        )
        snapshot = pd.DataFrame(
            [
                {
                    AssetsDef.ID: "p_degiro",
                    AssetsDef.TYPE: "investment.udziały",
                    AssetsDef.VALUE: 1100.0,
                    AssetsDef.VALUE_PLN: 4400.0,
                    AssetsDef.CURRENCY: "EUR",
                }
            ]
        )
        holdings = {
            "p_degiro": BrokerHoldings(
                positions_value=1000.0,
                cash_value=100.0,
                n_positions=1,
                n_cash_rows=1,
                evaluation_date="2024-05-31",
                currency="EUR",
            )
        }
        result = compute_named_portfolio_xirr(
            PORTFOLIO_GM,
            date(2025, 1, 1),
            assembly=assembly,
            snapshot=snapshot,
            fx_rates=_fx_frame(),
            holdings_by_id=holdings,
        )
        # 4400 * 1000/1100 = 4000 pozycji
        self.assertAlmostEqual(result.terminal_pln, 4000.0, places=4)


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


class PortfolioCfAssembleInitTests(unittest.TestCase):
    def test_datastep_not_initialised_is_not_swallowed(self):
        with patch(
            "portfolio_cf.assemble.adapt_catalog_ledger",
            side_effect=ReferenceError("DataStep not initialised"),
        ):
            with self.assertRaises(ReferenceError):
                build_instrument_ledger(date(2026, 9, 25), snapshot=pd.DataFrame())


class PortfolioCfInstrumentSummaryTests(unittest.TestCase):
    def test_summary_matches_roi_columns_in_pln(self):
        from importers.assets.data_model import AssetsDef
        from portfolio_cf.instrument_summary import build_portfolio_instrument_summary
        from roi.aggregate_venue_roi import VENUE_TOTAL_ASSET_ID, aggregate_venue_roi

        rows = [
            build_ledger_row(
                instrument_id="horbaczewskiego",
                event_date="2020-01-01",
                category=CAPEX,
                amount=-100000.0,
                currency="PLN",
                venue="catalog",
                fx_rates=_fx_frame(),
            ),
            build_ledger_row(
                instrument_id="horbaczewskiego",
                event_date="2021-06-01",
                category=REVENUES,
                amount=5000.0,
                currency="PLN",
                venue="catalog",
                fx_rates=_fx_frame(),
            ),
            build_ledger_row(
                instrument_id="p_xtb:A",
                event_date="2024-01-01",
                category=CAPEX,
                amount=-1000.0,
                currency="PLN",
                venue="xtb",
                fx_rates=_fx_frame(),
            ),
        ]
        ledger = pd.DataFrame(rows)
        assembly = AssemblyResult(
            ledger=ledger,
            coverage=[
                InstrumentCoverage("horbaczewskiego", CoverageStatus.COVERED, venue="catalog"),
                InstrumentCoverage("p_xtb:A", CoverageStatus.COVERED, venue="xtb"),
            ],
            is_sold_by_instrument={"horbaczewskiego": False, "p_xtb:A": False},
        )
        snapshot = pd.DataFrame(
            [
                {
                    AssetsDef.ID: "horbaczewskiego",
                    AssetsDef.VALUE_PLN: 150000.0,
                    AssetsDef.EVALUATION_DATE: "2025-01-01",
                }
            ]
        )
        with (
            patch(
                "portfolio_cf.instrument_summary.load_gm_position_lines",
                return_value=([], []),
            ),
            patch(
                "portfolio_cf.instrument_summary._fill_terminals_from_venue_roi",
            ),
            patch(
                "portfolio_cf.instrument_summary._instrument_labels",
                return_value={
                    "horbaczewskiego": "horbaczewskiego",
                    "p_xtb:A": "Asset A",
                },
            ),
        ):
            summary, events, local_events = build_portfolio_instrument_summary(
                assembly,
                PORTFOLIO_NIERUCHOMOSCI,
                date(2025, 1, 1),
                snapshot=snapshot,
                sold_filter="Wszystkie",
                fx_rates=_fx_frame(),
            )

        self.assertEqual(list(summary["asset_id"]), ["horbaczewskiego"])
        self.assertEqual(float(summary.iloc[0]["capex"]), -100000.0)
        self.assertEqual(float(summary.iloc[0]["revenue"]), 5000.0)
        self.assertEqual(float(summary.iloc[0]["terminal_unrealized"]), 150000.0)
        self.assertEqual(float(summary.iloc[0]["roi_nominal"]), 55000.0)
        self.assertEqual(float(summary.iloc[0]["roi_fx"]), 0.0)
        self.assertEqual(float(summary.iloc[0]["fx_share"]), 0.0)
        self.assertIn("horbaczewskiego", events)
        self.assertIn("horbaczewskiego", local_events)

        total = aggregate_venue_roi(
            summary,
            events,
            date(2025, 1, 1),
            local_events_by_asset=local_events,
        )
        self.assertEqual(total.iloc[0]["asset_id"], VENUE_TOTAL_ASSET_ID)
        self.assertEqual(float(total.iloc[0]["capex"]), -100000.0)
        self.assertEqual(float(total.iloc[0]["roi_fx"]), 0.0)

    def test_sold_instrument_has_zero_unrealized_terminal(self):
        from portfolio_cf.instrument_summary import build_portfolio_instrument_summary

        rows = [
            build_ledger_row(
                instrument_id="horbaczewskiego",
                event_date="2020-01-01",
                category=CAPEX,
                amount=-100000.0,
                currency="PLN",
                venue="catalog",
                fx_rates=_fx_frame(),
            ),
            build_ledger_row(
                instrument_id="horbaczewskiego",
                event_date="2024-06-01",
                category=DIVESTMENT,
                amount=120000.0,
                currency="PLN",
                venue="catalog",
                fx_rates=_fx_frame(),
            ),
        ]
        assembly = AssemblyResult(
            ledger=pd.DataFrame(rows),
            coverage=[
                InstrumentCoverage("horbaczewskiego", CoverageStatus.COVERED, venue="catalog"),
            ],
            is_sold_by_instrument={"horbaczewskiego": True},
        )
        with (
            patch(
                "portfolio_cf.instrument_summary.load_gm_position_lines",
                return_value=([], []),
            ),
            patch(
                "portfolio_cf.instrument_summary._fill_terminals_from_venue_roi",
            ),
            patch(
                "portfolio_cf.instrument_summary._instrument_labels",
                return_value={"horbaczewskiego": "horbaczewskiego"},
            ),
        ):
            summary, _events, _local = build_portfolio_instrument_summary(
                assembly,
                PORTFOLIO_NIERUCHOMOSCI,
                date(2025, 1, 1),
                snapshot=pd.DataFrame(),
                sold_filter="Wszystkie",
                fx_rates=_fx_frame(),
            )
        self.assertEqual(float(summary.iloc[0]["terminal_unrealized"]), 0.0)
        self.assertEqual(float(summary.iloc[0]["terminal_realized"]), 120000.0)
        self.assertTrue(bool(summary.iloc[0]["is_sold"]))


if __name__ == "__main__":
    unittest.main()
