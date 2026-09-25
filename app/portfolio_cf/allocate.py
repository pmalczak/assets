# -*- coding: utf-8 -*-
"""Alokacja wierszy ledgeru do nazwanego portfela."""
from __future__ import annotations

import pandas as pd

from portfolio_cf.adapters.base import empty_ledger
from portfolio_cf.data_model import InstrumentCashFlow
from portfolio_cf.instrument_portfolio import portfolio_for_instrument


def allocate_ledger_to_portfolio(ledger: pd.DataFrame, portfolio_name: str) -> pd.DataFrame:
    """Filtr CF należących do portfela (po instrument_id)."""
    if ledger is None or ledger.empty:
        return empty_ledger()
    if InstrumentCashFlow.INSTRUMENT_ID not in ledger.columns:
        return empty_ledger()

    mask = ledger[InstrumentCashFlow.INSTRUMENT_ID].map(
        lambda instrument_id: portfolio_for_instrument(instrument_id) == portfolio_name
    )
    out = ledger.loc[mask].copy()
    if out.empty:
        return empty_ledger()
    InstrumentCashFlow.check_structure(out)
    return out.reset_index(drop=True)
