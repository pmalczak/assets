# -*- coding: utf-8 -*-
"""Adapter XTB: tickery + CASH (deposit/withdrawal + lustra purchase/sale/div)."""
from __future__ import annotations

from datetime import date

import pandas as pd

from evaluators.valuation_date import filter_excel_rows_on_or_before
from importers.xtb.data_model import (
    CASH_OP_DEPOSIT,
    CASH_OP_DIVIDEND,
    CASH_OP_PURCHASE,
    CASH_OP_SALE,
    CASH_OP_WITHDRAWAL,
    DEFAULT_XTB_ASSET_ID,
    TICKER_ROI_TYPES,
    XtbCashOperationsFile,
    classify_xtb_cash_type,
    is_xtb_cash_footer,
    xtb_instrument_id,
)
from importers.xtb.read_xtb import read_xtb_cash
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
    cash_ledger, cash_cov = _build_cash_ledger(
        filtered,
        broker_id=broker_id,
        valuation_date=valuation_date,
        fx_rates=fx_rates,
    )
    coverage.append(cash_cov)
    return _concat(ticker_ledger, cash_ledger), coverage, warnings


def _build_cash_ledger(
    cash_operations_df: pd.DataFrame,
    *,
    broker_id: str,
    valuation_date: date,
    fx_rates: pd.DataFrame | None,
) -> tuple[pd.DataFrame, InstrumentCoverage]:
    cash_id = cash_instrument_id(broker_id)
    cov = InstrumentCoverage(
        instrument_id=cash_id,
        status=CoverageStatus.COVERED,
        reason="deposit/withdrawal + lustra ticker CF",
        venue=VENUE,
    )
    if cash_operations_df is None or cash_operations_df.empty:
        return empty_ledger(), cov

    rows: list[dict] = []
    for _, row in cash_operations_df.iterrows():
        raw_type = str(row.get(XtbCashOperationsFile.TYPE) or "").strip()
        if is_xtb_cash_footer(raw_type):
            continue
        op_type = classify_xtb_cash_type(raw_type)
        if op_type is None:
            continue
        amount = pd.to_numeric(pd.Series([row.get(XtbCashOperationsFile.AMOUNT)]), errors="coerce").iloc[0]
        if pd.isna(amount):
            continue
        amount = float(amount)
        event_date = row.get(XtbCashOperationsFile.TIME)

        if op_type == CASH_OP_DEPOSIT:
            rows.append(
                build_ledger_row(
                    instrument_id=cash_id,
                    event_date=event_date,
                    category=CAPEX,
                    amount=-abs(amount),
                    currency=CURRENCY,
                    venue=VENUE,
                    source=broker_id,
                    description=raw_type,
                    title="CASH",
                    fx_rates=fx_rates,
                )
            )
            continue
        if op_type == CASH_OP_WITHDRAWAL:
            rows.append(
                build_ledger_row(
                    instrument_id=cash_id,
                    event_date=event_date,
                    category=DIVESTMENT,
                    amount=abs(amount),
                    currency=CURRENCY,
                    venue=VENUE,
                    source=broker_id,
                    description=raw_type,
                    title="CASH",
                    fx_rates=fx_rates,
                )
            )
            continue
        if op_type not in TICKER_ROI_TYPES:
            continue
        if op_type == CASH_OP_PURCHASE:
            ticker_cat, ticker_amt = CAPEX, -abs(amount)
        elif op_type == CASH_OP_SALE:
            ticker_cat, ticker_amt = DIVESTMENT, abs(amount)
        elif op_type == CASH_OP_DIVIDEND:
            ticker_cat, ticker_amt = REVENUES, abs(amount)
        else:
            continue
        cash_cat, cash_amt = cash_leg_category_and_amount(ticker_cat, ticker_amt)
        rows.append(
            build_ledger_row(
                instrument_id=cash_id,
                event_date=event_date,
                category=cash_cat,
                amount=cash_amt,
                currency=CURRENCY,
                venue=VENUE,
                source=broker_id,
                description=f"cash-leg:{raw_type}",
                title=xtb_instrument_id(row) or "",
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
