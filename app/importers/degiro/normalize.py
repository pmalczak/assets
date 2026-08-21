# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date

import pandas as pd

from importers.broker.data_model import (
    BrokerCashBalanceFrame,
    BrokerCashFlowFrame,
    BrokerPositionFrame,
    BrokerTransactionFrame,
    CashFlowType,
    TransactionType,
)
from importers.degiro.data_model import (
    DEFAULT_DEGIRO_ASSET_ID,
    DegiroAccountFile,
    DegiroPortfolioFile,
    DegiroTransactionsFile,
)
from importers.degiro.read_degiro import parse_degiro_date


def normalize_degiro_positions(
    portfolio_df: pd.DataFrame,
    *,
    account_id: str = DEFAULT_DEGIRO_ASSET_ID,
    broker: str = "DEGIRO",
) -> pd.DataFrame:
    rows = []
    if portfolio_df is not None and not portfolio_df.empty:
        positions = portfolio_df[
            portfolio_df[DegiroPortfolioFile.ISIN].notna()
            & portfolio_df[DegiroPortfolioFile.ISIN].astype(str).str.strip().ne("")
        ]
        for _, row in positions.iterrows():
            rows.append(
                {
                    BrokerPositionFrame.BROKER: broker,
                    BrokerPositionFrame.ACCOUNT_ID: account_id,
                    BrokerPositionFrame.INSTRUMENT: str(row.get(DegiroPortfolioFile.PRODUCT) or ""),
                    BrokerPositionFrame.TICKER: "",
                    BrokerPositionFrame.ISIN: str(row.get(DegiroPortfolioFile.ISIN) or "").strip(),
                    BrokerPositionFrame.QUANTITY: _float_or_zero(row.get(DegiroPortfolioFile.QUANTITY)),
                    BrokerPositionFrame.AVERAGE_COST: None,
                    BrokerPositionFrame.CURRENCY: str(row.get(DegiroPortfolioFile.LOCAL_CURRENCY) or "").strip(),
                    BrokerPositionFrame.MARKET_VALUE: _float_or_zero(row.get(DegiroPortfolioFile.VALUE_EUR)),
                    BrokerPositionFrame.AS_OF: str(row.get(DegiroPortfolioFile.PERIOD_END) or ""),
                }
            )
    result = pd.DataFrame(rows, columns=list(BrokerPositionFrame.expected_columns()))
    BrokerPositionFrame.check_structure(result)
    return result


def normalize_degiro_transactions(
    transactions_df: pd.DataFrame,
    *,
    account_id: str = DEFAULT_DEGIRO_ASSET_ID,
    broker: str = "DEGIRO",
) -> pd.DataFrame:
    rows = []
    if transactions_df is not None and not transactions_df.empty:
        for _, row in transactions_df.iterrows():
            amount = _float_or_zero(row.get(DegiroTransactionsFile.VALUE_EUR))
            qty = _float_or_zero(row.get(DegiroTransactionsFile.QUANTITY))
            tx_type = TransactionType.BUY if amount < 0 or qty > 0 else TransactionType.SELL
            rows.append(
                {
                    BrokerTransactionFrame.BROKER: broker,
                    BrokerTransactionFrame.ACCOUNT_ID: account_id,
                    BrokerTransactionFrame.DATE: _iso_date(row.get(DegiroTransactionsFile.DATE)),
                    BrokerTransactionFrame.INSTRUMENT: str(row.get(DegiroTransactionsFile.PRODUCT) or ""),
                    BrokerTransactionFrame.TICKER: "",
                    BrokerTransactionFrame.ISIN: str(row.get(DegiroTransactionsFile.ISIN) or "").strip(),
                    BrokerTransactionFrame.TYPE: tx_type.value,
                    BrokerTransactionFrame.QUANTITY: qty,
                    BrokerTransactionFrame.PRICE: row.get(DegiroTransactionsFile.PRICE),
                    BrokerTransactionFrame.CURRENCY: "EUR",
                    BrokerTransactionFrame.AMOUNT: amount,
                    BrokerTransactionFrame.COMMISSION: _float_or_zero(row.get(DegiroTransactionsFile.DEGIRO_FEE)),
                    BrokerTransactionFrame.TAX: 0.0,
                    BrokerTransactionFrame.TRANSACTION_ID: str(row.get(DegiroTransactionsFile.ORDER_ID) or ""),
                }
            )
    result = pd.DataFrame(rows, columns=list(BrokerTransactionFrame.expected_columns()))
    BrokerTransactionFrame.check_structure(result)
    return result


