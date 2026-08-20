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
from importers.xtb.data_model import (
    CASH_OP_DEPOSIT,
    CASH_OP_DIVIDEND,
    CASH_OP_FEE,
    CASH_OP_FX,
    CASH_OP_INTEREST,
    CASH_OP_PURCHASE,
    CASH_OP_SALE,
    CASH_OP_WITHDRAWAL,
    DEFAULT_XTB_ASSET_ID,
    XTB_BROKER_NAME,
    XtbCashOperationsFile,
    XtbClosedPositionsFile,
    XtbOpenPositionsFile,
    classify_xtb_cash_type,
)
from importers.xtb.read_xtb import (
    parse_xtb_date,
    parse_xtb_number,
    xtb_cash_rows,
    xtb_open_position_rows,
)


def normalize_xtb_positions(
    open_df: pd.DataFrame,
    *,
    account_id: str = DEFAULT_XTB_ASSET_ID,
    broker: str = XTB_BROKER_NAME,
) -> pd.DataFrame:
    rows = []
    positions = xtb_open_position_rows(open_df)
    for _, row in positions.iterrows():
        rows.append(
            {
                BrokerPositionFrame.BROKER: broker,
                BrokerPositionFrame.ACCOUNT_ID: account_id,
                BrokerPositionFrame.INSTRUMENT: str(row.get(XtbOpenPositionsFile.INSTRUMENT) or ""),
                BrokerPositionFrame.TICKER: str(row.get(XtbOpenPositionsFile.TICKER) or "").strip(),
                BrokerPositionFrame.ISIN: str(row.get(XtbOpenPositionsFile.ISIN) or "").strip(),
                BrokerPositionFrame.QUANTITY: _float_or_zero(row.get(XtbOpenPositionsFile.VOLUME)),
                BrokerPositionFrame.AVERAGE_COST: None,
                BrokerPositionFrame.CURRENCY: str(row.get(XtbOpenPositionsFile.CURRENCY) or "").strip(),
                BrokerPositionFrame.MARKET_VALUE: _float_or_zero(row.get(XtbOpenPositionsFile.VALUE)),
                BrokerPositionFrame.AS_OF: str(row.get(XtbOpenPositionsFile.PERIOD_END) or ""),
            }
        )
    result = pd.DataFrame(rows, columns=list(BrokerPositionFrame.expected_columns()))
    BrokerPositionFrame.check_structure(result)
    return result


def normalize_xtb_transactions(
    closed_df: pd.DataFrame,
    cash_df: pd.DataFrame | None = None,
    *,
    account_id: str = DEFAULT_XTB_ASSET_ID,
    broker: str = XTB_BROKER_NAME,
) -> pd.DataFrame:
    rows = []
    if closed_df is not None and not closed_df.empty:
        for _, row in closed_df.iterrows():
            ticker = str(row.get(XtbClosedPositionsFile.TICKER) or "").strip()
            if not ticker and not str(row.get(XtbClosedPositionsFile.ISIN) or "").strip():
                continue
            qty = _float_or_zero(row.get(XtbClosedPositionsFile.VOLUME))
            price = row.get(XtbClosedPositionsFile.CLOSE_PRICE)
            amount = None
            if price is not None and not pd.isna(price) and qty:
                amount = abs(float(price) * float(qty))
            rows.append(
                {
                    BrokerTransactionFrame.BROKER: broker,
                    BrokerTransactionFrame.ACCOUNT_ID: account_id,
                    BrokerTransactionFrame.DATE: _iso_date(
                        row.get(XtbClosedPositionsFile.CLOSE_TIME) or row.get(XtbClosedPositionsFile.PERIOD_END)
                    ),
                    BrokerTransactionFrame.INSTRUMENT: str(row.get(XtbClosedPositionsFile.INSTRUMENT) or ""),
                    BrokerTransactionFrame.TICKER: ticker,
                    BrokerTransactionFrame.ISIN: str(row.get(XtbClosedPositionsFile.ISIN) or "").strip(),
                    BrokerTransactionFrame.TYPE: TransactionType.SELL.value,
                    BrokerTransactionFrame.QUANTITY: qty,
                    BrokerTransactionFrame.PRICE: price,
                    BrokerTransactionFrame.CURRENCY: "",
                    BrokerTransactionFrame.AMOUNT: amount if amount is not None else 0.0,
                    BrokerTransactionFrame.COMMISSION: 0.0,
                    BrokerTransactionFrame.TAX: 0.0,
                    BrokerTransactionFrame.TRANSACTION_ID: str(row.get(XtbClosedPositionsFile.POSITION_ID) or ""),
                }
            )
    if cash_df is not None and not cash_df.empty:
        for _, row in cash_df.iterrows():
            op_type = classify_xtb_cash_type(row.get(XtbCashOperationsFile.TYPE))
            if op_type not in {CASH_OP_PURCHASE, CASH_OP_SALE}:
                continue
            ticker = str(row.get(XtbCashOperationsFile.TICKER) or "").strip()
            isin = str(row.get(XtbCashOperationsFile.ISIN) or "").strip()
            if not ticker and not isin:
                continue
            amount = _float_or_zero(row.get(XtbCashOperationsFile.AMOUNT))
            rows.append(
                {
                    BrokerTransactionFrame.BROKER: broker,
                    BrokerTransactionFrame.ACCOUNT_ID: account_id,
                    BrokerTransactionFrame.DATE: _iso_date(row.get(XtbCashOperationsFile.TIME)),
                    BrokerTransactionFrame.INSTRUMENT: str(row.get(XtbCashOperationsFile.INSTRUMENT) or ""),
                    BrokerTransactionFrame.TICKER: ticker,
                    BrokerTransactionFrame.ISIN: isin,
                    BrokerTransactionFrame.TYPE: (
                        TransactionType.BUY.value if op_type == CASH_OP_PURCHASE else TransactionType.SELL.value
                    ),
                    BrokerTransactionFrame.QUANTITY: 0.0,
                    BrokerTransactionFrame.PRICE: None,
                    BrokerTransactionFrame.CURRENCY: str(row.get(XtbCashOperationsFile.CURRENCY) or "").strip(),
                    BrokerTransactionFrame.AMOUNT: amount,
                    BrokerTransactionFrame.COMMISSION: 0.0,
                    BrokerTransactionFrame.TAX: 0.0,
                    BrokerTransactionFrame.TRANSACTION_ID: str(
                        row.get(XtbCashOperationsFile.ID) or row.get(XtbCashOperationsFile.POSITION_ID) or ""
                    ),
                }
            )
    result = pd.DataFrame(rows, columns=list(BrokerTransactionFrame.expected_columns()))
    BrokerTransactionFrame.check_structure(result)
    return result


