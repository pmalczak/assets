# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest
from datetime import date

import pandas as pd

from analyse_assets.account_tx import AccountTx
from importers.degiro.data_model import DegiroAccountFile
from importers.mbank.data_model import MbankOperationType
from importers.revolut.deposit_data_model import RevolutDepositFile
from importers.revolut.savings_statement import OPIS_DEPOSIT, OPIS_WITHDRAWAL
from importers.revolut.trading_data_model import RevolutTradingFile
from importers.traderepublic.data_model import TradeRepublicFile
from importers.xtb.data_model import XtbCashOperationsFile
from roi.broker_trading_roi import TO_ROBO_TITLE
from roi.funding_report import (
    MATCH_KIND_A_ONLY,
    MATCH_KIND_B_ONLY,
    MATCH_KIND_EXACT,
    MATCH_KIND_SETTLEMENT,
    STATUS_MISMATCH,
    STATUS_OK,
    TO_DEGIRO_TITLE,
    FlowLeg,
    build_funding_report,
    match_flow_legs,
    matched_legs_frame,
    parse_flow_legs,
)


def _pool_row(
    *,
    title: str,
    amount: float,
    tx_date: str = "2026-06-01",
    account_id: str = "p_re_eur",
    counterparty: str = "",
    operation_type: str = "",
    account_number: str = "",
) -> dict:
    return {
        AccountTx.TRANSACTION_DATE: tx_date,
        AccountTx.TITLE: title,
        AccountTx.AMOUNT: amount,
        AccountTx.ACCOUNT_ID: account_id,
        AccountTx.COUNTERPARTY: counterparty,
        AccountTx.OPERATION_TYPE: operation_type,
        AccountTx.ACCOUNT_NUMBER: account_number,
    }


def _empty_pools_kwargs(**overrides) -> dict:
    empty = pd.DataFrame()
    base = {
        "revolut_eur_pool": empty,
        "revolut_pln_pool": empty,
        "mbank_pln_pool": empty,
        "mbank_eur_pool": empty,
        "robo_trading": empty,
        "degiro_account": empty,
        "xtb_cash": empty,
        "traderepublic": empty,
        "savings_by_account": {
            aid: empty for aid in ("p_re_eur", "p_re_pln", "g_re_eur", "g_re_pln")
        },
    }
    base.update(overrides)
    return base


def _trading_top_up(total: float, dt: str = "2026-06-01T00:00:00Z") -> dict:
    return {
        RevolutTradingFile.DATE: dt,
        RevolutTradingFile.TICKER: "",
        RevolutTradingFile.TYPE: RevolutTradingFile.TYPE_CASH_TOP_UP,
        RevolutTradingFile.QUANTITY: "",
        RevolutTradingFile.PRICE_PER_SHARE: "",
        RevolutTradingFile.TOTAL_AMOUNT: total,
        RevolutTradingFile.CURRENCY: "EUR",
        RevolutTradingFile.FX_RATE: 1.0,
        RevolutTradingFile.FILE_DATE: "2026-06-01",
        RevolutTradingFile.PERIOD_START: "2026-01-01",
        RevolutTradingFile.PERIOD_END: "2026-06-30",
    }