def normalize_degiro_cashflows(
    account_df: pd.DataFrame,
    *,
    account_id: str = DEFAULT_DEGIRO_ASSET_ID,
    broker: str = "DEGIRO",
) -> pd.DataFrame:
    rows = []
    if account_df is not None and not account_df.empty:
        for _, row in account_df.iterrows():
            flow_type = _cashflow_type(row)
            if flow_type is None:
                continue
            rows.append(
                {
                    BrokerCashFlowFrame.BROKER: broker,
                    BrokerCashFlowFrame.ACCOUNT_ID: account_id,
                    BrokerCashFlowFrame.DATE: _iso_date(row.get(DegiroAccountFile.BOOKING_DATE)),
                    BrokerCashFlowFrame.TYPE: flow_type.value,
                    BrokerCashFlowFrame.AMOUNT: _float_or_zero(row.get(DegiroAccountFile.CHANGE)),
                    BrokerCashFlowFrame.CURRENCY: str(row.get(DegiroAccountFile.CHANGE_CURRENCY) or "").strip(),
                    BrokerCashFlowFrame.DESCRIPTION: str(row.get(DegiroAccountFile.DESCRIPTION) or ""),
                    BrokerCashFlowFrame.TRANSACTION_ID: str(row.get(DegiroAccountFile.ORDER_ID) or ""),
                }
            )
    result = pd.DataFrame(rows, columns=list(BrokerCashFlowFrame.expected_columns()))
    BrokerCashFlowFrame.check_structure(result)
    return result


def normalize_degiro_cash_balances(
    portfolio_df: pd.DataFrame,
    *,
    account_id: str = DEFAULT_DEGIRO_ASSET_ID,
    broker: str = "DEGIRO",
) -> pd.DataFrame:
    rows = []
    if portfolio_df is not None and not portfolio_df.empty:
        cash = portfolio_df[
            portfolio_df[DegiroPortfolioFile.ISIN].isna()
            | portfolio_df[DegiroPortfolioFile.ISIN].astype(str).str.strip().eq("")
        ]
        for _, row in cash.iterrows():
            currency = str(row.get(DegiroPortfolioFile.LOCAL_CURRENCY) or "").strip()
            if not currency:
                currency = "EUR"
            rows.append(
                {
                    BrokerCashBalanceFrame.BROKER: broker,
                    BrokerCashBalanceFrame.ACCOUNT_ID: account_id,
                    BrokerCashBalanceFrame.CURRENCY: currency,
                    BrokerCashBalanceFrame.AMOUNT: _float_or_zero(row.get(DegiroPortfolioFile.VALUE_EUR)),
                    BrokerCashBalanceFrame.AS_OF: str(row.get(DegiroPortfolioFile.PERIOD_END) or ""),
                }
            )
    result = pd.DataFrame(rows, columns=list(BrokerCashBalanceFrame.expected_columns()))
    BrokerCashBalanceFrame.check_structure(result)
    return result


def _cashflow_type(row: pd.Series) -> CashFlowType | None:
    desc = str(row.get(DegiroAccountFile.DESCRIPTION) or "").lower()
    if "dywidenda" in desc:
        return CashFlowType.DIVIDEND
    if "interest" in desc or "odset" in desc:
        return CashFlowType.INTEREST
    return None


def _float_or_zero(value) -> float:
    if value is None or pd.isna(value):
        return 0.0
    return float(value)


def _iso_date(value) -> str:
    parsed = parse_degiro_date(value)
    if isinstance(parsed, date):
        return parsed.isoformat()
    return str(parsed)
