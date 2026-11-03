# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest
from datetime import date

import pandas as pd

from analyse_assets.account_tx import AccountTx
from importers.degiro.data_model import DegiroAccountFile
from importers.revolut.deposit_data_model import RevolutDepositFile
from importers.revolut.savings_statement import OPIS_DEPOSIT, OPIS_WITHDRAWAL
from importers.revolut.trading_data_model import RevolutTradingFile
from importers.traderepublic.data_model import TradeRepublicFile
from importers.xtb.data_model import XtbCashOperationsFile
from roi.broker_trading_roi import TO_ROBO_TITLE
from roi.funding_report import (
    STATUS_MISMATCH,
    STATUS_OK,
    TO_DEGIRO_TITLE,
    build_funding_report,
)


def _pool_row(
    *,
    title: str,
    amount: float,
    tx_date: str = "2026-06-01",
    account_id: str = "p_re_eur",
    counterparty: str = "",
) -> dict:
    return {
        AccountTx.TRANSACTION_DATE: tx_date,
        AccountTx.TITLE: title,
        AccountTx.AMOUNT: amount,
        AccountTx.ACCOUNT_ID: account_id,
        AccountTx.COUNTERPARTY: counterparty,
    }


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
        self.assertEqual(by_id.loc["xtb_mbank", "status"], STATUS_OK)
        self.assertAlmostEqual(float(by_id.loc["xtb_mbank", "amount_a"]), 21420.0)
        self.assertAlmostEqual(float(by_id.loc["xtb_mbank", "amount_b"]), 21420.0)
        self.assertEqual(by_id.loc["traderepublic", "status"], STATUS_OK)
        self.assertEqual(by_id.loc["savings_deposit:p_re_eur", "status"], STATUS_OK)
        self.assertEqual(by_id.loc["savings_deposit:p_re_pln", "status"], STATUS_OK)
        self.assertEqual(by_id.loc["savings_withdraw:p_re_pln", "status"], STATUS_OK)
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
        empty = pd.DataFrame()
        report, warnings = build_funding_report(
            date(2026, 11, 1),
            revolut_eur_pool=eur_pool,
            revolut_pln_pool=empty,
            mbank_pln_pool=empty,
            robo_trading=trading,
            degiro_account=empty,
            xtb_cash=empty,
            traderepublic=empty,
            savings_by_account={aid: empty for aid in (
                "p_re_eur", "p_re_pln", "g_re_eur", "g_re_pln"
            )},
        )
        self.assertEqual(
            report.set_index("corridor").loc["robo", "status"], STATUS_MISMATCH
        )
        self.assertTrue(any("Robo" in w and "mismatch" in w for w in warnings))


if __name__ == "__main__":
    unittest.main()
