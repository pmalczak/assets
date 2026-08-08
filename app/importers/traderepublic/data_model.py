# -*- coding: utf-8 -*-
"""Model blottera Trade Republic (`Eksport transakcji.csv`)."""
from __future__ import annotations

from importers.data_model_generic import GenericStructureClass

DEFAULT_TRADEREPUBLIC_ASSET_ID = "p_traderepublic"
SOURCE_EXPORT_STEM = "Eksport transakcji"
FILE_PREFIX = "eksport-transakcji"

REQUIRED_SOURCE_COLUMNS = (
    "datetime",
    "date",
    "account_type",
    "category",
    "type",
    "asset_class",
    "name",
    "symbol",
    "shares",
    "price",
    "amount",
    "fee",
    "tax",
    "currency",
    "original_amount",
    "original_currency",
    "fx_rate",
    "description",
    "transaction_id",
    "counterparty_name",
    "counterparty_iban",
    "payment_reference",
    "mcc_code",
)


class TradeRepublicFileCls(GenericStructureClass):
    DATETIME = "datetime"
    DATE = "date"
    ACCOUNT_TYPE = "account_type"
    CATEGORY = "category"
    TYPE = "type"
    ASSET_CLASS = "asset_class"
    NAME = "name"
    SYMBOL = "symbol"
    SHARES = "shares"
    PRICE = "price"
    AMOUNT = "amount"
    FEE = "fee"
    TAX = "tax"
    CURRENCY = "currency"
    ORIGINAL_AMOUNT = "original_amount"
    ORIGINAL_CURRENCY = "original_currency"
    FX_RATE = "fx_rate"
    DESCRIPTION = "description"
    TRANSACTION_ID = "transaction_id"
    COUNTERPARTY_NAME = "counterparty_name"
    COUNTERPARTY_IBAN = "counterparty_iban"
    PAYMENT_REFERENCE = "payment_reference"
    MCC_CODE = "mcc_code"
    FILE_DATE = "ref_date"
    PERIOD_START = "period_start"
    PERIOD_END = "period_end"

    TYPE_CUSTOMER_INPAYMENT = "CUSTOMER_INPAYMENT"

    def expected_columns(self) -> set:
        return {
            self.DATETIME,
            self.DATE,
            self.ACCOUNT_TYPE,
            self.CATEGORY,
            self.TYPE,
            self.ASSET_CLASS,
            self.NAME,
            self.SYMBOL,
            self.SHARES,
            self.PRICE,
            self.AMOUNT,
            self.FEE,
            self.TAX,
            self.CURRENCY,
            self.ORIGINAL_AMOUNT,
            self.ORIGINAL_CURRENCY,
            self.FX_RATE,
            self.DESCRIPTION,
            self.TRANSACTION_ID,
            self.COUNTERPARTY_NAME,
            self.COUNTERPARTY_IBAN,
            self.PAYMENT_REFERENCE,
            self.MCC_CODE,
            self.FILE_DATE,
            self.PERIOD_START,
            self.PERIOD_END,
        }

    def unique_key(self) -> list:
        return [self.TRANSACTION_ID]


TradeRepublicFile = TradeRepublicFileCls()
