# -*- coding: utf-8 -*-
"""Adapter DEGIRO: tickery (ISIN). Gotówka robocza tylko w składzie/NAV — bez CF `*:CASH`."""
from __future__ import annotations

from datetime import date

import pandas as pd

from importers.degiro.data_model import (
    DEFAULT_DEGIRO_ASSET_ID,
    DegiroAccountFile,
    DegiroTransactionsFile,
)
from importers.degiro.read_degiro import read_degiro_account, read_degiro_transactions
from portfolio_cf.adapters.base import empty_ledger, legacy_events_to_ledger
from portfolio_cf.coverage import InstrumentCoverage
from roi.degiro_roi import _filter_degiro_rows_on_or_before, build_degiro_cashflows

VENUE = "degiro"
CURRENCY = "EUR"


def adapt_degiro_ledger(
    valuation_date: date,
    *,
    broker_id: str = DEFAULT_DEGIRO_ASSET_ID,
    transactions_df: pd.DataFrame | None = None,
    account_df: pd.DataFrame | None = None,
    fx_rates: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, list[InstrumentCoverage], list[str]]:
    warnings: list[str] = []
    transactions_df, account_df, warnings = _ensure_frames(
        broker_id, transactions_df, account_df, warnings
    )

    tx = _filter_degiro_rows_on_or_before(transactions_df, DegiroTransactionsFile.DATE, valuation_date)
    account = _filter_degiro_rows_on_or_before(account_df, DegiroAccountFile.BOOKING_DATE, valuation_date)
    events = build_degiro_cashflows(tx, account, broker_id)
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


def _ensure_frames(
    broker_id: str,
    transactions_df: pd.DataFrame | None,
    account_df: pd.DataFrame | None,
    warnings: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    if transactions_df is not None and account_df is not None:
        return transactions_df, account_df, warnings
    from roi.degiro_roi import _asset_dir

    try:
        asset_dir = _asset_dir(broker_id)
    except ValueError as exc:
        warnings.append(f"DEGIRO: {exc}")
        empty = pd.DataFrame()
        return (
            transactions_df if transactions_df is not None else empty,
            account_df if account_df is not None else empty,
            warnings,
        )
    if transactions_df is None:
        transactions_df, tw = read_degiro_transactions(asset_dir, broker_id)
        warnings.extend(tw)
    if account_df is None:
        account_df, aw = read_degiro_account(asset_dir, broker_id)
        warnings.extend(aw)
    return transactions_df, account_df, warnings