def normalize_xtb_cashflows(
    cash_df: pd.DataFrame,
    *,
    account_id: str = DEFAULT_XTB_ASSET_ID,
    broker: str = XTB_BROKER_NAME,
) -> pd.DataFrame:
    rows = []
    if cash_df is not None and not cash_df.empty:
        for _, row in cash_df.iterrows():
            flow_type = _cashflow_type(row)
            if flow_type is None:
                continue
            rows.append(
                {
                    BrokerCashFlowFrame.BROKER: broker,
                    BrokerCashFlowFrame.ACCOUNT_ID: account_id,
                    BrokerCashFlowFrame.DATE: _iso_date(row.get(XtbCashOperationsFile.TIME)),
                    BrokerCashFlowFrame.TYPE: flow_type.value,
                    BrokerCashFlowFrame.AMOUNT: _float_or_zero(row.get(XtbCashOperationsFile.AMOUNT)),
                    BrokerCashFlowFrame.CURRENCY: str(row.get(XtbCashOperationsFile.CURRENCY) or "").strip(),
                    BrokerCashFlowFrame.DESCRIPTION: str(row.get(XtbCashOperationsFile.TYPE) or ""),
                    BrokerCashFlowFrame.TRANSACTION_ID: str(
                        row.get(XtbCashOperationsFile.ID) or row.get(XtbCashOperationsFile.POSITION_ID) or ""
                    ),
                }
            )
    result = pd.DataFrame(rows, columns=list(BrokerCashFlowFrame.expected_columns()))
    BrokerCashFlowFrame.check_structure(result)
    return result


def normalize_xtb_cash_balances(
    open_df: pd.DataFrame,
    *,
    account_id: str = DEFAULT_XTB_ASSET_ID,
    broker: str = XTB_BROKER_NAME,
) -> pd.DataFrame:
    rows = []
    cash = xtb_cash_rows(open_df)
    for _, row in cash.iterrows():
        currency = str(row.get(XtbOpenPositionsFile.CURRENCY) or "").strip()
        rows.append(
            {
                BrokerCashBalanceFrame.BROKER: broker,
                BrokerCashBalanceFrame.ACCOUNT_ID: account_id,
                BrokerCashBalanceFrame.CURRENCY: currency,
                BrokerCashBalanceFrame.AMOUNT: _float_or_zero(row.get(XtbOpenPositionsFile.VALUE)),
                BrokerCashBalanceFrame.AS_OF: str(row.get(XtbOpenPositionsFile.PERIOD_END) or ""),
            }
        )
    result = pd.DataFrame(rows, columns=list(BrokerCashBalanceFrame.expected_columns()))
    BrokerCashBalanceFrame.check_structure(result)
    return result


def _cashflow_type(row: pd.Series) -> CashFlowType | None:
    op_type = classify_xtb_cash_type(row.get(XtbCashOperationsFile.TYPE))
    return {
        CASH_OP_DIVIDEND: CashFlowType.DIVIDEND,
        CASH_OP_DEPOSIT: CashFlowType.DEPOSIT,
        CASH_OP_WITHDRAWAL: CashFlowType.WITHDRAWAL,
        CASH_OP_FEE: CashFlowType.FEE,
        CASH_OP_FX: CashFlowType.FX,
        CASH_OP_INTEREST: CashFlowType.INTEREST,
    }.get(op_type)


def _float_or_zero(value) -> float:
    parsed = parse_xtb_number(value)
    return 0.0 if parsed is None else parsed


def _iso_date(value) -> str:
    parsed = parse_xtb_date(value)
    if isinstance(parsed, date):
        return parsed.isoformat()
    return str(value or "")