class FundingReportTests(unittest.TestCase):
    def test_all_corridors_ok_with_fixtures(self):
        eur_pool = pd.DataFrame(
            [
                _pool_row(title=TO_ROBO_TITLE, amount=-500.0),
                _pool_row(title=TO_DEGIRO_TITLE, amount=-15000.0, tx_date="2026-08-14"),
                _pool_row(
                    title="Depositing savings",
                    amount=-1000.0,
                    tx_date="2025-08-20",
                    account_id="p_re_eur",
                ),
            ]
        )
        pln_pool = pd.DataFrame(
            [
                _pool_row(
                    title="XTB",
                    amount=-100.0,
                    tx_date="2026-09-30",
                    account_id="p_re_pln",
                ),
                _pool_row(
                    title="Trade Republic",
                    amount=-400.0,
                    tx_date="2026-07-22",
                    account_id="p_re_pln",
                ),
                _pool_row(
                    title="Depositing savings",
                    amount=-100.0,
                    tx_date="2025-08-20",
                    account_id="p_re_pln",
                ),
                _pool_row(
                    title="Withdrawing savings",
                    amount=100.0,
                    tx_date="2025-11-05",
                    account_id="p_re_pln",
                ),
            ]
        )
        mbank_pln = pd.DataFrame(
            [
                _pool_row(
                    title="PRZELEW ŚRODKÓW",
                    amount=-100.0,
                    tx_date="2020-10-04",
                    account_id="p_m_23_2330",
                    counterparty="STICHTING DEGIRO",
                ),
                _pool_row(
                    title="PRZELEW ŚRODKÓW",
                    amount=-2900.0,
                    tx_date="2021-05-26",
                    account_id="p_m_23_2330",
                    counterparty="STICHTING DEGIRO",
                ),
                _pool_row(
                    title="55260027",
                    amount=-21420.0,
                    tx_date="2026-09-02",
                    account_id="p_m_23_2330",
                    counterparty="XTB SPOLKA AKCYJNA",
                ),
            ]
        )
        trading = pd.DataFrame([_trading_top_up(500.0)])
        degiro = pd.DataFrame(
            [
                {
                    DegiroAccountFile.BOOKING_DATE: "14-08-2026",
                    DegiroAccountFile.DESCRIPTION: "Depozyt",
                    DegiroAccountFile.CHANGE: 15000.0,
                    DegiroAccountFile.CHANGE_CURRENCY: "EUR",
                },
                {
                    DegiroAccountFile.BOOKING_DATE: "05-10-2020",
                    DegiroAccountFile.DESCRIPTION: "Depozyt",
                    DegiroAccountFile.CHANGE: 100.0,
                    DegiroAccountFile.CHANGE_CURRENCY: "PLN",
                },
                {
                    DegiroAccountFile.BOOKING_DATE: "27-05-2021",
                    DegiroAccountFile.DESCRIPTION: "Depozyt",
                    DegiroAccountFile.CHANGE: 2900.0,
                    DegiroAccountFile.CHANGE_CURRENCY: "PLN",
                },
            ]
        )
        xtb_cash = pd.DataFrame(
            [
                {
                    XtbCashOperationsFile.TIME: "2026-09-30 08:54:50",
                    XtbCashOperationsFile.TYPE: "Deposit",
                    XtbCashOperationsFile.AMOUNT: 100.0,
                    XtbCashOperationsFile.COMMENT: "Adyen Cards deposit",
                },
                {
                    XtbCashOperationsFile.TIME: "2026-09-03 10:16:03",
                    XtbCashOperationsFile.TYPE: "Deposit",
                    XtbCashOperationsFile.AMOUNT: 21420.0,
                    XtbCashOperationsFile.COMMENT: "Pekao S.A. deposit",
                },
            ]
        )
        tr = pd.DataFrame(
            [
                {
                    TradeRepublicFile.DATE: "2026-07-22",
                    TradeRepublicFile.TYPE: TradeRepublicFile.TYPE_CUSTOMER_INPAYMENT,
                    TradeRepublicFile.AMOUNT: 400.0,
                }
            ]
        )
        savings = {
            "p_re_eur": pd.DataFrame(
                [
                    {
                        RevolutDepositFile.DATE: "2025-08-20",
                        RevolutDepositFile.DESCRIPTION: OPIS_DEPOSIT,
                        RevolutDepositFile.MONEY_IN: 1000.0,
                        RevolutDepositFile.MONEY_OUT: None,
                    }
                ]
            ),
            "p_re_pln": pd.DataFrame(
                [
                    {
                        RevolutDepositFile.DATE: "2025-08-20",
                        RevolutDepositFile.DESCRIPTION: OPIS_DEPOSIT,
                        RevolutDepositFile.MONEY_IN: 100.0,
                        RevolutDepositFile.MONEY_OUT: None,
                    },
                    {
                        RevolutDepositFile.DATE: "2025-11-05",
                        RevolutDepositFile.DESCRIPTION: OPIS_WITHDRAWAL,
                        RevolutDepositFile.MONEY_IN: None,
                        RevolutDepositFile.MONEY_OUT: 100.0,
                    },
                ]
            ),
            "g_re_eur": pd.DataFrame(),
            "g_re_pln": pd.DataFrame(),
        }

        report, warnings = build_funding_report(
            date(2026, 11, 1),
            revolut_eur_pool=eur_pool,
            revolut_pln_pool=pln_pool,
            mbank_pln_pool=mbank_pln,
            mbank_eur_pool=pd.DataFrame(),
            robo_trading=trading,
            degiro_account=degiro,
            xtb_cash=xtb_cash,
            traderepublic=tr,
            savings_by_account=savings,
        )

        by_id = report.set_index("corridor")
        self.assertEqual(by_id.loc["robo", "status"], STATUS_OK)
        self.assertEqual(by_id.loc["degiro_revolut", "status"], STATUS_OK)
        self.assertEqual(by_id.loc["degiro_mbank", "status"], STATUS_OK)
        self.assertAlmostEqual(float(by_id.loc["degiro_mbank", "amount_a"]), 3000.0)
        self.assertAlmostEqual(float(by_id.loc["degiro_mbank", "amount_b"]), 3000.0)
        self.assertEqual(by_id.loc["xtb_adyen", "status"], STATUS_OK)
        self.assertEqual(
            by_id.loc["xtb_adyen", "side_a"], "revolut_pln: |Revolut XTB|"
        )
        self.assertEqual(by_id.loc["xtb_adyen", "side_b"], "p_xtb: Adyen Deposit")
        self.assertEqual(by_id.loc["xtb_mbank", "status"], STATUS_OK)
        self.assertEqual(
            by_id.loc["xtb_mbank", "side_a"], "mbank_pln: |XTB 55260027|"
        )
        self.assertEqual(by_id.loc["robo", "side_a"], "revolut_eur: |To Robo portfolio|")
        self.assertEqual(by_id.loc["robo", "side_b"], "p_re_robo: CASH TOP-UP")
        self.assertAlmostEqual(float(by_id.loc["xtb_mbank", "amount_a"]), 21420.0)
        self.assertAlmostEqual(float(by_id.loc["xtb_mbank", "amount_b"]), 21420.0)
        self.assertEqual(by_id.loc["traderepublic", "status"], STATUS_OK)
        self.assertEqual(by_id.loc["savings_deposit:p_re_eur", "status"], STATUS_OK)
        self.assertEqual(by_id.loc["savings_deposit:p_re_pln", "status"], STATUS_OK)
        self.assertEqual(by_id.loc["savings_withdraw:p_re_pln", "status"], STATUS_OK)
        self.assertEqual(by_id.loc["mbank_revolut_pln", "status"], STATUS_OK)
        self.assertEqual(by_id.loc["mbank_revolut_eur", "status"], STATUS_OK)
        self.assertAlmostEqual(float(by_id.loc["mbank_revolut_pln", "amount_a"]), 0.0)
        self.assertAlmostEqual(float(by_id.loc["mbank_revolut_eur", "amount_a"]), 0.0)
        self.assertIn("2026-08-14: 15000.00", str(by_id.loc["degiro_revolut", "tx_a"]))
        self.assertIn("2026-08-14: 15000.00", str(by_id.loc["degiro_revolut", "tx_b"]))
        self.assertIn("2020-10-04: 100.00", str(by_id.loc["degiro_mbank", "tx_a"]))
        self.assertIn("2020-10-05: 100.00", str(by_id.loc["degiro_mbank", "tx_b"]))
        self.assertIn("2026-09-30: 100.00", str(by_id.loc["xtb_adyen", "tx_a"]))
        self.assertIn("2026-09-02: 21420.00", str(by_id.loc["xtb_mbank", "tx_a"]))
        self.assertIn("2026-09-03: 21420.00", str(by_id.loc["xtb_mbank", "tx_b"]))
        self.assertFalse(any("mismatch" in w for w in warnings))

    def test_robo_mismatch_surfaces_warning(self):
        eur_pool = pd.DataFrame([_pool_row(title=TO_ROBO_TITLE, amount=-500.0)])
        trading = pd.DataFrame([_trading_top_up(100.0)])
        report, warnings = build_funding_report(
            date(2026, 11, 1),
            **_empty_pools_kwargs(
                revolut_eur_pool=eur_pool,
                robo_trading=trading,
            ),
        )
        self.assertEqual(
            report.set_index("corridor").loc["robo", "status"], STATUS_MISMATCH
        )
        self.assertTrue(any("Robo" in w and "mismatch" in w for w in warnings))

    def test_mbank_revolut_pln_transfer_and_card_ok(self):
        mbank_pln = pd.DataFrame(
            [
                _pool_row(
                    title="PRZELEW WŁASNY",
                    amount=-600.0,
                    tx_date="2026-10-28",
                    account_id="g_m_46_2796",
                    counterparty="REVOLUT MALGORZATA MALCZAK",
                    operation_type=MbankOperationType.PRZELEW_ZEWNETRZNY_WYCHODZACY,
                ),
                _pool_row(
                    title="Wyslano z Revolut /LT873250088062429561",
                    amount=15800.0,
                    tx_date="2026-09-01",
                    account_id="p_m_23_2330",
                    counterparty="Revolut Bank UAB",
                    operation_type=MbankOperationType.PRZELEW_ZEWNETRZNY_PRZYCHODZACY,
                ),
                _pool_row(
                    title="Revolut**9746* /Dublin DATA TRANSAKCJI: 2026-01-03",
                    amount=-1500.0,
                    tx_date="2026-01-05",
                    account_id="p_m_23_2330",
                    operation_type=MbankOperationType.ZAKUP_PRZY_UZYCIU_KARTY,
                ),
                # Historyczny merchant REVO* (bez pełnego „revolut” w tytule).
                _pool_row(
                    title="REVO*PIOTRMALCZAK  /GBR DATA TRANSAKCJI: 2020-09-21",
                    amount=-500.0,
                    tx_date="2020-09-23",
                    account_id="p_m_23_2330",
                    operation_type=MbankOperationType.ZAKUP_PRZY_UZYCIU_KARTY,
                ),
                # Express Elixir: tytuł „Wplata wlasna”, bez „Revolut” — rachunek kanału Revolut.
                _pool_row(
                    title="/ref/281475553881914/Wplata wlasna",
                    amount=50000.0,
                    tx_date="2026-08-31",
                    account_id="g_m_46_2796",
                    counterparty="Piotr Malczak  DOB 1967-09-14 PL Wroclaw",
                    operation_type=MbankOperationType.PRZELEW_EXPRESS_ELIXIR_PRZYCH,
                    account_number="58109028510000000147575158",
                ),
            ]
        )
        revolut_pln = pd.DataFrame(
            [
                _pool_row(
                    title="Płatność od MAŁGORZATA MALCZAK",
                    amount=600.0,
                    tx_date="2026-10-28",
                    account_id="g_re_pln",
                ),
                _pool_row(
                    title="To Piotr Bernard Malczak",
                    amount=-15800.0,
                    tx_date="2026-08-31",
                    account_id="p_re_pln",
                ),
                _pool_row(
                    title="To Małgorzata Malczak",
                    amount=-50000.0,
                    tx_date="2026-08-31",
                    account_id="p_re_pln",
                ),
                _pool_row(
                    title="Zasilenie o *5896",
                    amount=1500.0,
                    tx_date="2026-01-05",
                    account_id="p_re_pln",
                ),
                _pool_row(
                    title="Zasilenie o *5896",
                    amount=500.0,
                    tx_date="2020-09-21",
                    account_id="p_re_pln",
                ),
                # obce / venue — poza korytarzem
                _pool_row(
                    title="To Piotr Chrobot",
                    amount=-135.0,
                    tx_date="2026-11-08",
                    account_id="p_re_pln",
                ),
                _pool_row(
                    title="XTB",
                    amount=-100.0,
                    tx_date="2026-09-30",
                    account_id="p_re_pln",
                ),
            ]
        )
        report, warnings = build_funding_report(
            date(2026, 11, 1),
            **_empty_pools_kwargs(
                mbank_pln_pool=mbank_pln,
                revolut_pln_pool=revolut_pln,
            ),
        )
        row = report.set_index("corridor").loc["mbank_revolut_pln"]
        self.assertEqual(row["status"], STATUS_OK)
        self.assertAlmostEqual(float(row["amount_a"]), 68400.0)
        self.assertAlmostEqual(float(row["amount_b"]), 68400.0)
        self.assertIn("2026-10-28: 600.00", str(row["tx_a"]))
        self.assertIn("2026-01-05: 1500.00", str(row["tx_a"]))
        self.assertIn("2020-09-23: 500.00", str(row["tx_a"]))
        self.assertIn("2026-08-31: 50000.00", str(row["tx_a"]))
        self.assertIn("2020-09-21: 500.00", str(row["tx_b"]))
        self.assertIn("2026-08-31: 50000.00", str(row["tx_b"]))
        self.assertIn("2026-10-28: 600.00", str(row["tx_b"]))
        self.assertNotIn("135.00", str(row["tx_b"]))
        self.assertFalse(any("mBank ↔ Revolut PLN" in w and "mismatch" in w for w in warnings))

    def test_mbank_revolut_eur_sepa_ok(self):
        mbank_eur = pd.DataFrame(
            [
                _pool_row(
                    title="PRZELEW SRODKOW",
                    amount=-50000.0,
                    tx_date="2026-09-17",
                    account_id="p_m_63_3209_eur",
                    counterparty="PIOTR-KONTO WALUTOWE REVOLUT",
                    operation_type=MbankOperationType.PRZELEW_SEPA_WYCHODZACY,
                    account_number="LT873250088062429561",
                ),
                # Bez „Revolut” w kontrahencie — tylko IBAN LT##32500…
                _pool_row(
                    title="PRZELEW SRODKOW",
                    amount=-1000.0,
                    tx_date="2025-08-20",
                    account_id="p_m_63_3209_eur",
                    counterparty="PIOTR MALCZAK",
                    operation_type=MbankOperationType.PRZELEW_SEPA_WYCHODZACY,
                    account_number="LT873250088062429561",
                ),
            ]
        )
        revolut_eur = pd.DataFrame(
            [
                _pool_row(
                    title="Płatność od PIOTR MALCZAK",
                    amount=50000.0,
                    tx_date="2026-09-18",
                    account_id="p_re_eur",
                ),
                _pool_row(
                    title="Płatność od PIOTR MALCZAK",
                    amount=1000.0,
                    tx_date="2025-08-20",
                    account_id="p_re_eur",
                ),
            ]
        )
        report, _warnings = build_funding_report(
            date(2026, 11, 1),
            **_empty_pools_kwargs(
                mbank_eur_pool=mbank_eur,
                revolut_eur_pool=revolut_eur,
            ),
        )
        row = report.set_index("corridor").loc["mbank_revolut_eur"]
        self.assertEqual(row["status"], STATUS_OK)
        self.assertAlmostEqual(float(row["amount_a"]), 51000.0)
        self.assertAlmostEqual(float(row["amount_b"]), 51000.0)
        self.assertIn("2025-08-20: 1000.00", str(row["tx_a"]))
        self.assertIn("2025-08-20: 1000.00", str(row["tx_b"]))
        self.assertEqual(row["side_a"], "mbank_eur: |Revolut przelew/karta|")
        self.assertEqual(row["side_b"], "revolut_eur: |mBank przelew/karta|")

    def test_mbank_revolut_mismatch_surfaces_warning(self):
        mbank_pln = pd.DataFrame(
            [
                _pool_row(
                    title="PRZELEW WŁASNY",
                    amount=-600.0,
                    tx_date="2026-10-28",
                    account_id="g_m_46_2796",
                    counterparty="REVOLUT MALGORZATA MALCZAK",
                    operation_type=MbankOperationType.PRZELEW_ZEWNETRZNY_WYCHODZACY,
                ),
            ]
        )
        report, warnings = build_funding_report(
            date(2026, 11, 1),
            **_empty_pools_kwargs(mbank_pln_pool=mbank_pln),
        )
        row = report.set_index("corridor").loc["mbank_revolut_pln"]
        self.assertEqual(row["status"], STATUS_MISMATCH)
        self.assertTrue(
            any("mBank ↔ Revolut PLN" in w and "mismatch" in w for w in warnings)
        )

    def test_mbank_revolut_excludes_degiro_xtb_legs(self):
        mbank_pln = pd.DataFrame(
            [
                _pool_row(
                    title="PRZELEW ŚRODKÓW",
                    amount=-100.0,
                    tx_date="2020-10-04",
                    account_id="p_m_23_2330",
                    counterparty="STICHTING DEGIRO",
                ),
                _pool_row(
                    title="55260027",
                    amount=-21420.0,
                    tx_date="2026-09-02",
                    account_id="p_m_23_2330",
                    counterparty="XTB SPOLKA AKCYJNA",
                ),
            ]
        )
        report, _warnings = build_funding_report(
            date(2026, 11, 1),
            **_empty_pools_kwargs(mbank_pln_pool=mbank_pln),
        )
        row = report.set_index("corridor").loc["mbank_revolut_pln"]
        self.assertEqual(row["status"], STATUS_OK)
        self.assertAlmostEqual(float(row["amount_a"]), 0.0)


