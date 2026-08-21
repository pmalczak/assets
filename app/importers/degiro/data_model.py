# -*- coding: utf-8 -*-
from __future__ import annotations

from importers.data_model_generic import GenericStructureClass

DEFAULT_DEGIRO_ASSET_ID = "p_degiro"

PORTFOLIO_SOURCE = "Portfolio.csv"
TRANSACTIONS_SOURCE = "Transactions.csv"
ACCOUNT_SOURCE = "Account.csv"

PORTFOLIO_PREFIX = "portfolio"
TRANSACTIONS_PREFIX = "transactions"
ACCOUNT_PREFIX = "account"


class DegiroPortfolioFileCls(GenericStructureClass):
    PRODUCT = "Produkt"
    ISIN = "Symbol/ISIN"
    QUANTITY = "Suma"
    PRICE = "Kurs"
    LOCAL_CURRENCY = "local_currency"
    LOCAL_VALUE = "Lokalna wartość"
    VALUE_EUR = "Wartość w EUR"
    FILE_DATE = "ref_date"
    PERIOD_START = "period_start"
    PERIOD_END = "period_end"

    def expected_columns(self) -> set:
        return {
            self.PRODUCT,
            self.ISIN,
            self.QUANTITY,
            self.PRICE,
            self.LOCAL_CURRENCY,
            self.LOCAL_VALUE,
            self.VALUE_EUR,
            self.FILE_DATE,
            self.PERIOD_START,
            self.PERIOD_END,
        }


class DegiroTransactionsFileCls(GenericStructureClass):
    DATE = "Data"
    TIME = "Czas"
    PRODUCT = "Produkt"
    ISIN = "ISIN"
    REFERENCE_EXCHANGE = "Giełda referencyjna"
    EXECUTION_VENUE = "Miejsce wykonania"
    QUANTITY = "Liczba"
    PRICE = "Kurs"
    PRICE_CURRENCY = "price_currency"
    LOCAL_VALUE = "Wartość lokalna"
    LOCAL_VALUE_CURRENCY = "local_value_currency"
    VALUE_EUR = "Wartość EUR"
    FX_RATE = "Kurs wymiany"
    AUTOFX_FEE = "Opłaty AutoFX"
    DEGIRO_FEE = "Opłata transakcyjna DEGIRO i/lub opłata stron"
    TOTAL_EUR = "Razem EUR"
    ORDER_ID = "Identyfikator zlecenia"
    FILE_DATE = "ref_date"
    PERIOD_START = "period_start"
    PERIOD_END = "period_end"

    TYPE_BUY = "BUY"
    TYPE_SELL = "SELL"

    def expected_columns(self) -> set:
        return {
            self.DATE,
            self.TIME,
            self.PRODUCT,
            self.ISIN,
            self.REFERENCE_EXCHANGE,
            self.EXECUTION_VENUE,
            self.QUANTITY,
            self.PRICE,
            self.PRICE_CURRENCY,
            self.LOCAL_VALUE,
            self.LOCAL_VALUE_CURRENCY,
            self.VALUE_EUR,
            self.FX_RATE,
            self.AUTOFX_FEE,
            self.DEGIRO_FEE,
            self.TOTAL_EUR,
            self.ORDER_ID,
            self.FILE_DATE,
            self.PERIOD_START,
            self.PERIOD_END,
        }

    def unique_key(self) -> list:
        return [
            self.ORDER_ID,
            self.DATE,
            self.TIME,
            self.PRODUCT,
            self.ISIN,
            self.QUANTITY,
            self.PRICE,
            self.VALUE_EUR,
        ]


class DegiroAccountFileCls(GenericStructureClass):
    BOOKING_DATE = "booking_date"
    TIME = "time"
    VALUE_DATE = "value_date"
    PRODUCT = "product"
    ISIN = "isin"
    DESCRIPTION = "description"
    RATE = "rate"
    CHANGE_CURRENCY = "change_currency"
    CHANGE = "change"
    BALANCE_CURRENCY = "balance_currency"
    BALANCE = "balance"
    ORDER_ID = "order_id"
    FILE_DATE = "ref_date"
    PERIOD_START = "period_start"
    PERIOD_END = "period_end"

    DESCRIPTION_DIVIDEND = "Dywidenda"

    def expected_columns(self) -> set:
        return {
            self.BOOKING_DATE,
            self.TIME,
            self.VALUE_DATE,
            self.PRODUCT,
            self.ISIN,
            self.DESCRIPTION,
            self.RATE,
            self.CHANGE_CURRENCY,
            self.CHANGE,
            self.BALANCE_CURRENCY,
            self.BALANCE,
            self.ORDER_ID,
            self.FILE_DATE,
            self.PERIOD_START,
            self.PERIOD_END,
        }

    def unique_key(self) -> list:
        return [
            self.BOOKING_DATE,
            self.TIME,
            self.VALUE_DATE,
            self.PRODUCT,
            self.ISIN,
            self.DESCRIPTION,
            self.RATE,
            self.CHANGE_CURRENCY,
            self.CHANGE,
            self.BALANCE_CURRENCY,
            self.BALANCE,
            self.ORDER_ID,
        ]


DegiroPortfolioFile = DegiroPortfolioFileCls()
DegiroTransactionsFile = DegiroTransactionsFileCls()
DegiroAccountFile = DegiroAccountFileCls()
