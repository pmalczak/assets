# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from app_proc.data_root import resolve_asset_dir
from evaluators.valuation_date import filter_excel_rows_on_or_before
from importers.assets.data_model import AssetsDef
from importers.assets.read_assets import read_assets
from importers.xtb.data_model import (
    CASH_OP_PURCHASE,
    CASH_OP_SALE,
    DEFAULT_XTB_ASSET_ID,
    TICKER_ROI_TYPES,
    XtbCashOperationsFile,
    XtbClosedPositionsFile,
    XtbOpenPositionsFile,
    classify_xtb_cash_type,
    is_xtb_cash_footer,
    xtb_instrument_id,
)
from importers.xtb.read_xtb import (
    latest_open_as_of,
    parse_xtb_date,
    read_xtb_cash,
    read_xtb_closed,
    read_xtb_open,
    xtb_open_position_rows,
)
from roi.broker_trading_roi import compute_ticker_roi, ticker_asset_id
from roi.categories import CAPEX, DIVESTMENT, REVENUES
from roi.compute_roi import roi_summary_to_row
from roi.data_model import CashFlowEvent


def compute_xtb_ticker_roi(
    valuation_date: date,
    *,
    broker_id: str = DEFAULT_XTB_ASSET_ID,
    cash_operations_df: pd.DataFrame | None = None,
    open_positions_df: pd.DataFrame | None = None,
    closed_positions_df: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame], list[str]]:
    warnings: list[str] = []
    if cash_operations_df is None or open_positions_df is None:
        asset_dir = _asset_dir(broker_id)
        if open_positions_df is None:
            open_positions_df = read_xtb_open(asset_dir, broker_id)
        if cash_operations_df is None:
            cash_operations_df, cash_warnings = read_xtb_cash(asset_dir, broker_id)
            warnings.extend(cash_warnings)
        if closed_positions_df is None:
            closed_positions_df = read_xtb_closed(asset_dir, broker_id)

    if closed_positions_df is None:
        closed_positions_df = pd.DataFrame()

    open_latest = latest_open_as_of(open_positions_df, valuation_date)
    cash_operations_df = _filter_xtb_rows_on_or_before(
        cash_operations_df, XtbCashOperationsFile.TIME, valuation_date
    )
    closed_positions_df = _filter_closed_on_or_before(closed_positions_df, valuation_date)

    events_by_asset, type_warnings = build_xtb_cashflows(cash_operations_df, broker_id)
    warnings.extend(type_warnings)
    terminal_by_ticker = _terminal_by_instrument(open_latest)
    qty_by_ticker = _qty_by_instrument(open_latest)
    all_tickers = (
        set(_instrument_from_asset_id(asset_id) for asset_id in events_by_asset)
        | set(terminal_by_ticker)
        | set(_closed_instruments(closed_positions_df))
    )

    rows = []
    for ticker in sorted(t for t in all_tickers if t):
        asset_id = ticker_asset_id(broker_id, ticker)
        events = events_by_asset.get(asset_id, _empty_events())
        terminal = float(terminal_by_ticker.get(ticker, 0.0))
        qty = float(qty_by_ticker.get(ticker, 0.0))
        open_qty = 1.0 if abs(qty) > 1e-12 and terminal != 0.0 else 0.0
        summary = compute_ticker_roi(
            asset_id,
            events,
            valuation_date,
            open_qty=open_qty,
            last_price=terminal if open_qty else 0.0,
        )
        rows.append(roi_summary_to_row(summary))

    return pd.DataFrame(rows), events_by_asset, warnings


def build_xtb_cashflows(
    cash_operations_df: pd.DataFrame,
    broker_id: str,
) -> tuple[dict[str, pd.DataFrame], list[str]]:
    if cash_operations_df is None or cash_operations_df.empty:
        return {}, []

    rows_by_asset: dict[str, list[dict]] = {}
    warnings: list[str] = []
    seen_unknown: set[str] = set()
    for _, row in cash_operations_df.iterrows():
        raw_type = str(row.get(XtbCashOperationsFile.TYPE) or "").strip()
        if is_xtb_cash_footer(raw_type):
            continue
        op_type = classify_xtb_cash_type(raw_type)
        if op_type is None:
            if raw_type and raw_type not in seen_unknown:
                warnings.append(f"Nieznany typ operacji XTB: {raw_type!r}")
                seen_unknown.add(raw_type)
            continue
        if op_type not in TICKER_ROI_TYPES:
            continue
        instrument = xtb_instrument_id(row)
        if not instrument:
            continue
        amount = pd.to_numeric(pd.Series([row.get(XtbCashOperationsFile.AMOUNT)]), errors="coerce").iloc[0]
        if pd.isna(amount):
            continue
        amount = float(amount)
        if op_type == CASH_OP_PURCHASE:
            category = CAPEX
            amount = -abs(amount)
        elif op_type == CASH_OP_SALE:
            category = DIVESTMENT
            amount = abs(amount)
        else:
            category = REVENUES
            amount = abs(amount)

        asset_id = ticker_asset_id(broker_id, instrument)
        rows_by_asset.setdefault(asset_id, []).append(
            {
                CashFlowEvent.ASSET_ID: asset_id,
                CashFlowEvent.DATE: _date_str(row.get(XtbCashOperationsFile.TIME)),
                CashFlowEvent.AMOUNT: amount,
                CashFlowEvent.CATEGORY: category,
                CashFlowEvent.SOURCE: broker_id,
                CashFlowEvent.DESCRIPTION: raw_type,
                CashFlowEvent.TITLE: str(row.get(XtbCashOperationsFile.INSTRUMENT) or instrument),
                CashFlowEvent.COUNTERPARTY: "",
                CashFlowEvent.ACCOUNT_NUMBER: str(
                    row.get(XtbCashOperationsFile.ID) or row.get(XtbCashOperationsFile.POSITION_ID) or ""
                ),
            }
        )

    result: dict[str, pd.DataFrame] = {}
    for asset_id, rows in rows_by_asset.items():
        df = pd.DataFrame(rows, columns=list(CashFlowEvent.COLUMN_ORDER))
        CashFlowEvent.check_structure(df)
        result[asset_id] = df
    return result, warnings