class MatchFlowLegsTests(unittest.TestCase):
    def test_exact_date_and_amount(self):
        pairs = match_flow_legs(
            [FlowLeg("2026-08-14", 15000.0)],
            [FlowLeg("2026-08-14", 15000.0)],
        )
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0].match, MATCH_KIND_EXACT)
        self.assertEqual(pairs[0].date_skew_days, 0)

    def test_settlement_date_skew_within_window(self):
        pairs = match_flow_legs(
            [FlowLeg("2020-10-04", 100.0)],
            [FlowLeg("2020-10-05", 100.0)],
        )
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0].match, MATCH_KIND_SETTLEMENT)
        self.assertEqual(pairs[0].date_skew_days, 1)

    def test_unmatched_when_skew_too_large(self):
        pairs = match_flow_legs(
            [FlowLeg("2026-01-01", 50.0)],
            [FlowLeg("2026-02-01", 50.0)],
            max_date_skew_days=7,
        )
        kinds = {p.match for p in pairs}
        self.assertEqual(kinds, {MATCH_KIND_A_ONLY, MATCH_KIND_B_ONLY})

    def test_matched_legs_frame_from_tx_strings(self):
        frame = matched_legs_frame(
            "2026-09-02: 21420.00",
            "2026-09-03: 21420.00",
        )
        self.assertEqual(len(frame), 1)
        self.assertEqual(frame.iloc[0]["match"], MATCH_KIND_SETTLEMENT)
        self.assertEqual(int(frame.iloc[0]["date_skew_days"]), 1)

    def test_parse_roundtrip(self):
        legs = [FlowLeg("2026-01-02", 10.5), FlowLeg("2026-01-01", 3.0)]
        from roi.funding_report import format_flow_legs

        parsed = parse_flow_legs(format_flow_legs(legs))
        self.assertEqual([(p.date, p.amount) for p in parsed], [
            ("2026-01-02", 10.5),
            ("2026-01-01", 3.0),
        ])

    def test_matched_legs_newest_first(self):
        pairs = match_flow_legs(
            [FlowLeg("2026-01-01", 10.0), FlowLeg("2026-09-01", 20.0)],
            [FlowLeg("2026-01-01", 10.0), FlowLeg("2026-09-01", 20.0)],
        )
        dates = [p.date_a or p.date_b for p in pairs]
        self.assertEqual(dates, ["2026-09-01", "2026-01-01"])


if __name__ == "__main__":
    unittest.main()
