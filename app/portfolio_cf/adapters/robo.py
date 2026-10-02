# -*- coding: utf-8 -*-
"""Adapter Revolut Robo: tickery (+ fee). Gotówka robocza tylko w składzie/NAV — bez CF `*:CASH`."""
from __future__ import annotations

from datetime import date

import pandas as pd

from evaluators.evaluate_broker_revolut import filter_trading_on_or_before
from importers.revolut.trading_data_model import DEFAULT_REVOLUT_ROBO_ASSET_ID
from portfolio_cf.adapters.base import empty_ledger, legacy_events_to_ledger
from portfolio_cf.coverage import InstrumentCoverage
from roi.broker_trading_roi import build_broker_ticker_cashflows

VENUE = "robo"
CURRENCY = "EUR"


def adapt_robo_ledger(
    valuation_date: date,
    *,
    broker_id: str = DEFAULT_REVOLUT_ROBO_ASSET_ID,
    trading_df: pd.DataFrame | None = None,
    fx_rates: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, list[InstrumentCoverage], list[str]]:
    warnings: list[str] = []
    if trading_df is None:
        from roi.broker_trading_roi import _load_broker_trading

        trading_df, load_warnings = _load_broker_trading(broker_id)
        warnings.extend(load_warnings)

    filtered = filter_trading_on_or_before(trading_df, valuation_date)
    events = build_broker_ticker_cashflows(filtered, broker_id)
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
