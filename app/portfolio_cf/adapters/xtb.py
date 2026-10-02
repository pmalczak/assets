# -*- coding: utf-8 -*-
"""Adapter XTB: tickery. Gotówka robocza tylko w składzie/NAV — bez CF `*:CASH`."""
from __future__ import annotations

from datetime import date

import pandas as pd

from importers.xtb.data_model import DEFAULT_XTB_ASSET_ID, XtbCashOperationsFile
from importers.xtb.read_xtb import read_xtb_cash
from portfolio_cf.adapters.base import empty_ledger, legacy_events_to_ledger
from portfolio_cf.coverage import InstrumentCoverage
from roi.xtb_roi import _asset_dir, _filter_xtb_rows_on_or_before, build_xtb_cashflows

VENUE = "xtb"
CURRENCY = "PLN"


def adapt_xtb_ledger(
    valuation_date: date,
    *,
    broker_id: str = DEFAULT_XTB_ASSET_ID,
    cash_operations_df: pd.DataFrame | None = None,
    fx_rates: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, list[InstrumentCoverage], list[str]]:
    warnings: list[str] = []
    if cash_operations_df is None:
        asset_dir = _asset_dir(broker_id)
        cash_operations_df, cash_warnings = read_xtb_cash(asset_dir, broker_id)
        warnings.extend(cash_warnings)

    filtered = _filter_xtb_rows_on_or_before(
        cash_operations_df, XtbCashOperationsFile.TIME, valuation_date
    )
    events, build_warnings = build_xtb_cashflows(filtered, broker_id)
    warnings.extend(build_warnings)
    ticker_ledger, coverage = legacy_events_to_ledger(
        events,
        venue=VENUE,
        currency=CURRENCY,
        valuation_date=valuation_date,
        fx_rates=fx_rates,
    )
    if ticker_ledger is None or ticker_ledger.empty:
        return empty_ledger(), coverage, warnings
    return ticker_ledger, coverage, warnings
