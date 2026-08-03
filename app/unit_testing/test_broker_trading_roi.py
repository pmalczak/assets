# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest
from datetime import date

import pandas as pd

from analyse_assets.account_tx import AccountTx
from importers.revolut.trading_data_model import RevolutTradingFile
from roi.broker_trading_roi import (
    TO_ROBO_TITLE,
    build_broker_ticker_cashflows,
    compute_broker_ticker_roi_from_trading,
    compute_revolut_robo_ticker_roi,
    reconcile_robo_top_up,
    ticker_open_state,
)
from roi.categories import CAPEX, DIVESTMENT, REVENUES
from roi.data_model import CashFlowEvent


def _row(
    *,
    dt: str,
    ticker: str,
    tx_type: str,
    qty,
    price,
    total,
    currency: str = "EUR",
) -> dict:
    return {
        RevolutTradingFile.DATE: dt,
        RevolutTradingFile.TICKER: ticker,
        RevolutTradingFile.TYPE: tx_type,
        RevolutTradingFile.QUANTITY: qty,
        RevolutTradingFile.PRICE_PER_SHARE: price,
        RevolutTradingFile.TOTAL_AMOUNT: total,
        RevolutTradingFile.CURRENCY: currency,
        RevolutTradingFile.FX_RATE: 1.0,
        RevolutTradingFile.FILE_DATE: "2026-06-30",
        RevolutTradingFile.PERIOD_START: "2026-01-01",
        RevolutTradingFile.PERIOD_END: "2026-06-30",
    }


class BrokerTickerCashflowTests(unittest.TestCase):
    def test_buy_sell_div_categories(self):
        trading = pd.DataFrame(
            [
                _row(
                    dt="2026-01-01T10:00:00Z",
                    ticker="PRAR",
                    tx_type=RevolutTradingFile.TYPE_BUY,
                    qty=10.0,
                    price=5.0,
                    total=-50.0,
                ),
                _row(
                    dt="2026-02-01T10:00:00Z",
                    ticker="PRAR",
                    tx_type=RevolutTradingFile.TYPE_SELL,
                    qty=-4.0,
                    price=6.0,
                    total=24.0,
                ),
                _row(
                    dt="2026-03-01T10:00:00Z",
                    ticker="PRAR",
                    tx_type=RevolutTradingFile.TYPE_DIVIDEND,
                    qty="",
                    price="",
                    total=1.5,
                ),
                _row(
                    dt="2026-01-15T10:00:00Z",
                    ticker="",
                    tx_type=RevolutTradingFile.TYPE_CASH_TOP_UP,
                    qty="",
                    price="",
                    total=100.0,
                ),
            ]
        )
        events = build_broker_ticker_cashflows(trading, "p_re_robo")
        self.assertEqual(set(events), {"p_re_robo:PRAR"})
        df = events["p_re_robo:PRAR"]
        cats = df[CashFlowEvent.CATEGORY].tolist()
        self.assertEqual(cats, [CAPEX, DIVESTMENT, REVENUES])
        self.assertAlmostEqual(float(df.iloc[0][CashFlowEvent.AMOUNT]), -50.0)
        self.assertAlmostEqual(float(df.iloc[1][CashFlowEvent.AMOUNT]), 24.0)
        self.assertAlmostEqual(float(df.iloc[2][CashFlowEvent.AMOUNT]), 1.5)


