# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

import pandas as pd

from importers.data_model_generic import GenericStructureClass


class TransactionType(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    OTHER = "OTHER"


class CashFlowType(StrEnum):
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    DIVIDEND = "DIVIDEND"
    INTEREST = "INTEREST"
    FEE = "FEE"
    TAX = "TAX"
    FX = "FX"
    OTHER = "OTHER"


@dataclass(frozen=True)
class Account:
    broker: str
    account_id: str
    base_currency: str


@dataclass(frozen=True)
class Position:
    broker: str
    account_id: str
    instrument: str
    ticker: str
    isin: str
    quantity: float
    average_cost: float | None
    currency: str
    market_value: float
    as_of: date | None = None


@dataclass(frozen=True)
class Transaction:
    broker: str
    account_id: str
    date: date
    instrument: str
    ticker: str
    isin: str
    type: TransactionType
    quantity: float
    price: float | None
    currency: str
    amount: float
    commission: float = 0.0
    tax: float = 0.0
    transaction_id: str = ""


@dataclass(frozen=True)
class CashFlow:
    broker: str
    account_id: str
    date: date
    type: CashFlowType
    amount: float
    currency: str
    description: str = ""
    transaction_id: str = ""


@dataclass(frozen=True)
class CashBalance:
    broker: str
    account_id: str
    currency: str
    amount: float
    as_of: date | None = None


class BrokerAccountFrameCls(GenericStructureClass):
    BROKER = "broker"
    ACCOUNT_ID = "account_id"
    BASE_CURRENCY = "base_currency"

    def expected_columns(self) -> set:
        return {self.BROKER, self.ACCOUNT_ID, self.BASE_CURRENCY}


class BrokerPositionFrameCls(GenericStructureClass):
    BROKER = "broker"
    ACCOUNT_ID = "account_id"
    INSTRUMENT = "instrument"
    TICKER = "ticker"
    ISIN = "isin"
    QUANTITY = "quantity"
    AVERAGE_COST = "average_cost"
    CURRENCY = "currency"
    MARKET_VALUE = "market_value"
    AS_OF = "as_of"

    def expected_columns(self) -> set:
        return {
            self.BROKER,
            self.ACCOUNT_ID,
            self.INSTRUMENT,
            self.TICKER,
            self.ISIN,
            self.QUANTITY,
            self.AVERAGE_COST,
            self.CURRENCY,
            self.MARKET_VALUE,
            self.AS_OF,
        }


class BrokerTransactionFrameCls(GenericStructureClass):
    BROKER = "broker"
    ACCOUNT_ID = "account_id"
    DATE = "date"
    INSTRUMENT = "instrument"
    TICKER = "ticker"
    ISIN = "isin"
    TYPE = "type"
    QUANTITY = "quantity"
    PRICE = "price"
    CURRENCY = "currency"
    AMOUNT = "amount"
    COMMISSION = "commission"
    TAX = "tax"
    TRANSACTION_ID = "transaction_id"

    def expected_columns(self) -> set:
        return {
            self.BROKER,
            self.ACCOUNT_ID,
            self.DATE,
            self.INSTRUMENT,
            self.TICKER,
            self.ISIN,
            self.TYPE,
            self.QUANTITY,
            self.PRICE,
            self.CURRENCY,
            self.AMOUNT,
            self.COMMISSION,
            self.TAX,
            self.TRANSACTION_ID,
        }


class BrokerCashFlowFrameCls(GenericStructureClass):
    BROKER = "broker"
    ACCOUNT_ID = "account_id"
    DATE = "date"
    TYPE = "type"
    AMOUNT = "amount"
    CURRENCY = "currency"
    DESCRIPTION = "description"
    TRANSACTION_ID = "transaction_id"

    def expected_columns(self) -> set:
        return {
            self.BROKER,
            self.ACCOUNT_ID,
            self.DATE,
            self.TYPE,
            self.AMOUNT,
            self.CURRENCY,
            self.DESCRIPTION,
            self.TRANSACTION_ID,
        }


class BrokerCashBalanceFrameCls(GenericStructureClass):
    BROKER = "broker"
    ACCOUNT_ID = "account_id"
    CURRENCY = "currency"
    AMOUNT = "amount"
    AS_OF = "as_of"

    def expected_columns(self) -> set:
        return {self.BROKER, self.ACCOUNT_ID, self.CURRENCY, self.AMOUNT, self.AS_OF}


BrokerAccountFrame = BrokerAccountFrameCls()
BrokerPositionFrame = BrokerPositionFrameCls()
BrokerTransactionFrame = BrokerTransactionFrameCls()
BrokerCashFlowFrame = BrokerCashFlowFrameCls()
BrokerCashBalanceFrame = BrokerCashBalanceFrameCls()


def empty_broker_frame(model: GenericStructureClass) -> pd.DataFrame:
    return pd.DataFrame(columns=list(model.expected_columns()))
