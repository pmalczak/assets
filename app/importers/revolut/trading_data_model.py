# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from importers.data_model_generic import GenericStructureClass


class RevolutTradingFileCls(GenericStructureClass):
    DATE = "Date"
    TICKER = "Ticker"
    TYPE = "Type"
    QUANTITY = "Quantity"
    PRICE_PER_SHARE = "Price per share"
    TOTAL_AMOUNT = "Total Amount"
    CURRENCY = "Currency"
    FX_RATE = "FX Rate"
    FILE_DATE = "ref_date"
    PERIOD_START = "period_start"
    PERIOD_END = "period_end"

    TYPE_BUY = "BUY - MARKET"
    TYPE_SELL = "SELL - MARKET"
    TYPE_DIVIDEND = "DIVIDEND"
    TYPE_CASH_TOP_UP = "CASH TOP-UP"
    TYPE_ROBO_FEE = "ROBO MANAGEMENT FEE"

    def expected_columns(self) -> set:
        return {
            self.DATE,
            self.TICKER,
            self.TYPE,
            self.QUANTITY,
            self.PRICE_PER_SHARE,
            self.TOTAL_AMOUNT,
            self.CURRENCY,
            self.FX_RATE,
            self.FILE_DATE,
            self.PERIOD_START,
            self.PERIOD_END,
        }

    def unique_key(self) -> list:
        return [
            self.DATE,
            self.TICKER,
            self.TYPE,
            self.QUANTITY,
            self.PRICE_PER_SHARE,
            self.TOTAL_AMOUNT,
            self.CURRENCY,
            self.FX_RATE,
        ]


class RevolutTradingPnlFileCls(GenericStructureClass):
    SECTION = "section"
    SECTION_SELLS = "Income from Sells"
    SECTION_OTHER = "Other income & fees"

    DATE_ACQUIRED = "Date acquired"
    DATE_SOLD = "Date sold"
    DATE = "Date"
    SYMBOL = "Symbol"
    SECURITY_NAME = "Security name"
    ISIN = "ISIN"
    COUNTRY = "Country"
    QUANTITY = "Quantity"
    COST_BASIS = "Cost basis"
    GROSS_PROCEEDS = "Gross proceeds"
    GROSS_PNL = "Gross PnL"
    GROSS_AMOUNT = "Gross amount"
    WITHHOLDING_TAX = "Withholding tax"
    NET_AMOUNT = "Net Amount"
    CURRENCY = "Currency"
    FILE_DATE = "ref_date"
    PERIOD_START = "period_start"
    PERIOD_END = "period_end"

    def expected_columns(self) -> set:
        return {
            self.SECTION,
            self.DATE_ACQUIRED,
            self.DATE_SOLD,
            self.DATE,
            self.SYMBOL,
            self.SECURITY_NAME,
            self.ISIN,
            self.COUNTRY,
            self.QUANTITY,
            self.COST_BASIS,
            self.GROSS_PROCEEDS,
            self.GROSS_PNL,
            self.GROSS_AMOUNT,
            self.WITHHOLDING_TAX,
            self.NET_AMOUNT,
            self.CURRENCY,
            self.FILE_DATE,
            self.PERIOD_START,
            self.PERIOD_END,
        }

    def unique_key(self) -> list:
        return [
            self.SECTION,
            self.DATE_ACQUIRED,
            self.DATE_SOLD,
            self.DATE,
            self.SYMBOL,
            self.SECURITY_NAME,
            self.ISIN,
            self.COUNTRY,
            self.QUANTITY,
            self.COST_BASIS,
            self.GROSS_PROCEEDS,
            self.GROSS_PNL,
            self.GROSS_AMOUNT,
            self.WITHHOLDING_TAX,
            self.NET_AMOUNT,
            self.CURRENCY,
        ]


RevolutTradingFile = RevolutTradingFileCls()
RevolutTradingPnlFile = RevolutTradingPnlFileCls()
