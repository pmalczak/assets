# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest
from datetime import date

import pandas as pd

from importers.broker.data_model import (
    Account,
    BrokerCashBalanceFrame,
    BrokerCashFlowFrame,
    BrokerPositionFrame,
    BrokerTransactionFrame,
    CashBalance,
    CashFlow,
    CashFlowType,
    Position,
    Transaction,
    TransactionType,
)
from importers.degiro.normalize import (
    normalize_degiro_cash_balances,
    normalize_degiro_cashflows,
    normalize_degiro_positions,
    normalize_degiro_transactions,
)


class BrokerModelTests(unittest.TestCase):
    def test_dataclasses_cover_required_entities(self):
        account = Account("DEGIRO", "p_degiro", "EUR")
        position = Position("DEGIRO", "p_degiro", "ETF", "", "IE00", 2.0, None, "EUR", 100.0)
        tx = Transaction(
            "DEGIRO",
            "p_degiro",
            date(2026, 1, 2),
            "ETF",
            "",
            "IE00",
            TransactionType.BUY,
            2.0,
            50.0,
            "EUR",
            -100.0,
        )
        flow = CashFlow("DEGIRO", "p_degiro", date(2026, 1, 3), CashFlowType.DIVIDEND, 1.0, "EUR")
        balance = CashBalance("DEGIRO", "p_degiro", "EUR", 10.0)

        self.assertEqual(account.base_currency, "EUR")
        self.assertEqual(position.isin, "IE00")
        self.assertEqual(tx.type, TransactionType.BUY)
        self.assertEqual(flow.type, CashFlowType.DIVIDEND)
        self.assertEqual(balance.amount, 10.0)


class DegiroNormalizationTests(unittest.TestCase):
    def test_normalizes_degiro_frames_to_broker_model(self):
        portfolio = pd.DataFrame(
            [
                {
                    "Produkt": "CASH & CASH FUND & FTX CASH (EUR)",
                    "Symbol/ISIN": "",
                    "Suma": None,
                    "Kurs": None,
                    "local_currency": "EUR",
                    "Lokalna wartość": 30.12,
                    "Wartość w EUR": 30.12,
                    "period_end": "2025-10-09",
                },
                {
                    "Produkt": "INTER RAO LIETUVA AB",
                    "Symbol/ISIN": "LT0000128621",
                    "Suma": 150.0,
                    "Kurs": 11.54,
                    "local_currency": "PLN",
                    "Lokalna wartość": 1731.0,
                    "Wartość w EUR": 402.28,
                    "period_end": "2025-10-09",
                },
            ]
        )
        transactions = pd.DataFrame(
            [
                {
                    "Data": "28-07-2021",
                    "Produkt": "INTER RAO LIETUVA AB",
                    "ISIN": "LT0000128621",
                    "Liczba": 150.0,
                    "Kurs": 19.5,
                    "Wartość EUR": -635.97,
                    "Opłata transakcyjna DEGIRO i/lub opłata stron": -0.79,
                    "Identyfikator zlecenia": "order-1",
                }
            ]
        )
        account = pd.DataFrame(
            [
                {
                    "booking_date": "01-09-2021",
                    "description": "Dywidenda",
                    "change": 5.0,
                    "change_currency": "EUR",
                    "order_id": "",
                }
            ]
        )

        positions = normalize_degiro_positions(portfolio)
        tx = normalize_degiro_transactions(transactions)
        flows = normalize_degiro_cashflows(account)
        cash = normalize_degiro_cash_balances(portfolio)

        BrokerPositionFrame.check_structure(positions)
        BrokerTransactionFrame.check_structure(tx)
        BrokerCashFlowFrame.check_structure(flows)
        BrokerCashBalanceFrame.check_structure(cash)
        self.assertEqual(len(positions), 1)
        self.assertEqual(positions.iloc[0]["isin"], "LT0000128621")
        self.assertEqual(tx.iloc[0]["type"], "BUY")
        self.assertEqual(flows.iloc[0]["type"], "DIVIDEND")
        self.assertAlmostEqual(float(cash.iloc[0]["amount"]), 30.12)


if __name__ == "__main__":
    unittest.main()