class BrokerTickerRoiTests(unittest.TestCase):
    def test_partial_sell_open_terminal_last_price(self):
        trading = pd.DataFrame(
            [
                _row(
                    dt="2026-01-01T00:00:00Z",
                    ticker="AAA",
                    tx_type=RevolutTradingFile.TYPE_BUY,
                    qty=10.0,
                    price=10.0,
                    total=-100.0,
                ),
                _row(
                    dt="2026-02-01T00:00:00Z",
                    ticker="AAA",
                    tx_type=RevolutTradingFile.TYPE_SELL,
                    qty=-4.0,
                    price=12.0,
                    total=48.0,
                ),
            ]
        )
        state = ticker_open_state(trading)
        self.assertAlmostEqual(state["AAA"]["qty"], 6.0)
        self.assertAlmostEqual(state["AAA"]["last_price"], 12.0)

        summary, events = compute_broker_ticker_roi_from_trading(
            trading, date(2026, 6, 1), "p_re_robo"
        )
        self.assertEqual(len(summary), 1)
        row = summary.iloc[0]
        self.assertEqual(row["asset_id"], "p_re_robo:AAA")
        self.assertFalse(bool(row["is_sold"]))
        self.assertAlmostEqual(float(row["terminal_unrealized"]), 72.0)  # 6×12
        self.assertAlmostEqual(float(row["capex"]), -100.0)
        self.assertAlmostEqual(float(row["revenue"]), 0.0)
        self.assertAlmostEqual(float(row["terminal_realized"]), 48.0)
        self.assertEqual(events["p_re_robo:AAA"][CashFlowEvent.CATEGORY].tolist(), [CAPEX, DIVESTMENT])
        self.assertIn("p_re_robo:AAA", events)

    def test_full_sell_is_sold_zero_terminal(self):
        trading = pd.DataFrame(
            [
                _row(
                    dt="2026-01-01T00:00:00Z",
                    ticker="BBB",
                    tx_type=RevolutTradingFile.TYPE_BUY,
                    qty=2.0,
                    price=20.0,
                    total=-40.0,
                ),
                _row(
                    dt="2026-03-01T00:00:00Z",
                    ticker="BBB",
                    tx_type=RevolutTradingFile.TYPE_SELL,
                    qty=-2.0,
                    price=25.0,
                    total=50.0,
                ),
            ]
        )
        summary, _ = compute_broker_ticker_roi_from_trading(
            trading, date(2026, 6, 1), "p_re_robo"
        )
        row = summary.iloc[0]
        self.assertTrue(bool(row["is_sold"]))
        self.assertAlmostEqual(float(row["terminal_unrealized"]), 0.0)
        self.assertAlmostEqual(float(row["terminal_realized"]), 50.0)
        self.assertAlmostEqual(float(row["roi_nominal"]), 10.0)  # -40 + 50

    def test_dividend_inflow(self):
        trading = pd.DataFrame(
            [
                _row(
                    dt="2026-01-01T00:00:00Z",
                    ticker="CCC",
                    tx_type=RevolutTradingFile.TYPE_BUY,
                    qty=1.0,
                    price=100.0,
                    total=-100.0,
                ),
                _row(
                    dt="2026-04-01T00:00:00Z",
                    ticker="CCC",
                    tx_type=RevolutTradingFile.TYPE_DIVIDEND,
                    qty="",
                    price="",
                    total=3.0,
                ),
            ]
        )
        summary, _ = compute_broker_ticker_roi_from_trading(
            trading, date(2026, 6, 1), "p_re_robo"
        )
        row = summary.iloc[0]
        self.assertAlmostEqual(float(row["revenue"]), 3.0)
        self.assertFalse(bool(row["is_sold"]))
        self.assertAlmostEqual(float(row["terminal_unrealized"]), 100.0)


class ReconcileRoboTests(unittest.TestCase):
    def test_reconcile_match_and_mismatch(self):
        trading = pd.DataFrame(
            [
                _row(
                    dt="2026-01-10T00:00:00Z",
                    ticker="",
                    tx_type=RevolutTradingFile.TYPE_CASH_TOP_UP,
                    qty="",
                    price="",
                    total=500.0,
                ),
                _row(
                    dt="2026-02-10T00:00:00Z",
                    ticker="",
                    tx_type=RevolutTradingFile.TYPE_CASH_TOP_UP,
                    qty="",
                    price="",
                    total=100.0,
                ),
            ]
        )
        pool_ok = pd.DataFrame(
            [
                {
                    AccountTx.TRANSACTION_DATE: "2026-01-10",
                    AccountTx.TITLE: TO_ROBO_TITLE,
                    AccountTx.AMOUNT: -500.0,
                },
                {
                    AccountTx.TRANSACTION_DATE: "2026-02-10",
                    AccountTx.TITLE: "To Robo portfolio",
                    AccountTx.AMOUNT: -100.0,
                },
            ]
        )
        self.assertEqual(
            reconcile_robo_top_up(trading, pool_ok, valuation_date=date(2026, 6, 1)),
            [],
        )

        pool_bad = pool_ok.copy()
        pool_bad.loc[1, AccountTx.AMOUNT] = -50.0
        warnings = reconcile_robo_top_up(
            trading, pool_bad, valuation_date=date(2026, 6, 1)
        )
        self.assertEqual(len(warnings), 1)
        self.assertIn("mismatch", warnings[0])

    def test_compute_api_includes_reconcile_warning(self):
        trading = pd.DataFrame(
            [
                _row(
                    dt="2026-01-01T00:00:00Z",
                    ticker="ZZZ",
                    tx_type=RevolutTradingFile.TYPE_BUY,
                    qty=1.0,
                    price=10.0,
                    total=-10.0,
                ),
                _row(
                    dt="2026-01-02T00:00:00Z",
                    ticker="",
                    tx_type=RevolutTradingFile.TYPE_CASH_TOP_UP,
                    qty="",
                    price="",
                    total=10.0,
                ),
            ]
        )
        pool = pd.DataFrame(
            [
                {
                    AccountTx.TRANSACTION_DATE: "2026-01-02",
                    AccountTx.TITLE: TO_ROBO_TITLE,
                    AccountTx.AMOUNT: -1.0,
                }
            ]
        )
        summary, events, warnings = compute_revolut_robo_ticker_roi(
            date(2026, 6, 1),
            trading_df=trading,
            pool_tx=pool,
        )
        self.assertEqual(len(summary), 1)
        self.assertIn("p_re_robo:ZZZ", events)
        self.assertTrue(any("mismatch" in w for w in warnings))


if __name__ == "__main__":
    unittest.main()