def _terminal_by_instrument(open_positions_df: pd.DataFrame) -> dict[str, float]:
    result: dict[str, float] = {}
    rows = xtb_open_position_rows(open_positions_df)
    if rows.empty or XtbOpenPositionsFile.VALUE not in rows.columns:
        return result
    for _, row in rows.iterrows():
        instrument = xtb_instrument_id(row)
        if not instrument:
            continue
        value = pd.to_numeric(pd.Series([row.get(XtbOpenPositionsFile.VALUE)]), errors="coerce").iloc[0]
        if pd.notna(value):
            result[instrument] = result.get(instrument, 0.0) + float(value)
    return result


def _qty_by_instrument(open_positions_df: pd.DataFrame) -> dict[str, float]:
    result: dict[str, float] = {}
    rows = xtb_open_position_rows(open_positions_df)
    if rows.empty or XtbOpenPositionsFile.VOLUME not in rows.columns:
        return result
    for _, row in rows.iterrows():
        instrument = xtb_instrument_id(row)
        if not instrument:
            continue
        qty = pd.to_numeric(pd.Series([row.get(XtbOpenPositionsFile.VOLUME)]), errors="coerce").iloc[0]
        if pd.notna(qty):
            result[instrument] = result.get(instrument, 0.0) + float(qty)
    return result


def _closed_instruments(closed_df: pd.DataFrame) -> set[str]:
    if closed_df is None or closed_df.empty:
        return set()
    result = set()
    for _, row in closed_df.iterrows():
        instrument = xtb_instrument_id(row)
        if instrument:
            result.add(instrument)
    return result


def _filter_xtb_rows_on_or_before(df: pd.DataFrame, col: str, valuation_date: date) -> pd.DataFrame:
    if df is None or df.empty or col not in df.columns:
        return df.copy() if df is not None else pd.DataFrame()
    work = df.copy()
    work["_iso_date"] = work[col].map(_date_str)
    filtered = filter_excel_rows_on_or_before(work, "_iso_date", valuation_date)
    return filtered.drop(columns=["_iso_date"])


def _filter_closed_on_or_before(df: pd.DataFrame, valuation_date: date) -> pd.DataFrame:
    if df is None or df.empty:
        return df.copy() if df is not None else pd.DataFrame()
    date_col = XtbClosedPositionsFile.CLOSE_TIME
    if date_col not in df.columns or df[date_col].astype(str).str.strip().eq("").all():
        date_col = XtbClosedPositionsFile.PERIOD_END
    return _filter_xtb_rows_on_or_before(df, date_col, valuation_date)


def _date_str(value) -> str:
    parsed = parse_xtb_date(value)
    if parsed is None:
        return date.today().isoformat()
    return parsed.isoformat()


def _asset_dir(broker_id: str) -> Path:
    assets = read_assets()
    rows = assets[assets[AssetsDef.ID].astype(str) == broker_id]
    if rows.empty:
        raise ValueError(f"Brak aktywa brokerskiego {broker_id!r} w a_config.xlsx (arkusz assets)")
    row = rows.iloc[0]
    asset_dir = resolve_asset_dir(broker_id, row[AssetsDef.TYPE])
    if not Path(asset_dir).is_dir():
        raise ValueError(f"Brak katalogu brokera: {asset_dir}")
    return asset_dir


def _empty_events() -> pd.DataFrame:
    return pd.DataFrame(columns=list(CashFlowEvent.COLUMN_ORDER))


def _instrument_from_asset_id(asset_id: str) -> str:
    return str(asset_id).split(":", 1)[-1]
