# -*- coding: utf-8 -*-
"""Kanoniczny wiersz przepływu instrumentu (native + PLN)."""
from __future__ import annotations

from importers.data_model_generic import GenericStructureClass


class InstrumentCashFlowCls(GenericStructureClass):
    INSTRUMENT_ID = "instrument_id"
    DATE = "date"
    CATEGORY = "category"
    AMOUNT = "amount"
    CURRENCY = "currency"
    AMOUNT_PLN = "amount_pln"
    FX_RATE = "fx_rate"
    FX_DATE = "fx_date"
    VENUE = "venue"
    SOURCE = "source"
    DESCRIPTION = "description"
    TITLE = "title"
    COUNTERPARTY = "counterparty"
    ACCOUNT_NUMBER = "account_number"

    COLUMN_ORDER = (
        INSTRUMENT_ID,
        DATE,
        CATEGORY,
        AMOUNT,
        CURRENCY,
        AMOUNT_PLN,
        FX_RATE,
        FX_DATE,
        VENUE,
        SOURCE,
        DESCRIPTION,
        TITLE,
        COUNTERPARTY,
        ACCOUNT_NUMBER,
    )

    def expected_columns(self) -> set:
        return set(self.COLUMN_ORDER)


InstrumentCashFlow = InstrumentCashFlowCls()

CASH_SUFFIX = "CASH"


def cash_instrument_id(broker_id: str) -> str:
    return f"{str(broker_id).strip()}:{CASH_SUFFIX}"
