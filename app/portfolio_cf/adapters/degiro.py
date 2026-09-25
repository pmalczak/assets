# -*- coding: utf-8 -*-
"""Adapter DEGIRO: tickery (ISIN) + CASH (lustra + transfery bez ISIN)."""
from __future__ import annotations

from datetime import date

import pandas as pd

from evaluators.valuation_date import filter_excel_rows_on_or_before
from importers.degiro.data_model import (
    DEFAULT_DEGIRO_ASSET_ID,
    DegiroAccountFile,
    DegiroTransactionsFile,
)
from importers.degiro.read_degiro import read_degiro_account, read_degiro_transactions
from portfolio_cf.adapters.base import (
    build_ledger_row,
    cash_leg_category_and_amount,
    empty_ledger,
    legacy_events_to_ledger,
    rows_to_ledger,
)
from portfolio_cf.coverage import CoverageStatus, InstrumentCoverage
from portfolio_cf.data_model import InstrumentCashFlow, cash_instrument_id
from roi.categories import CAPEX, DIVESTMENT, REVENUES
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
    cash_ledger, cash_cov = _build_cash_ledger(
        tx, account, broker_id=broker_id, valuation_date=valuation_date, fx_rates=fx_rates
    )
    coverage.append(cash_cov)
    return _concat(ticker_ledger, cash_ledger), coverage, warnings


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


def _build_cash_ledger(
    transactions_df: pd.DataFrame,
    account_df: pd.DataFrame,
    *,
    broker_id: str,
    valuation_date: date,
    fx_rates: pd.DataFrame | None,
) -> tuple[pd.DataFrame, InstrumentCoverage]:
    cash_id = cash_instrument_id(broker_id)
    cov = InstrumentCoverage(
        instrument_id=cash_id,
        status=CoverageStatus.COVERED,
        reason="lustra trade/div + transfery bez ISIN",
        venue=VENUE,
    )
    rows: list[dict] = []

    if transactions_df is not None and not transactions_df.empty:
        for _, row in transactions_df.iterrows():
            amount = row.get(DegiroTransactionsFile.VALUE_EUR)
            if pd.isna(amount):
                continue
            amount = float(amount)
            qty = row.get(DegiroTransactionsFile.QUANTITY)
            qty = float(qty) if pd.notna(qty) else 0.0
            if amount < 0 or qty > 0:
                ticker_cat, ticker_amt = CAPEX, -abs(amount)
            else:
                ticker_cat, ticker_amt = DIVESTMENT, abs(amount)
            cash_cat, cash_amt = cash_leg_category_and_amount(ticker_cat, ticker_amt)
            rows.append(
                build_ledger_row(
                    instrument_id=cash_id,
                    event_date=row.get(DegiroTransactionsFile.DATE),
                    category=cash_cat,
                    amount=cash_amt,
                    currency=CURRENCY,
                    venue=VENUE,
                    source=broker_id,
                    description=f"cash-leg:{'BUY' if ticker_cat == CAPEX else 'SELL'}",
                    title=str(row.get(DegiroTransactionsFile.PRODUCT) or ""),
                    fx_rates=fx_rates,
                )
            )

    if account_df is not None and not account_df.empty:
        for _, row in account_df.iterrows():
            description = str(row.get(DegiroAccountFile.DESCRIPTION) or "")
            isin = str(row.get(DegiroAccountFile.ISIN) or "").strip()
            amount = row.get(DegiroAccountFile.CHANGE)
            if pd.isna(amount) or abs(float(amount)) < 1e-12:
                continue
            amount = float(amount)
            if isin and DegiroAccountFile.DESCRIPTION_DIVIDEND.lower() in description.lower():
                cash_cat, cash_amt = cash_leg_category_and_amount(REVENUES, abs(amount))
                rows.append(
                    build_ledger_row(
                        instrument_id=cash_id,
                        event_date=row.get(DegiroAccountFile.BOOKING_DATE),
                        category=cash_cat,
                        amount=cash_amt,
                        currency=CURRENCY,
                        venue=VENUE,
                        source=broker_id,
                        description="cash-leg:dividend",
                        title=str(row.get(DegiroAccountFile.PRODUCT) or ""),
                        fx_rates=fx_rates,
                    )
                )
                continue
            if isin:
                continue
            if amount > 0:
                category, signed = CAPEX, -abs(amount)
            else:
                category, signed = DIVESTMENT, abs(amount)
            rows.append(
                build_ledger_row(
                    instrument_id=cash_id,
                    event_date=row.get(DegiroAccountFile.BOOKING_DATE),
                    category=category,
                    amount=signed,
                    currency=CURRENCY,
                    venue=VENUE,
                    source=broker_id,
                    description=description or "cash-transfer",
                    title="CASH",
                    fx_rates=fx_rates,
                )
            )

    ledger = rows_to_ledger(rows)
    if ledger.empty:
        return ledger, cov
    return filter_excel_rows_on_or_before(ledger, InstrumentCashFlow.DATE, valuation_date), cov


def _concat(*frames: pd.DataFrame) -> pd.DataFrame:
    present = [frame for frame in frames if frame is not None and not frame.empty]
    if not present:
        return empty_ledger()
    out = pd.concat(present, ignore_index=True)
    InstrumentCashFlow.check_structure(out)
    return out
