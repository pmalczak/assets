# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from importers.data_model_generic import GenericStructureClass

DEFAULT_XTB_ASSET_ID = "p_xtb"
DEFAULT_XTB_CLIENT_ID = "55260027"
XTB_FILE_PREFIX = "xtb"
XTB_BROKER_NAME = "XTB"

XTB_SHEET_OPEN_POSITIONS = "Open Positions"
XTB_SHEET_CLOSED_POSITIONS = "Closed Positions"
XTB_SHEET_CASH_OPERATIONS = "Cash Operations"

OPEN_KIND = "open"
CLOSED_KIND = "closed"
CASH_KIND = "cash"

CASH_OP_PURCHASE = "purchase"
CASH_OP_SALE = "sale"
CASH_OP_DIVIDEND = "dividend"
CASH_OP_FEE = "fee"
CASH_OP_DEPOSIT = "deposit"
CASH_OP_WITHDRAWAL = "withdrawal"
CASH_OP_FX = "fx"
CASH_OP_INTEREST = "interest"

TICKER_ROI_TYPES = {CASH_OP_PURCHASE, CASH_OP_SALE, CASH_OP_DIVIDEND}
ACCOUNT_LEVEL_TYPES = {
    CASH_OP_FEE,
    CASH_OP_DEPOSIT,
    CASH_OP_WITHDRAWAL,
    CASH_OP_FX,
    CASH_OP_INTEREST,
}

# Stopka tabeli Cash Operations (nie jest operacją).
CASH_FOOTER_TYPES = frozenset({"total", "suma"})


@dataclass(frozen=True)
class XtbExportSheetInfo:
    sheet_name: str
    columns: tuple[str, ...]
    rows: int
    header_row: int | None = None


class XtbOpenPositionsFileCls(GenericStructureClass):
    PRODUCT = "Product"
    INSTRUMENT = "Instrument/Position"
    TICKER = "Ticker"
    ISIN = "ISIN"
    VOLUME = "Volume"
    VALUE = "Value"
    CURRENCY = "Currency"
    TYPE = "Type"
    POSITION_ID = "Position ID"
    FILE_DATE = "ref_date"
    PERIOD_START = "period_start"
    PERIOD_END = "period_end"

    def expected_columns(self) -> set:
        return {
            self.PRODUCT,
            self.INSTRUMENT,
            self.TICKER,
            self.ISIN,
            self.VOLUME,
            self.VALUE,
            self.CURRENCY,
            self.TYPE,
            self.POSITION_ID,
            self.FILE_DATE,
            self.PERIOD_START,
            self.PERIOD_END,
        }


class XtbClosedPositionsFileCls(GenericStructureClass):
    INSTRUMENT = "Instrument"
    TICKER = "Ticker"
    ISIN = "ISIN"
    VOLUME = "Volume"
    OPEN_PRICE = "Open Price"
    CLOSE_PRICE = "Close Price"
    OPEN_TIME = "Open Time"
    CLOSE_TIME = "Close Time"
    POSITION_ID = "Position ID"
    PROFIT = "Profit"
    FILE_DATE = "ref_date"
    PERIOD_START = "period_start"
    PERIOD_END = "period_end"

    def expected_columns(self) -> set:
        return {
            self.INSTRUMENT,
            self.TICKER,
            self.ISIN,
            self.VOLUME,
            self.OPEN_PRICE,
            self.CLOSE_PRICE,
            self.OPEN_TIME,
            self.CLOSE_TIME,
            self.POSITION_ID,
            self.PROFIT,
            self.FILE_DATE,
            self.PERIOD_START,
            self.PERIOD_END,
        }

    def unique_key(self) -> list:
        return [
            self.POSITION_ID,
            self.TICKER,
            self.ISIN,
            self.VOLUME,
            self.OPEN_TIME,
            self.CLOSE_TIME,
            self.OPEN_PRICE,
            self.CLOSE_PRICE,
        ]


class XtbCashOperationsFileCls(GenericStructureClass):
    ID = "ID"
    TYPE = "Type"
    INSTRUMENT = "Instrument"
    TICKER = "Ticker"
    ISIN = "ISIN"
    TIME = "Time"
    AMOUNT = "Amount"
    COMMENT = "Comment"
    POSITION_ID = "Position ID"
    BALANCE = "Balance"
    CURRENCY = "Currency"
    FILE_DATE = "ref_date"
    PERIOD_START = "period_start"
    PERIOD_END = "period_end"

    def expected_columns(self) -> set:
        return {
            self.ID,
            self.TYPE,
            self.INSTRUMENT,
            self.TICKER,
            self.ISIN,
            self.TIME,
            self.AMOUNT,
            self.COMMENT,
            self.POSITION_ID,
            self.BALANCE,
            self.CURRENCY,
            self.FILE_DATE,
            self.PERIOD_START,
            self.PERIOD_END,
        }

    def unique_key(self) -> list:
        return [
            self.ID,
            self.TYPE,
            self.TICKER,
            self.ISIN,
            self.TIME,
            self.AMOUNT,
            self.POSITION_ID,
            self.COMMENT,
        ]


XtbOpenPositionsFile = XtbOpenPositionsFileCls()
XtbClosedPositionsFile = XtbClosedPositionsFileCls()
XtbCashOperationsFile = XtbCashOperationsFileCls()


def is_xtb_cash_footer(operation_type: str) -> bool:
    """Wiersz podsumowania arkusza (Type=Total/Suma), nie operacja kasowa."""
    return str(operation_type or "").strip().lower() in CASH_FOOTER_TYPES


def classify_xtb_cash_type(operation_type: str) -> str | None:
    """Mapuje Type z Cash Operations na klasę v1; None = nieznany typ."""
    text = str(operation_type or "").strip().lower()
    if not text or is_xtb_cash_footer(text):
        return None
    if "purchase" in text or text == "buy":
        return CASH_OP_PURCHASE
    if "sale" in text or text == "sell":
        return CASH_OP_SALE
    if "dividend" in text:
        return CASH_OP_DIVIDEND
    if "commission" in text or "fee" in text or "tax" in text:
        return CASH_OP_FEE
    if "deposit" in text:
        return CASH_OP_DEPOSIT
    if "withdrawal" in text or "withdraw" in text:
        return CASH_OP_WITHDRAWAL
    if "fx" in text or "conversion" in text or "exchange" in text or "swap" in text:
        return CASH_OP_FX
    if "interest" in text:
        return CASH_OP_INTEREST
    return None


def xtb_instrument_id(row) -> str:
    """Stabilny klucz instrumentu: ISIN jeśli jest, inaczej ticker XTB."""
    isin = _cell_text(row.get(XtbOpenPositionsFile.ISIN))
    if isin:
        return isin
    return _cell_text(row.get(XtbOpenPositionsFile.TICKER))


def _cell_text(value) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none"} else text
